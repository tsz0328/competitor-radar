"""工作台「AI 今日洞察」。

分层原则与趋势/周报一致：所有统计数字由数据库聚合得出，AI 只负责把这些事实写成一段话；
未配置 Key 时走规则兜底。结果按（用户, 天数）做短 TTL 缓存，避免工作台每次刷新都调一次 LLM。
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_types import EVENT_TYPE_LABELS
from app.core.llm import get_llm_client
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.user import User
from app.services.settings import get_user_llm_config

# 洞察的复用时长：TTL 内直接返回上次结果，超过则重新聚合/生成
_CACHE_TTL = timedelta(minutes=10)
# (user_id, days) -> (生成时刻, 响应体)
_cache: dict[tuple[int, int], tuple[datetime, dict]] = {}


def _period_text(days: int) -> str:
    return "过去 24 小时" if days <= 1 else f"过去 {days} 天"


async def _load_events(
    db: AsyncSession, user_id: int, since: datetime
) -> list[IntelligenceEvent]:
    result = await db.execute(
        select(IntelligenceEvent)
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .where(
            Competitor.user_id == user_id,
            IntelligenceEvent.created_at >= since,
        )
        .order_by(IntelligenceEvent.created_at.desc(), IntelligenceEvent.id.desc())
    )
    return list(result.scalars().all())


async def _competitor_names(db: AsyncSession, user_id: int) -> dict[int, str]:
    rows = (
        await db.execute(
            select(Competitor.id, Competitor.name).where(Competitor.user_id == user_id)
        )
    ).all()
    return {cid: (name or f"竞品{cid}") for cid, name in rows}


async def build_daily_insight(db: AsyncSession, user: User, days: int = 1) -> dict:
    """聚合近 N 天（默认 1 天）的事件，产出工作台用的「AI 今日洞察」。"""
    key = (user.id, days)
    now = datetime.now(timezone.utc)
    cached = _cache.get(key)
    if cached is not None and now - cached[0] < _CACHE_TTL:
        return cached[1]

    events = await _load_events(db, user.id, now - timedelta(days=days))
    names = await _competitor_names(db, user.id)

    total = len(events)
    high_count = sum(1 for event in events if event.priority == "high")
    involved = len({event.competitor_id for event in events})

    type_counter = Counter(event.event_type for event in events)
    type_lines = [
        f"{EVENT_TYPE_LABELS[event_type]} {count} 条"
        for event_type, count in type_counter.most_common()
    ]
    # 高优先级优先（sorted 稳定，同优先级保持时间倒序）
    ranked = sorted(events, key=lambda event: 0 if event.priority == "high" else 1)
    event_lines = [
        f"{names.get(event.competitor_id, '')}｜"
        f"{EVENT_TYPE_LABELS[event.event_type]}｜{event.title}"
        for event in ranked[:20]
    ]

    # 用当前账号自己的配置（开关 / 模型 / Key）
    llm_cfg = await get_user_llm_config(db, user.id)
    narrative = await get_llm_client(llm_cfg).daily_insight(
        period_text=_period_text(days),
        total_events=total,
        high_count=high_count,
        involved_competitors=involved,
        type_lines=type_lines or ["本期没有检测到变化"],
        event_lines=event_lines,
    )

    payload = {
        "days": days,
        "period_text": _period_text(days),
        "event_count": total,
        "high_count": high_count,
        "competitor_count": involved,
        "summary": narrative.summary,
        "highlights": narrative.highlights,
        "from_llm": narrative.from_llm,
        "generated_at": now,
    }
    _cache[key] = (now, payload)
    return payload
