"""情报事件接口（里程碑 7）。

约定：`GET /api/events` 返回「顶部统计 + 事件记录」，
统计口径不受 eventType 影响（否则按类型筛选后其它分类会全变 0），
但同样受竞品与时间范围约束。
"""
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.event_types import EVENT_TYPE_CATEGORY, EventType
from app.core.exceptions import ERR_EVENT_NOT_FOUND, BusinessError
from app.core.timeutil import local_day_end_utc, local_day_start_utc
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.snapshot import PageSnapshot
from app.models.source import MonitorSource
from app.models.user import User
from app.schemas.event import (
    DailyInsightOut,
    EventDetailOut,
    EventListOut,
    EventRecordOut,
    EventSummaryOut,
    SnapshotOut,
)
from app.services.daily import build_daily_insight

router = APIRouter(prefix="/api/events", tags=["events"])


# 分类（feature/price/content/negative/other）→ 对应的事件类型，用于按分类筛选
CATEGORY_TO_TYPES: dict[str, list[EventType]] = {}
for _et, _cat in EVENT_TYPE_CATEGORY.items():
    CATEGORY_TO_TYPES.setdefault(_cat, []).append(_et)


def _base_conditions(
    current_user: User,
    *,
    competitor_id: int | None = None,
    keyword: str | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = None,
) -> list:
    """除「分类/类型/优先级」之外的公共筛选条件（这三个是自身维度，分面计数时要排除）。"""
    conditions = [
        Competitor.user_id == current_user.id,
        Competitor.deleted_at.is_(None),  # 回收站里的竞品，其事件不出现在情报中心
    ]
    if competitor_id is not None:
        conditions.append(IntelligenceEvent.competitor_id == competitor_id)
    if days:
        conditions.append(
            IntelligenceEvent.created_at >= datetime.now(timezone.utc) - timedelta(days=days)
        )
    if start is not None:
        conditions.append(IntelligenceEvent.created_at >= start)
    if end is not None:
        conditions.append(IntelligenceEvent.created_at < end)
    if min_confidence is not None:
        conditions.append(IntelligenceEvent.confidence >= min_confidence)
    if max_confidence is not None:
        conditions.append(IntelligenceEvent.confidence <= max_confidence)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            or_(
                IntelligenceEvent.title.ilike(like),
                IntelligenceEvent.summary.ilike(like),
                Competitor.name.ilike(like),
            )
        )
    return conditions


def _type_conditions(category: str | None, event_type: EventType | None) -> list:
    """分类/类型筛选条件（不与其它维度冲突，可直接追加到 base 上）。"""
    if event_type is not None:
        return [IntelligenceEvent.event_type == event_type]
    if category is not None and category in CATEGORY_TO_TYPES:
        return [IntelligenceEvent.event_type.in_(CATEGORY_TO_TYPES[category])]
    return []


def _base_select():
    """事件 + 竞品名 + 官网 + 来源页名 + 来源页地址 + 竞品图标（一次查询取齐展示所需字段）。"""
    return (
        select(
            IntelligenceEvent,
            Competitor.name,
            Competitor.official_url,
            func.coalesce(MonitorSource.name, "未知页面"),
            func.coalesce(MonitorSource.url, ""),
            # 抓取时落库的真实图标；为空时响应层回退成官网 favicon
            Competitor.logo_url,
        )
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .outerjoin(MonitorSource, MonitorSource.id == IntelligenceEvent.source_id)
    )


def _to_record(row) -> EventRecordOut:
    event, competitor_name, official_url, source_name, _source_url, logo_url = row
    return EventRecordOut(
        id=event.id,
        competitor_id=event.competitor_id,
        competitor_name=competitor_name or "",
        competitor_domain=official_url or "",
        competitor_logo_url=logo_url or None,
        source_name=source_name or "未知页面",
        event_type=event.event_type,
        title=event.title,
        summary=event.summary or "",
        ai_analysis=event.ai_analysis or "",
        keywords=list(event.keywords or []),
        confidence=event.confidence or 0.0,
        priority_level=event.priority or "mid",
        created_at=event.created_at,
    )


@router.get("", response_model=EventListOut)
async def list_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    competitor_id: int | None = Query(default=None, alias='competitorId'),
    category: str | None = Query(default=None, alias='category'),
    event_type: EventType | None = Query(default=None, alias='eventType'),
    priority: str | None = Query(default=None, alias='priority'),
    min_confidence: int | None = Query(default=None, alias='minConfidence', ge=0, le=100),
    max_confidence: int | None = Query(default=None, alias='maxConfidence', ge=0, le=100),
    keyword: str | None = Query(default=None, alias='keyword'),
    start_date: date_cls | None = Query(default=None, alias='startDate'),
    end_date: date_cls | None = Query(default=None, alias='endDate'),
    days: int | None = Query(default=None, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """事件列表（只返回当前用户自己的竞品产生的事件）。

    筛选下推到后端并服务端分页：分类统计反映「除分类自身外」的全部筛选，
    优先级统计反映「除优先级自身外」的全部筛选，二者互不污染。
    """
    # 时间范围：优先 start/end（前端日期选择器/快捷预设），其次 days
    start = None
    end = None
    if start_date is not None:
        start = local_day_start_utc(start_date)
    if end_date is not None:
        end = local_day_end_utc(end_date)
    min_c = min_confidence / 100 if min_confidence is not None else None
    max_c = max_confidence / 100 if max_confidence is not None else None

    base = _base_conditions(
        current_user,
        competitor_id=competitor_id,
        keyword=keyword,
        min_confidence=min_c,
        max_confidence=max_c,
        start=start,
        end=end,
        days=days,
    )
    type_conds = _type_conditions(category, event_type)

    # 顶部分类统计：排除分类自身，但含优先级等其它筛选
    summary_stmt = (
        select(IntelligenceEvent.event_type, func.count())
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .where(*base)
        .group_by(IntelligenceEvent.event_type)
    )
    summary = EventSummaryOut()
    for et_value, count in (await db.execute(summary_stmt)).all():
        summary.total += count
        cat = EVENT_TYPE_CATEGORY.get(et_value)
        if cat:
            setattr(summary, cat, count)

    # 优先级分面计数：排除优先级自身，但含分类等其它筛选
    priority_stmt = (
        select(IntelligenceEvent.priority, func.count())
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .where(*(base + type_conds))
        .group_by(IntelligenceEvent.priority)
    )
    for prio, count in (await db.execute(priority_stmt)).all():
        if prio == "high":
            summary.high = count
        elif prio == "mid":
            summary.mid = count
        elif prio == "low":
            summary.low = count

    # 记录：叠加分类 + 优先级，并服务端分页
    record_conditions = base + type_conds
    if priority:
        priorities = [p for p in priority.split(",") if p]
        if priorities:
            record_conditions.append(IntelligenceEvent.priority.in_(priorities))

    total = (
        await db.execute(
            select(func.count())
            .select_from(IntelligenceEvent)
            .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
            .where(*record_conditions)
        )
    ).scalar() or 0

    records_stmt = (
        _base_select()
        .where(*record_conditions)
        .order_by(IntelligenceEvent.created_at.desc(), IntelligenceEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(records_stmt)).all()

    return EventListOut(
        summary=summary,
        total=total,
        records=[_to_record(row) for row in rows],
    )


@router.get("/related", response_model=list[EventRecordOut])
async def related_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    competitor_id: int = Query(..., alias='competitorId'),
    exclude_id: int | None = Query(default=None, alias='excludeId'),
    limit: int = Query(default=8, ge=1, le=30),
    days: int | None = Query(default=None, ge=1, le=365),
    category: str | None = Query(default=None),
):
    """某竞品的其它事件（详情抽屉"相关事件"用），只返回当前用户自己的竞品。
    可按时间范围(days)与类型(category)筛选。"""
    if category is not None and category not in CATEGORY_TO_TYPES:
        raise BusinessError(40000, "不支持的事件分类", 400)

    stmt = (
        _base_select()
        .where(
            Competitor.user_id == current_user.id,
            Competitor.deleted_at.is_(None),
            IntelligenceEvent.competitor_id == competitor_id,
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(IntelligenceEvent.id != exclude_id)
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(IntelligenceEvent.created_at >= cutoff)
    if category is not None:
        stmt = stmt.where(IntelligenceEvent.event_type.in_(CATEGORY_TO_TYPES[category]))
    stmt = stmt.order_by(
        IntelligenceEvent.created_at.desc(), IntelligenceEvent.id.desc()
    ).limit(limit)
    rows = (await db.execute(stmt)).all()
    return [_to_record(row) for row in rows]


@router.get("/daily-insight", response_model=DailyInsightOut)
async def daily_insight(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: int = Query(default=1, ge=1, le=7),
):
    """工作台「AI 今日洞察」：聚合近 N 天事件，由 LLM（无 Key 时规则兜底）总结成一段话。

    注意：必须声明在 `/{event_id}` 之前，否则 "daily-insight" 会被当成 event_id 解析。
    """
    return DailyInsightOut(**await build_daily_insight(db, current_user, days))


@router.get("/{event_id}/snapshots", response_model=list[SnapshotOut])
async def event_snapshots(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    event_id: int,
    limit: int = Query(default=10, ge=1, le=50),
):
    """该事件所属监控页面的历史快照（详情抽屉「查看历史快照」用）。"""
    event = (
        await db.execute(
            select(IntelligenceEvent)
            .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
            .where(
                IntelligenceEvent.id == event_id,
                Competitor.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if event is None:
        raise BusinessError(ERR_EVENT_NOT_FOUND, "事件不存在或已被删除，请刷新列表后重试", 404)
    if event.source_id is None:
        return []

    rows = (
        (
            await db.execute(
                select(PageSnapshot)
                .where(PageSnapshot.source_id == event.source_id)
                .order_by(PageSnapshot.crawled_at.desc(), PageSnapshot.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        SnapshotOut(
            id=snapshot.id,
            crawled_at=snapshot.crawled_at,
            available=bool(snapshot.raw_html_path),
            change_detected=snapshot.change_detected,
            is_current=snapshot.id == event.snapshot_id,
        )
        for snapshot in rows
    ]


@router.get("/{event_id}", response_model=EventDetailOut)
async def get_event(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    event_id: int,
):
    """事件详情：补上差异原文与来源地址。"""
    row = (
        await db.execute(
            _base_select().where(
                IntelligenceEvent.id == event_id,
                Competitor.user_id == current_user.id,
                Competitor.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise BusinessError(ERR_EVENT_NOT_FOUND, "事件不存在或已被删除，请刷新列表后重试", 404)

    event, _name, official_url, _source_name, source_url, _logo_url = row
    base = _to_record(row)
    return EventDetailOut(
        id=base.id,
        competitor_id=base.competitor_id,
        competitor_name=base.competitor_name,
        competitor_domain=base.competitor_domain,
        competitor_logo_url=base.competitor_logo_url,
        source_name=base.source_name,
        event_type=base.event_type,
        title=base.title,
        summary=base.summary,
        keywords=base.keywords,
        confidence=base.confidence,
        priority_level=base.priority_level,
        created_at=base.created_at,
        url=official_url,
        source_url=source_url or None,
        diff_detail=event.diff_detail,
    )
