"""任务调度（里程碑 10）：进程内 APScheduler，不引 Celery、不依赖外部 broker。

为什么是「一个 tick 扫描到期任务」而不是「给每个监控源注册一个 job」：
- 监控源会被随时增删改（改频率、停用、换 URL），逐个注册 job 就必须在每个写入口
  同步重注册，容易漏；
- 扫描式只有一个固定 job，配置改动"下一分钟"自动生效，零重注册逻辑；
- 代价是到期精度取决于 tick 间隔（默认 60s），对"每小时 / 每天"级频率完全够用。

两个 job：
- `crawl_due_sources`     按各源自己的 `interval_minutes` 到期抓取（含 LLM 分析与事件生成）
- `generate_weekly_reports`  每周日自动生成"本节竞品周报"，同一周已存在则跳过
- `generate_monthly_reports` 每月末自动生成"本月竞品月报"，同一月已存在则跳过
"""
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.timeutil import format_time, to_utc
from app.models.competitor import Competitor, CompetitorStatus
from app.models.crawl_log import TRIGGER_SCHEDULER
from app.models.source import MonitorSource
from app.models.user import User
from app.models.weekly_report import ReportType, WeeklyReport
from app.services import analyzer, notifier
from app.services import report as report_service

logger = logging.getLogger(__name__)
settings = get_settings()

JOB_CRAWL = "crawl_due_sources"
JOB_REPORT = "generate_weekly_reports"
JOB_MONTHLY_REPORT = "generate_monthly_reports"

# 分布式锁的名字（多副本部署时保证同一批任务只由一个实例执行）
LOCK_CRAWL = "scheduler:crawl-tick"
LOCK_REPORT = "scheduler:weekly-report"
LOCK_MONTHLY_REPORT = "scheduler:monthly-report"

# 进程内单例；未启动时为 None
_scheduler: AsyncIOScheduler | None = None


def _is_due(last_crawled_at: datetime | None, interval_minutes: int, now: datetime) -> bool:
    """上次抓取时间 + 该源自己的频率 <= 现在，即视为到期。

    时间口径与展示层一致：SQLite 取回的是 naive datetime（实为 UTC），先按 UTC 解读。
    """
    last = to_utc(last_crawled_at)
    if last is None:
        return True  # 从没抓过 → 立刻纳入
    return (now - last).total_seconds() >= max(1, interval_minutes) * 60


@asynccontextmanager
async def _job_lock(name: str) -> AsyncIterator[bool]:
    """多副本互斥：抢不到锁就跳过本轮（不等待，也不阻塞其他实例干活）。

    锁带 TTL：持有进程崩溃后自动过期，不会死锁；
    释放时校验令牌，避免误删其他实例刚抢到的锁。
    """
    cache = get_cache()
    token = await cache.acquire(name, settings.scheduler_lock_ttl_seconds)
    if token is None:
        logger.info("调度器：%s 已被其他实例持有，本轮跳过", name)
        yield False
        return
    try:
        yield True
    finally:
        await cache.release(name, token)


async def crawl_due_sources() -> int:
    """扫描到期的监控源并逐个抓取，返回实际抓取的源数量。

    外层套分布式锁：多副本部署时保证同一批页面只由一个实例抓取。
    """
    async with _job_lock(LOCK_CRAWL) as acquired:
        if not acquired:
            return 0
        return await _crawl_due_sources_locked()


async def _crawl_due_sources_locked() -> int:
    """抢到锁之后的实际抓取逻辑（与锁无关，单独成函数便于阅读）。"""
    now = datetime.now(timezone.utc)
    crawled = changed = events = 0
    # 按用户累计本轮结果：调度器是**全库扫**（不按 user 过滤），一批里可能混着
    # 多个账号的页面，所以汇总通知必须拆回各自的竞品归属人，见 _notify_crawl_summary。
    per_user: dict[int, dict[str, int]] = {}

    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(MonitorSource, Competitor)
                .join(Competitor, Competitor.id == MonitorSource.competitor_id)
                .where(MonitorSource.enabled.is_(True))
                .where(Competitor.status == CompetitorStatus.ACTIVE)
                .where(Competitor.deleted_at.is_(None))
                # 最久没抓的排前面（SQLite 里 NULL 在 ASC 时天然最前，正好让新源优先）
                .order_by(MonitorSource.last_crawled_at.asc())
            )
        ).all()

        due = [
            (source, competitor)
            for source, competitor in rows
            if _is_due(source.last_crawled_at, source.interval_minutes, now)
        ][: settings.scheduler_batch_limit]

        if not due:
            return 0

        logger.info("调度器：%d 个监控源到期，开始抓取", len(due))
        for index, (source, competitor) in enumerate(due):
            try:
                outcomes = await analyzer.run_competitor_crawl(
                    db, competitor, [source], trigger=TRIGGER_SCHEDULER
                )
                await db.commit()  # 逐个提交：中途异常不至于丢掉整批进度
            except Exception:  # noqa: BLE001 - 单源异常不能影响同批其他源
                await db.rollback()
                logger.exception("调度器：抓取异常 source=%s url=%s", source.id, source.url)
                continue

            crawled += 1
            source_changed = sum(1 for outcome in outcomes if outcome.changed)
            source_events = sum(1 for outcome in outcomes if outcome.event_created)
            changed += source_changed
            events += source_events

            stat = per_user.setdefault(
                competitor.user_id, {"crawled": 0, "changed": 0, "events": 0}
            )
            stat["crawled"] += 1
            stat["changed"] += source_changed
            stat["events"] += source_events

            # 温和错峰：同一批内不连续冲击目标站点
            if settings.scheduler_jitter_seconds > 0 and index < len(due) - 1:
                await asyncio.sleep(settings.scheduler_jitter_seconds)

        # 会话还开着时一次拿全表 id→(email, 是否开启邮件通知)（避免逐用户查库）
        # 注意：select 出来是 3 列 (id, email, preferences)，不能直接 dict()——dict()
        # 只吃 2 元组，3 元组会抛 ValueError。必须显式组装成 id → (email, 开关)。
        pref_rows = (
            await db.execute(select(User.id, User.email, User.preferences))
        ).all()
        emails: dict[int, tuple[str | None, bool]] = {
            uid: (email, (prefs or {}).get("email_notify_enabled", True))
            for uid, email, prefs in pref_rows
        }

    if crawled:
        logger.info(
            "调度器：本轮完成 sources=%s changed=%s events=%s", crawled, changed, events
        )
    await _notify_crawl_summary(per_user, emails)
    return crawled


async def _notify_crawl_summary(
    per_user: dict[int, dict[str, int]],
    emails: dict[int, tuple[str | None, bool]],
) -> None:
    """把本轮抓取结果**按用户分别汇报**——只发给竞品归属人自己。

    调度器一批会扫到多个账号的页面，所以必须逐用户发；收件人取该账号自己在
    「用户中心」绑定的邮箱。**没绑邮箱就只推站内铃铛、不发邮件**，与 analyzer 的
    高优事件同口径——绝不能回落到 NOTIFY_RECIPIENTS / SMTP_USERNAME：那是运维
    邮箱，会把 A 用户的竞品动态投到 B 的信箱。
    """
    for user_id, stat in per_user.items():
        # 本轮没有变化就不打扰（"抓了但没变"不值得发信）
        if not (stat["changed"] or stat["events"]):
            continue
        row = emails.get(user_id)
        email = row[0] if row else None
        # 用户关闭了邮件通知：跳过邮件，只保留站内铃铛
        email_enabled = row[1] if row else True
        if not email or not email_enabled:
            continue
        await notifier.notify(
            f"竞品雷达：你的 {stat['changed']} 处监控页面发生变化",
            f"本轮自动抓取你的 {stat['crawled']} 个监控页面，"
            f"{stat['changed']} 处发生变化，新增 {stat['events']} 条情报事件。"
            "登录「情报事件」页查看详情。",
            to=[email],
            email_enabled=email_enabled,
        )


def _report_ready_mail(
    email: str | None, report: WeeklyReport, label: str
) -> tuple[str, str, str] | None:
    """这期报告已生成 → 返回 (收件人, 标题, 正文)；没邮箱或名下没竞品则 None。

    没有竞品的账号也会被生成一份"空报告"，但给它发「你的周报已生成」很莫名，
    所以只通知真正有竞品要看的账号。
    """
    if not email or not report.competitor_count:
        return None
    return (
        email,
        f"竞品雷达：你的本{label}已生成",
        f"你的「{report.title}」已生成（覆盖 {report.competitor_count} 个竞品、"
        f"{report.event_count} 条情报），可在「AI 报告」页查看。",
    )


async def generate_weekly_reports() -> int:
    """为每个用户生成本周周报（周日触发，跨度=周一~今天）；同一周已存在则跳过。"""
    return await _generate_period_reports(ReportType.WEEKLY, LOCK_REPORT)


async def generate_monthly_reports() -> int:
    """为每个用户生成本月月报（月末触发，跨度=本月1号~今天）；同一月已存在则跳过。"""
    return await _generate_period_reports(ReportType.MONTHLY, LOCK_MONTHLY_REPORT)


async def _generate_period_reports(report_type: ReportType, lock_name: str) -> int:
    """生成某一自然期（周报/月报）的通用逻辑；同一期已存在则跳过，返回新生成份数。

    外层套分布式锁：`window_has_report` 的"查了再写"在多副本下存在竞态，
    锁把它收敛成串行，保证同一期只生成一份。
    """
    async with _job_lock(lock_name) as acquired:
        if not acquired:
            return 0
        return await _generate_period_reports_locked(report_type)


async def _generate_period_reports_locked(report_type: ReportType) -> int:
    """抢到锁之后的实际生成逻辑。"""
    # 周报每周日触发、月报每月末触发，此时"当前自然期"恰好覆盖完整一周/一月，
    # 直接用当前窗口（`_window` 结束日=今天）生成即可。
    start, _ = report_service.current_window(report_type)
    created = 0
    label = "月报" if report_type == ReportType.MONTHLY else "周报"

    async with SessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        # (收件人, 标题, 正文)：攒齐后出会话再发信，不把 DB 会话和 SMTP 超时绑在一起
        pending: list[tuple[str, str, str]] = []
        for user in users:
            try:
                if await report_service.window_has_report(
                    db, user.id, start, report_type
                ):
                    continue
                report = await report_service.generate_report(
                    db, user, report_type=report_type
                )
                await db.commit()
                created += 1
            except Exception:  # noqa: BLE001 - 单个用户失败不影响其他用户
                await db.rollback()
                logger.exception("调度器：生成%s失败 user=%s", label, user.id)
                continue
            # 顺手把要发的邮件拼成纯值（收件人 + 标题 + 正文），别把 ORM 对象带出会话
            # 用户关闭了邮件通知：本账号的周报邮件直接跳过（只保留站内铃铛）
            email_enabled = (user.preferences or {}).get("email_notify_enabled", True)
            if not email_enabled:
                continue
            mail = _report_ready_mail(user.email, report, label)
            if mail is not None:
                pending.append(mail)

    if created:
        logger.info("调度器：已为 %d 个账号生成本%s", created, label)
    # 报告是「这个账号的」，完成通知只能发给他本人（绝不发运维邮箱）
    for email, title, message in pending:
        await notifier.notify(title, message, to=[email])
    return created


async def count_due_sources(db: AsyncSession, user_id: int) -> int:
    """当前账号名下到期、等待抓取的监控源数量（给状态接口用）。

    调度器本身是全局的（一批扫全库），但状态接口只统计调用者自己的源，
    避免把别人还有多少待抓暴露出来。
    """
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(MonitorSource.last_crawled_at, MonitorSource.interval_minutes)
            .join(Competitor, Competitor.id == MonitorSource.competitor_id)
            .where(
                MonitorSource.enabled.is_(True),
                Competitor.user_id == user_id,
                Competitor.status == CompetitorStatus.ACTIVE,
                Competitor.deleted_at.is_(None),
            )
        )
    ).all()
    return sum(1 for last, interval in rows if _is_due(last, interval, now))


def start_scheduler() -> None:
    """启动进程内调度器（在 app 启动时调用）。"""
    global _scheduler
    if not settings.scheduler_enabled:
        logger.info("调度器未启用（SCHEDULER_ENABLED=false），只能手动触发抓取")
        return
    if _scheduler is not None:
        return

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        crawl_due_sources,
        trigger=IntervalTrigger(seconds=settings.scheduler_tick_seconds),
        id=JOB_CRAWL,
        name="到期监控源自动抓取",
        max_instances=1,  # 上一轮没跑完就不再叠加，避免自我并发
        coalesce=True,  # 进程重启错过多次时只补跑一次
        misfire_grace_time=settings.scheduler_tick_seconds,
    )
    scheduler.add_job(
        generate_weekly_reports,
        trigger=CronTrigger(
            # 每周最后一天（周日）自动生成本周周报
            day_of_week=settings.report_cron_day_of_week,
            hour=settings.report_cron_hour,
            minute=settings.report_cron_minute,
            timezone=settings.app_timezone,
        ),
        id=JOB_REPORT,
        name="每周竞品周报自动生成",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        generate_monthly_reports,
        trigger=CronTrigger(
            # 每月最后一天自动生成本月月报（apscheduler 用 day='last'）
            day=settings.report_monthly_cron_day,
            hour=settings.report_cron_hour,
            minute=settings.report_cron_minute,
            timezone=settings.app_timezone,
        ),
        id=JOB_MONTHLY_REPORT,
        name="每月竞品月报自动生成",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "调度器已启动：每 %ss 扫描一次到期监控源（单次上限 %s 个），"
        "周报每周 %s %02d:%02d 生成，月报每月 %s %02d:%02d 生成",
        settings.scheduler_tick_seconds,
        settings.scheduler_batch_limit,
        settings.report_cron_day_of_week,
        settings.report_cron_hour,
        settings.report_cron_minute,
        settings.report_monthly_cron_day,
        settings.report_cron_hour,
        settings.report_cron_minute,
    )


def shutdown_scheduler() -> None:
    """停止调度器（在 app 关闭时调用）。"""
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("调度器已停止")


def get_scheduler_status() -> dict:
    """调度器运行状态与各 job 的下次执行时间（观测用）。"""
    base = {
        "enabled": settings.scheduler_enabled,
        "tick_seconds": settings.scheduler_tick_seconds,
        "batch_limit": settings.scheduler_batch_limit,
        "notify_enabled": settings.notify_enabled,
        "notify_backend": settings.notify_backend,
    }
    if _scheduler is None:
        return {**base, "running": False, "jobs": []}
    return {
        **base,
        "running": bool(_scheduler.running),
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "trigger": str(job.trigger),
                # 被暂停的 job 没有 next_run_time，format_time 会返回空串
                "next_run_at": format_time(getattr(job, "next_run_time", None)),
            }
            for job in _scheduler.get_jobs()
        ],
    }
