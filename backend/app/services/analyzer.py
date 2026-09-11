"""分析层：把"这次抓到的内容"和"上次的基准"比一比，决定要不要留痕。

里程碑 6 只做确定性部分：hash 粗筛 + difflib 差异。
里程碑 7 会在这里接 LLMClient，把差异翻译成"这件事意味着什么"并写 intelligence_events。
"""
import difflib
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.llm import count_changed_lines, get_llm_client
from app.core.source_registry import SourceType, get_source_config
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.snapshot import PageSnapshot
from app.models.source import MonitorSource
from app.services import crawler

settings = get_settings()

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


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
    """统一的 unified diff，只保留必要上下文并按上限截断。"""
    diff = difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        fromfile="上次",
        tofile="本次",
        lineterm="",
        n=1,
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
) -> bool:
    """变化足够显著时，让 LLM 把差异翻译成一条情报事件。

    先用 diff 的变更行数做粗筛：太轻微的变化只留快照、不生成事件——
    既避免噪声打扰用户，也避免为无意义的变化消耗 LLM 开销。
    """
    diff_text = snapshot.diff_text or ""
    if count_changed_lines(diff_text) < settings.llm_min_change_lines:
        return False

    analysis = await get_llm_client().classify_and_summarize(
        competitor_name=competitor.name,
        source_type=source.source_type,
        url=source.url,
        diff_text=diff_text,
    )
    db.add(
        IntelligenceEvent(
            competitor_id=competitor.id,
            source_id=source.id,
            snapshot_id=snapshot.id,
            event_type=analysis.event_type,
            title=analysis.title,
            summary=analysis.summary,
            diff_detail=diff_text,
            keywords=analysis.keywords,
            confidence=analysis.confidence,
            priority=analysis.priority,
        )
    )
    return True


async def crawl_source(
    db: AsyncSession,
    competitor: Competitor,
    source: MonitorSource,
) -> SourceCrawlOutcome:
    """抓一个监控源：抓取 → 提取 → 与上次基准比对 → 留痕 → 更新健康度。

    任何异常都在这里收敛成 failed 结果，不抛穿主流程——
    单个源失败不影响同批次其他源（见 docs/data-source-design.md 第八节）。
    """
    cfg = get_source_config(source.source_type)
    source.last_crawled_at = datetime.now(timezone.utc)

    try:
        fetch = await crawler.fetch_html(source.url)
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
            "未提取到有效正文（该页面可能需要浏览器渲染，Playwright 渲染待接入）",
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
        diff_text=build_diff(previous.clean_text or "", text),
    )
    db.add(snapshot)
    # 先 flush 拿到自增 id，事件才能精确归因到"哪一条快照"
    await db.flush()
    event_created = await _create_event(db, competitor, source, snapshot)

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
