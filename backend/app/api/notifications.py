"""通知中心接口：消费后端"已推送的高优事件"（priority=high）。

已读态服务端落库（event_reads），多端一致；表里没有记录即未读（懒标记）。
SSE（/stream）在高优事件产生时由 analyzer 广播，实时刷新未读数。
"""

# cspell:ignore outerjoin
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_sse
from app.core.config import get_settings
from app.core.database import get_db
from app.core.event_bus import bus
from app.core.exceptions import ERR_EVENT_NOT_FOUND, BusinessError
from app.core.timeutil import app_timezone, local_day_start_utc
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.notification import EventRead
from app.models.source import MonitorSource
from app.models.user import User
from app.schemas.event import EventRecordOut
from app.schemas.notification import (
    NotificationItemOut,
    NotificationListOut,
    ReadAckOut,
    UnreadCountOut,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
settings = get_settings()


def _notification_cutoff_utc() -> datetime:
    """业务时区下，包含今天在内的最近 N 个自然日的起点。"""
    today = datetime.now(app_timezone()).date()
    first_day = today - timedelta(days=max(0, settings.notification_window_days - 1))
    return local_day_start_utc(first_day)


def _cutoff_for(days: int | None) -> datetime | None:
    """把前端传的 days 参数换算成时间窗起点（UTC）。

    - days=None → 用系统设置 notification_window_days（铃铛/默认行为）
    - days<=0   → 不限时间窗（通知中心「归档」视图，返回全部高优事件）
    - days=N>0  → 最近 N 个自然日
    """
    if days is None:
        return _notification_cutoff_utc()
    if days <= 0:
        return None
    today = datetime.now(app_timezone()).date()
    first_day = today - timedelta(days=max(0, days - 1))
    return local_day_start_utc(first_day)


def _high_conditions(current_user: User, cutoff: datetime | None = None) -> list:
    """当前用户时间窗内的高优事件。cutoff=None 表示不限时间（归档）。"""
    conds = [
        Competitor.user_id == current_user.id,
        Competitor.deleted_at.is_(None),  # 回收站里的竞品，其高优事件不计入通知
        IntelligenceEvent.priority == "high",
    ]
    if cutoff is not None:
        conds.append(IntelligenceEvent.created_at >= cutoff)
    return conds




def _to_notification(row) -> NotificationItemOut:
    event, name, official_url, source_name, _source_url, is_read = row
    base = EventRecordOut(
        id=event.id,
        competitor_id=event.competitor_id,
        competitor_name=name or "",
        competitor_domain=official_url or "",
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
    return NotificationItemOut(**base.model_dump(), is_read=bool(is_read))


def _build_stmt(current_user: User):
    return (
        select(
            IntelligenceEvent,
            Competitor.name,
            Competitor.official_url,
            func.coalesce(MonitorSource.name, "未知页面"),
            func.coalesce(MonitorSource.url, ""),
            func.coalesce(EventRead.is_read, False).label("is_read"),
        )
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .outerjoin(MonitorSource, MonitorSource.id == IntelligenceEvent.source_id)
        .outerjoin(
            EventRead,
            (EventRead.event_id == IntelligenceEvent.id)
            & (EventRead.user_id == current_user.id),
        )
    )


async def _count_unread(
    db: AsyncSession, current_user: User, cutoff: datetime | None = None
) -> int:
    """当前用户高优事件中的未读数（总高优数 - 已读记录数）。cutoff 控制时间窗。"""
    conditions = _high_conditions(current_user, cutoff)
    total = (
        await db.execute(
            select(func.count())
            .select_from(IntelligenceEvent)
            .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
            .where(*conditions)
        )
    ).scalar() or 0
    read_count = (
        await db.execute(
            select(func.count())
            .select_from(EventRead)
            .join(IntelligenceEvent, IntelligenceEvent.id == EventRead.event_id)
            .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
            .where(
                EventRead.user_id == current_user.id,
                EventRead.is_read.is_(True),
                *conditions,
            )
        )
    ).scalar() or 0
    return max(total - read_count, 0)


async def _query(
    db: AsyncSession,
    current_user: User,
    limit: int,
    offset: int,
    cutoff: datetime | None = None,
) -> NotificationListOut:
    conditions = _high_conditions(current_user, cutoff)
    rows = (
        await db.execute(
            _build_stmt(current_user)
            .where(*conditions)
            .order_by(IntelligenceEvent.created_at.desc(), IntelligenceEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    records = [_to_notification(r) for r in rows]

    total = (
        await db.execute(
            select(func.count())
            .select_from(IntelligenceEvent)
            .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
            .where(*conditions)
        )
    ).scalar() or 0

    unread = await _count_unread(db, current_user)
    return NotificationListOut(records=records, total=total, unread=unread)


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    days: int | None = Query(
        default=None,
        ge=0,
        le=3650,
        description="时间窗天数：省略=系统设置(默认90天)；0=不限(归档)；N=最近N天",
    ),
):
    """当前用户的高优事件通知（多端已读态一致）。days=0 返回全部历史高优事件。"""
    return await _query(db, current_user, limit, offset, _cutoff_for(days))


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """轮询专用：只回未读数，避免每次拉整页。"""
    return UnreadCountOut(unread=await _count_unread(db, current_user, _notification_cutoff_utc()))


@router.get("/stream")
async def stream(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_sse)],
):
    """SSE：当前用户未读数变化时实时推送（高优事件产生时由 analyzer 广播）。

    浏览器用 EventSource 连接；连接即推当前未读数，之后每次广播重算并推送。
    30s 心跳保活，避免代理/浏览器因静默断开（EventSource 会自动重连）。
    """
    async def event_gen():
        q = await bus.subscribe(current_user.id)
        try:
            yield _sse(await _count_unread(db, current_user, _notification_cutoff_utc()))
            while True:
                try:
                    await asyncio.wait_for(q.get(), timeout=30)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(await _count_unread(db, current_user, _notification_cutoff_utc()))
        finally:
            await bus.unsubscribe(current_user.id, q)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _sse(unread: int) -> str:
    return f"data: {json.dumps({'unread': unread}, ensure_ascii=False)}\n\n"



async def _mark_read(db: AsyncSession, user_id: int, event_id: int) -> None:
    """懒标记已读：先确认事件属于该用户，再幂等地写已读记录。"""
    owned = await db.scalar(
        select(IntelligenceEvent.id)
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .where(
            IntelligenceEvent.id == event_id,
            Competitor.user_id == user_id,
            Competitor.deleted_at.is_(None),
        )
    )
    if owned is None:
        raise BusinessError(ERR_EVENT_NOT_FOUND, "事件不存在或已被删除，请刷新列表后重试", 404)
    await _write_read_rows(db, user_id, [event_id])

async def _mark_read_batch(db: AsyncSession, user_id: int, event_ids: list[int]) -> None:
    """批量已读：对并发的懒插入冲突进行重试。"""
    await _write_read_rows(db, user_id, event_ids)

async def _write_read_rows(
    db: AsyncSession, user_id: int, event_ids: list[int]
) -> None:
    """对同一 (user_id, event_id) 用查后写 + 唯一约束兜底，避免并发重复插入。"""
    event_ids = list(dict.fromkeys([eid for eid in event_ids if eid]))
    if not event_ids:
        return
    for _attempt in range(2):
        rows = (
            await db.execute(
                select(EventRead).where(
                    EventRead.user_id == user_id, EventRead.event_id.in_(event_ids)
                )
            )
        ).scalars().all()
        by_id = {row.event_id: row for row in rows}
        now = datetime.now(timezone.utc)
        for eid in event_ids:
            row = by_id.get(eid)
            if row is not None:
                row.is_read = True
                row.read_at = now
            else:
                db.add(EventRead(user_id=user_id, event_id=eid, is_read=True, read_at=now))
        try:
            await db.commit()
            return
        except IntegrityError:
            await db.rollback()
    raise RuntimeError("已读状态写入发生并发冲突")




@router.post("/{event_id}/read", response_model=ReadAckOut)
async def mark_read(
    event_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """标记单条已读（懒插入已读记录），返回未读数 + 事件 id。"""
    await _mark_read(db, current_user.id, event_id)
    return ReadAckOut(unread=await _count_unread(db, current_user), read_id=event_id)


@router.post("/read-all", response_model=ReadAckOut)
async def mark_all_read(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: int | None = Query(
        default=None,
        ge=0,
        le=3650,
        description="时间窗天数：省略=系统设置(默认90天)；0=不限(归档)；N=最近N天",
    ),
):
    """全部已读：为当前用户对指定时间窗内的高优事件批量插/更新已读记录（单次事务）。"""
    high_ids = (
        await db.execute(
            select(IntelligenceEvent.id)
            .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
            .where(*_high_conditions(current_user, _cutoff_for(days)))
        )
    ).scalars().all()
    await _mark_read_batch(db, current_user.id, list(high_ids))
    return ReadAckOut(unread=await _count_unread(db, current_user, _cutoff_for(days)), read_id=None)
