"""任务调度（里程碑 10）：进程内 APScheduler，不引 Celery、不依赖外部 broker。

为什么是「一个 tick 扫描到期任务」而不是「给每个监控源注册一个 job」：
- 监控源会被随时增删改（改频率、停用、换 URL），逐个注册 job 就必须在每个写入口
  同步重注册，容易漏；
- 扫描式只有一个固定 job，配置改动"下一分钟"自动生效，零重注册逻辑；
- 代价是到期精度取决于 tick 间隔（默认 60s），对"每小时 / 每天"级频率完全够用。

两个 job：
- `crawl_due_sources`     按各源自己的 `interval_minutes` 到期抓取（含 LLM 分析与事件生成）
- `generate_weekly_reports` 每周一自动生成上一自然周的周报，同一周已存在则跳过
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
from app.models.competitor import Competitor
from app.models.source import MonitorSource
from app.models.user import User
from app.services import analyzer, notifier
from app.services import report as report_service

logger = logging.getLogger(__name__)
settings = get_settings()

JOB_CRAWL = "crawl_due_sources"
JOB_REPORT = "generate_weekly_reports"

# 分布式锁的名字（多副本部署时保证同一批任务只由一个实例执行）
LOCK_CRAWL = "scheduler:crawl-tick"
LOCK_REPORT = "scheduler:weekly-report"

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

    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(MonitorSource, Competitor)
                .join(Competitor, Competitor.id == MonitorSource.competitor_id)
                .where(MonitorSource.enabled.is_(True))
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
                outcomes = await analyzer.run_competitor_crawl(db, competitor, [source])
                await db.commit()  # 逐个提交：中途异常不至于丢掉整批进度
            except Exception:  # noqa: BLE001 - 单源异常不能影响同批其他源
                await db.rollback()
                logger.exception("调度器：抓取异常 source=%s url=%s", source.id, source.url)
                continue

            crawled += 1
            changed += sum(1 for outcome in outcomes if outcome.changed)
            events += sum(1 for outcome in outcomes if outcome.event_created)

            # 温和错峰：同一批内不连续冲击目标站点
            if settings.scheduler_jitter_seconds > 0 and index < len(due) - 1:
                await asyncio.sleep(settings.scheduler_jitter_seconds)

    if crawled:
        logger.info(
            "调度器：本轮完成 sources=%s changed=%s events=%s", crawled, changed, events
        )
    if changed or events:
        await notifier.notify(
            f"竞品雷达：发现 {changed} 处页面变化",
            f"本轮自动抓取 {crawled} 个监控页面，{changed} 处发生变化，"
            f"新增 {events} 条情报事件。登录「情报事件」页查看详情。",
        )
    return crawled


async def generate_weekly_reports() -> int:
    """为每个用户生成上一自然周的周报；同一周已生成过则跳过，返回新生成的份数。

    外层套分布式锁：`window_has_report` 的"查了再写"在多副本下存在竞态，
    锁把它收敛成串行，保证同一周只生成一份。
    """
    async with _job_lock(LOCK_REPORT) as acquired:
        if not acquired:
            return 0
        return await _generate_weekly_reports_locked()


async def _generate_weekly_reports_locked() -> int:
    """抢到锁之后的实际生成逻辑。"""
    # 周一 06:00 触发时，生成本周还没结束，所以这里生成"上一个完整自然周"
    start, _ = report_service.previous_window()
    created = 0

    async with SessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        for user in users:
            try:
                if await report_service.window_has_report(db, user.id, start):
                    continue
                await report_service.generate_weekly_report(db, user, weeks_ago=1)
                await db.commit()
                created += 1
            except Exception:  # noqa: BLE001 - 单个用户失败不影响其他用户
                await db.rollback()
                logger.exception("调度器：生成周报失败 user=%s", user.id)

    if created:
        logger.info("调度器：已为 %d 个账号生成本周周报", created)
        await notifier.notify(
            "竞品雷达：本周周报已生成",
            f"已为 {created} 个账号生成本周竞品周报，可在「AI 报告」页查看。",
        )
    return created


async def count_due_sources(db: AsyncSession) -> int:
    """当前到期、等待抓取的监控源数量（给状态接口用）。"""
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(MonitorSource.last_crawled_at, MonitorSource.interval_minutes).where(
                MonitorSource.enabled.is_(True)
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
            day_of_week=settings.report_cron_day_of_week,
            hour=settings.report_cron_hour,
        ),
        id=JOB_REPORT,
        name="每周竞品周报自动生成",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "调度器已启动：每 %ss 扫描一次到期监控源（单次上限 %s 个），周报每周 %s %02d:00 生成",
        settings.scheduler_tick_seconds,
        settings.scheduler_batch_limit,
        settings.report_cron_day_of_week,
        settings.report_cron_hour,
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
