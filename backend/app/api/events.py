"""情报事件接口（里程碑 7）。

约定：`GET /api/events` 返回「顶部统计 + 事件记录」，
统计口径不受 eventType 影响（否则按类型筛选后其它分类会全变 0），
但同样受竞品与时间范围约束。
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.event_types import EVENT_TYPE_CATEGORY, EventType
from app.core.exceptions import ERR_EVENT_NOT_FOUND, BusinessError
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.source import MonitorSource
from app.models.user import User
from app.schemas.event import EventDetailOut, EventListOut, EventRecordOut, EventSummaryOut

router = APIRouter(prefix="/api/events", tags=["events"])


def _conditions(
    current_user: User,
    competitor_id: int | None,
    days: int | None,
    event_type: EventType | None = None,
) -> list:
    conditions = [Competitor.user_id == current_user.id]
    if competitor_id is not None:
        conditions.append(IntelligenceEvent.competitor_id == competitor_id)
    if days:
        conditions.append(
            IntelligenceEvent.created_at >= datetime.now(timezone.utc) - timedelta(days=days)
        )
    if event_type is not None:
        conditions.append(IntelligenceEvent.event_type == event_type)
    return conditions


def _base_select():
    """事件 + 竞品名 + 官网 + 来源页名 + 来源页地址（一次查询取齐展示所需字段）。"""
    return (
        select(
            IntelligenceEvent,
            Competitor.name,
            Competitor.official_url,
            func.coalesce(MonitorSource.name, "未知页面"),
            func.coalesce(MonitorSource.url, ""),
        )
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .outerjoin(MonitorSource, MonitorSource.id == IntelligenceEvent.source_id)
    )


def _to_record(row) -> EventRecordOut:
    event, competitor_name, official_url, source_name, _source_url = row
    return EventRecordOut(
        id=event.id,
        competitor_id=event.competitor_id,
        competitor_name=competitor_name or "",
        competitor_domain=official_url or "",
        source_name=source_name or "未知页面",
        event_type=event.event_type,
        title=event.title,
        summary=event.summary or "",
        keywords=list(event.keywords or []),
        confidence=event.confidence or 0.0,
        priority_level=event.priority or "mid",
        created_at=event.created_at,
    )


@router.get("", response_model=EventListOut)
async def list_events(
    competitor_id: int | None = Query(default=None, alias="competitorId"),
    event_type: EventType | None = Query(default=None, alias="eventType"),
    days: int | None = Query(default=None, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """事件列表（只返回当前用户自己的竞品产生的事件）。"""
    summary_stmt = (
        select(IntelligenceEvent.event_type, func.count())
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .where(*_conditions(current_user, competitor_id, days))
        .group_by(IntelligenceEvent.event_type)
    )
    summary = EventSummaryOut()
    for event_type_value, count in (await db.execute(summary_stmt)).all():
        summary.total += count
        category = EVENT_TYPE_CATEGORY.get(event_type_value)
        if category:
            setattr(summary, category, count)

    records_stmt = (
        _base_select()
        .where(*_conditions(current_user, competitor_id, days, event_type))
        .order_by(IntelligenceEvent.created_at.desc(), IntelligenceEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(records_stmt)).all()

    return EventListOut(summary=summary, records=[_to_record(row) for row in rows])


@router.get("/{event_id}", response_model=EventDetailOut)
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """事件详情：补上差异原文与来源地址。"""
    row = (
        await db.execute(
            _base_select().where(
                IntelligenceEvent.id == event_id,
                Competitor.user_id == current_user.id,
            )
        )
    ).first()
    if row is None:
        raise BusinessError(ERR_EVENT_NOT_FOUND, "事件不存在", 404)

    event, _name, official_url, _source_name, source_url = row
    base = _to_record(row)
    return EventDetailOut(
        id=base.id,
        competitor_id=base.competitor_id,
        competitor_name=base.competitor_name,
        competitor_domain=base.competitor_domain,
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
