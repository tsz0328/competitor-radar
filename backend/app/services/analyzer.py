"""分析层：把"这次抓到的内容"和"上次的基准"比一比，决定要不要留痕与是否生成事件。

确定性部分：hash 粗筛 + difflib 差异；语义部分：交给 LLMClient（无 Key 走规则兜底）。
"""
import difflib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.event_types import EVENT_TYPE_LABELS
from app.core.llm import get_llm_client, is_significant_change
from app.core.runtime_config import get_llm_config
from app.core.source_registry import RenderMode, SourceType, SourceTypeConfig, get_source_config
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.snapshot import PageSnapshot
from app.models.source import MonitorSource
from app.services import browser, crawler, notifier

settings = get_settings()

logger = logging.getLogger(__name__)

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


@dataclass
class SourceCrawlOutcome:
    """单个监控源这一次抓取的结果（回给前端做反馈）。"""

    source_id: int
    source_name: str
    source_type: SourceType
    status: str
    http_status: int | None = None
    changed: bool = False
    first_time: bool = False
    # 本次变化是否足以生成一条情报事件（太轻微则只留快照）
    event_created: bool = False
    error: str | None = None
    duration_ms: int = 0


def build_diff(old_text: str, new_text: str) -> str:
    """生成统一 diff，兼容旧调用；需要按 source_type 分流时传 build_source_diff。"""
    return _build_unified_diff(old_text, new_text, n=1)

def build_source_diff(old_text: str, new_text: str, differ: str) -> str:
    """按注册表的 differ 策略生成变化文本。

    full_text 保留少量上下文；item_set/structured 把行当作条目排序，
    输出零上下文的 + / - 行，适合 RSS、更新日志和版本/价格类 text。
    """
    if differ in ("item_set", "structured"):
        old_lines = sorted({line for line in old_text.splitlines() if line.strip()})
        new_lines = sorted({line for line in new_text.splitlines() if line.strip()})
        return _build_unified_diff("\n".join(old_lines), "\n".join(new_lines), n=0)
    return _build_unified_diff(old_text, new_text, n=1)

def _build_unified_diff(old_text: str, new_text: str, n: int) -> str:
    diff = difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        fromfile="上次",
        tofile="本次",
        lineterm="",
        n=n,
    )
    text = "\n".join(diff)
    if len(text) > settings.crawl_max_diff_chars:
        text = text[: settings.crawl_max_diff_chars] + "\n...（差异过长，已截断）"
    return text


async def _last_success_snapshot(db: AsyncSession, source_id: int) -> PageSnapshot | None:
    """取该源最近一次成功的快照，作为比对基准。"""
    result = await db.execute(
        select(PageSnapshot)
        .where(PageSnapshot.source_id == source_id, PageSnapshot.is_success.is_(True))
        .order_by(PageSnapshot.crawled_at.desc(), PageSnapshot.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _mark_success(source: MonitorSource) -> None:
    source.last_status = STATUS_SUCCESS
    source.last_error = None
    source.fail_count = 0


def _record_failure(
    db: AsyncSession,
    competitor: Competitor,
    source: MonitorSource,
    reason: str,
    http_status: int | None,
    duration_ms: int,
) -> SourceCrawlOutcome:
    """失败留痕：记健康度 + 一条失败快照；连续失败达阈值则自动停用该源。"""
    source.last_status = STATUS_FAILED
    source.fail_count = (source.fail_count or 0) + 1
    source.last_error = reason

    if source.fail_count >= settings.crawl_max_fail_count:
        source.enabled = False
        reason = f"{reason}（连续失败 {source.fail_count} 次，已自动暂停该监控源）"

    db.add(
        PageSnapshot(
            competitor_id=competitor.id,
            source_id=source.id,
            source_type=source.source_type,
            url=source.url,
            http_status=http_status,
            is_success=False,
            fail_reason=reason,
            change_detected=False,
        )
    )
    return SourceCrawlOutcome(
        source_id=source.id,
        source_name=source.name,
        source_type=source.source_type,
        status=STATUS_FAILED,
        http_status=http_status,
        error=reason,
        duration_ms=duration_ms,
    )


async def _create_event(
    db: AsyncSession,
    competitor: Competitor,
    source: MonitorSource,
    snapshot: PageSnapshot,
) -> IntelligenceEvent | None:
    """变化足够显著时，让 LLM 把差异翻译成一条情报事件。

    先做粗筛再调 LLM：太轻微的变化只留快照、不生成事件——
    既避免噪声打扰用户，也避免为无意义的变化消耗 LLM 开销。
    粗筛不只看变更行数，也看是否命中价格/版本/变更动词等高价值信号，
    否则「专业版 ￥99 -> ￥129」这种单行关键改动会被误杀。

    返回新创建的事件对象（供调用方做高优先级即时通知）；过轻则不生成，返回 None。
    """
    diff_text = snapshot.diff_text or ""
    # 阈值取运行时配置：设置页改了"最小变更行数"立即生效
    if not is_significant_change(diff_text, get_llm_config().min_change_lines):
        return None

    analysis = await get_llm_client().classify_and_summarize(
        competitor_name=competitor.name,
        source_type=source.source_type,
        url=source.url,
        diff_text=diff_text,
    )
    event = IntelligenceEvent(
        competitor_id=competitor.id,
        source_id=source.id,
        snapshot_id=snapshot.id,
        event_type=analysis.event_type,
        title=analysis.title,
        summary=analysis.summary,
        ai_analysis=analysis.analysis,
        diff_detail=diff_text,
        keywords=analysis.keywords,
        confidence=analysis.confidence,
        priority=analysis.priority,
    )
    db.add(event)
    # 先 flush 拿到自增 id：事件才能精确归因到快照，且通知可带详情链接
    await db.flush()
    return event


async def _notify_high_priority(
    competitor: Competitor, source: MonitorSource, event: IntelligenceEvent
) -> None:
    """高优先级情报事件即时推送一条通知，让用户不必每天打开 Dashboard 也能收到提醒。

    这是相对于"整批结束后的汇总通知"的**单条即时推送**（见 scheduler 的批次汇总）。
    推送是旁路：notifier 内部已保证失败不影响主流程，且只在 NOTIFY_ENABLED 时发送。
    """
    link = f"{settings.frontend_base_url.rstrip('/')}/app/event"
    label = EVENT_TYPE_LABELS.get(event.event_type, "情报变化")
    title = f"🔴 重要竞品变化：{competitor.name} · {label}"
    message = (
        f"{event.title}\n\n"
        f"{event.summary}\n\n"
        f"来源页面：{source.name}（{source.url}）\n"
        f"事件ID：{event.id}　查看详情：{link}"
    )
    await notifier.notify(title, message)


def _looks_like_html(html: str) -> bool:
    """粗略判断抓回来的到底是不是网页 HTML（而不是 RSS/Atom Feed）。

    只扫前 2KB：Feed 一定以 <rss / <feed / <atom 开头，普通网页则有 <html/<body。
    用于在「RSS 提取却抽不到正文」时，直接点破"你给的是网页首页而非 Feed"。
    """
    head = (html or "")[:2048].lower()
    if not head:
        return False
    is_feed = "<rss" in head or "<feed" in head or "<atom" in head
    is_html = "<!doctype html" in head or "<html" in head or "<body" in head
    # 既像网页又像 Feed 极少见，优先按 Feed 判断，避免误判
    return is_html and not is_feed


def _empty_content_reason(cfg: SourceTypeConfig, html: str | None = None) -> str:
    """抓取成功但没提取到正文时，给一句准确、可操作的说明。

    只有 browser 类型才会真正尝试浏览器渲染，http 类型仅走 httpx——
    文案要如实反映"到底试了什么"，别让用户以为浏览器也试过。

    若已拿到正文内容（html），还会进一步判断：RSS 类型却抓回网页首页时，
    直接点破"你给的是 HTML 首页而非 Feed"，免得用户以为是"链接打不开"。
    """
    if cfg.render == RenderMode.BROWSER:
        reason = "未提取到有效正文（httpx 与浏览器渲染均未取到内容）" + browser.availability_note()
    else:
        reason = "未提取到有效正文（该类型只走 httpx 直连，未取到内容）"
    if cfg.extractor == "rss":
        if html and _looks_like_html(html):
            reason += (
                "；该地址返回的是网页 HTML 首页，并非 RSS/Atom Feed"
                "（请把地址换成订阅源，如 /feed、/rss.xml、/atom.xml）"
            )
        else:
            reason += "；该地址可能不是 RSS/Atom 订阅源，请确认链接是否正确"
    else:
        reason += "；页面可能是纯 JS 渲染或需登录，也可能是地址有误"
    return reason


async def crawl_source(
    db: AsyncSession,
    competitor: Competitor,
    source: MonitorSource,
) -> SourceCrawlOutcome:
    """抓一个监控源，并加上源级非阻塞锁。"""
    lock_key = f"crawl:source:{source.id}"
    token = await get_cache().acquire(lock_key, settings.crawl_source_lock_ttl_seconds)
    if token is None:
        return SourceCrawlOutcome(
            source_id=source.id,
            source_name=source.name,
            source_type=source.source_type,
            status=STATUS_SKIPPED,
            error="该监控源正在抓取中，已跳过本次触发",
        )
    try:
        return await _crawl_source_locked(db, competitor, source)
    finally:
        await get_cache().release(lock_key, token)

async def _crawl_source_locked(
    db: AsyncSession,
    competitor: Competitor,
    source: MonitorSource,
) -> SourceCrawlOutcome:
    """抓取 -> 提取 -> 与上次基准比对 -> 留痕 -> 更新健康度。"

    任何异常都在这里收敛成 failed 结果，不抛穿主流程——
    单个源失败不影响同批次其他源（见 docs/data-source-design.md 第八节）。
    """
    cfg = get_source_config(source.source_type)
    source.last_crawled_at = datetime.now(timezone.utc)

    try:
        fetch = await crawler.fetch_auto(source.url, cfg)
    except Exception as exc:  # noqa: BLE001 - 兜底，绝不让单源异常打断整批
        return _record_failure(
            db, competitor, source, f"抓取异常：{type(exc).__name__}", None, 0
        )

    if not fetch.ok:
        return _record_failure(
            db, competitor, source, fetch.error or "抓取失败", fetch.http_status, fetch.elapsed_ms
        )

    text = crawler.extract_text(fetch.html, cfg)
    if len(text) < settings.crawl_min_text_length:
        return _record_failure(
            db,
            competitor,
            source,
            _empty_content_reason(cfg, fetch.html),
            fetch.http_status,
            fetch.elapsed_ms,
        )

    new_hash = crawler.compute_hash(text)
    previous = await _last_success_snapshot(db, source.id)

    # 首次抓取：建立基准，不算"变化"
    if previous is None:
        db.add(
            PageSnapshot(
                competitor_id=competitor.id,
                source_id=source.id,
                source_type=source.source_type,
                url=source.url,
                raw_html_path=crawler.persist_raw_html(competitor.id, source.id, fetch.html),
                clean_text=text,
                content_hash=new_hash,
                http_status=fetch.http_status,
                is_success=True,
                change_detected=False,
            )
        )
        _mark_success(source)
        return SourceCrawlOutcome(
            source_id=source.id,
            source_name=source.name,
            source_type=source.source_type,
            status=STATUS_SUCCESS,
            http_status=fetch.http_status,
            changed=False,
            first_time=True,
            duration_ms=fetch.elapsed_ms,
        )

    # 未变化：不留快照，只刷新健康度，避免按小时抓取把表撑大
    if previous.content_hash == new_hash:
        _mark_success(source)
        return SourceCrawlOutcome(
            source_id=source.id,
            source_name=source.name,
            source_type=source.source_type,
            status=STATUS_SUCCESS,
            http_status=fetch.http_status,
            changed=False,
            duration_ms=fetch.elapsed_ms,
        )

    # 有变化：留快照 + difflib 差异，再交给 LLM 生成情报事件
    snapshot = PageSnapshot(
        competitor_id=competitor.id,
        source_id=source.id,
        source_type=source.source_type,
        url=source.url,
        raw_html_path=crawler.persist_raw_html(competitor.id, source.id, fetch.html),
        clean_text=text,
        content_hash=new_hash,
        http_status=fetch.http_status,
        is_success=True,
        change_detected=True,
        diff_text=build_source_diff(previous.clean_text or "", text, cfg.differ),
    )
    db.add(snapshot)
    # 先 flush 拿到自增 id，事件才能精确归因到"哪一条快照"
    await db.flush()
    event = await _create_event(db, competitor, source, snapshot)
    event_created = event is not None

    # 高优先级事件即时推送（独立于调度器整批结束后的汇总通知），让用户尽早收到提醒
    if event is not None and event.priority == "high":
        await _notify_high_priority(competitor, source, event)

    _mark_success(source)
    return SourceCrawlOutcome(
        source_id=source.id,
        source_name=source.name,
        source_type=source.source_type,
        status=STATUS_SUCCESS,
        http_status=fetch.http_status,
        changed=True,
        event_created=event_created,
        duration_ms=fetch.elapsed_ms,
    )


async def run_competitor_crawl(
    db: AsyncSession,
    competitor: Competitor,
    sources: list[MonitorSource],
) -> list[SourceCrawlOutcome]:
    """顺序抓取给定的若干个监控源，并输出符合隐私约束的结构化日志。

    手动触发（接口）与定时调度（scheduler）共用这一段，
    保证两条入口在留痕策略、失败收敛与日志口径上完全一致。

    注意：这里不 commit，由调用方决定提交粒度（接口一次性提交、调度逐源提交）。
    """
    outcomes: list[SourceCrawlOutcome] = []
    for source in sources:
        outcome = await crawl_source(db, competitor, source)
        outcomes.append(outcome)
        # 只记 URL / 类型 / 状态码 / 耗时 / 错误摘要，不记正文（见 data-source-design 第八节）
        logger.log(
            logging.WARNING if outcome.status == STATUS_FAILED else logging.INFO,
            "crawl competitor=%s source=%s type=%s status=%s http=%s changed=%s "
            "first_time=%s event_created=%s duration=%sms url=%s error=%s",
            competitor.id,
            source.id,
            source.source_type.value,
            outcome.status,
            outcome.http_status,
            outcome.changed,
            outcome.first_time,
            outcome.event_created,
            outcome.duration_ms,
            source.url,
            outcome.error,
        )
    return outcomes
