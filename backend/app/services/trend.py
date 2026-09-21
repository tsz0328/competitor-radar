"""趋势分析：把历史事件聚合成时间序列，并给出节奏判断。

分层：序列与统计全部由数据库算出；只有"结论话术"来自 LLM（无 Key 时走规则）。
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_types import EVENT_TYPE_LABELS, EventType
from app.core.llm import get_llm_client
from app.core.timeutil import to_local
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.trend import TrendDirection, TrendInsight
from app.schemas.trend import TrendPointOut
from app.services.settings import get_user_llm_config

# 五类事件各自一条折线，与前端 TrendChart 一一对应
_SERIES_EVENT_TYPES = {
    EventType.NEW_FEATURE: "feature",
    EventType.PRICE_CHANGE: "price",
    EventType.PUBLIC_SENTIMENT: "sentiment",
    EventType.CONTENT_UPDATE: "content",
    EventType.OTHER: "other",
}

# 洞察的复用时长：超过该时长再次访问才重新生成，避免反复调用 LLM
_INSIGHT_TTL_HOURS = 24


def _is_fresh(moment: datetime | None) -> bool:
    local = to_local(moment)
    if local is None:
        return False
    return (datetime.now().astimezone() - local) < timedelta(hours=_INSIGHT_TTL_HOURS)


async def build_series(
    db: AsyncSession,
    user_id: int,
    days: int,
    competitor_id: int | None = None,
) -> list[TrendPointOut]:
    """按天聚合事件数量；窗口内没有事件的天补 0，保证折线连续。"""
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=days - 1)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(IntelligenceEvent.created_at, IntelligenceEvent.event_type)
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .where(
            Competitor.user_id == user_id,
            Competitor.deleted_at.is_(None),
            IntelligenceEvent.created_at >= since,
        )
    )
    if competitor_id is not None:
        stmt = stmt.where(IntelligenceEvent.competitor_id == competitor_id)

    buckets: dict[str, dict[str, int]] = {}
    for created_at, event_type in (await db.execute(stmt)).all():
        series = _SERIES_EVENT_TYPES.get(event_type)
        local = to_local(created_at)
        if series is None or local is None:
            continue
        bucket = buckets.setdefault(local.strftime("%Y-%m-%d"), {})
        bucket[series] = bucket.get(series, 0) + 1

    points: list[TrendPointOut] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = buckets.get(day.strftime("%Y-%m-%d"), {})
        points.append(
            TrendPointOut(
                date=f"{day.month}/{day.day}",
                feature=row.get("feature", 0),
                price=row.get("price", 0),
                sentiment=row.get("sentiment", 0),
                content=row.get("content", 0),
                other=row.get("other", 0),
            )
        )
    return points


async def build_daily_totals(db: AsyncSession, user_id: int, days: int) -> list[dict]:
    """全部竞品汇总的每日变化总数（工作台趋势图 + 点击钻取用）。"""
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=days - 1)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(IntelligenceEvent.created_at)
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .where(
            Competitor.user_id == user_id,
            Competitor.deleted_at.is_(None),
            IntelligenceEvent.created_at >= since,
        )
    )
    buckets: dict[str, int] = {}
    for (created_at,) in (await db.execute(stmt)).all():
        local = to_local(created_at)
        if local is None:
            continue
        key = local.strftime("%Y-%m-%d")
        buckets[key] = buckets.get(key, 0) + 1

    points: list[dict] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        iso = day.strftime("%Y-%m-%d")
        points.append(
            {
                "date": f"{day.month}/{day.day}",
                "date_iso": iso,
                "count": buckets.get(iso, 0),
            }
        )
    return points


async def build_compare_series(
    db: AsyncSession, user_id: int, days: int
) -> list[dict]:
    """按竞品聚合每日变化总数，供「多竞品对比」折线使用。

    与 `build_series` 的区别：这里按竞品分组、且统计全部类型的事件（对比看的是总活跃度）。
    """
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=days - 1)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    competitors = (
        await db.execute(
            select(Competitor.id, Competitor.name)
            .where(Competitor.user_id == user_id, Competitor.deleted_at.is_(None))
            .order_by(Competitor.name)
        )
    ).all()

    stmt = (
        select(IntelligenceEvent.competitor_id, IntelligenceEvent.created_at)
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .where(
            Competitor.user_id == user_id,
            Competitor.deleted_at.is_(None),
            IntelligenceEvent.created_at >= since,
        )
    )
    buckets: dict[int, dict[str, int]] = {}
    for competitor_id, created_at in (await db.execute(stmt)).all():
        local = to_local(created_at)
        if local is None:
            continue
        bucket = buckets.setdefault(competitor_id, {})
        key = local.strftime("%Y-%m-%d")
        bucket[key] = bucket.get(key, 0) + 1

    series: list[dict] = []
    for competitor_id, name in competitors:
        bucket = buckets.get(competitor_id, {})
        points = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            points.append(
                {
                    "date": f"{day.month}/{day.day}",
                    "count": bucket.get(day.strftime("%Y-%m-%d"), 0),
                }
            )
        series.append(
            {
                "competitor_id": competitor_id,
                "competitor_name": name or f"竞品{competitor_id}",
                "points": points,
            }
        )
    return series


async def _events_since(
    db: AsyncSession, competitor_id: int, since: datetime
) -> list[IntelligenceEvent]:
    result = await db.execute(
        select(IntelligenceEvent)
        .where(
            IntelligenceEvent.competitor_id == competitor_id,
            IntelligenceEvent.created_at >= since,
        )
        .order_by(IntelligenceEvent.created_at.desc(), IntelligenceEvent.id.desc())
    )
    return list(result.scalars().all())


def _daily_weighted_strength(events: list[IntelligenceEvent], period_days: int) -> list[float]:
    """把窗口内事件按 类型×优先级 加权，聚合成每日强度序列（从早到晚，缺口补 0）。"""
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=period_days - 1)
    daily = {start + timedelta(days=i): 0.0 for i in range(period_days)}
    for event in events:
        local = to_local(event.created_at)
        if local is None or local.date() not in daily:
            continue
        weight = _EVENT_TYPE_WEIGHTS.get(event.event_type, 1.0) * _PRIORITY_WEIGHTS.get(
            event.priority or "mid", 1.0)
        daily[local.date()] += weight
    return [round(value, 1) for value in daily.values()]


async def generate_insight(
    db: AsyncSession,
    competitor: Competitor,
    period_days: int = 30,
) -> TrendInsight:
    """聚合该竞品近 N 天的事件，产出一条趋势洞察（未提交，由调用方 commit）。"""
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    events = await _events_since(db, competitor.id, since)

    # 节奏判断看"加权后的每日强度"：同样的事件数，价格/高优先级事件占比越高越"活跃"；
    # coverage_days 仍用原始事件数统计，避免加权把有事件的 0 天误判成没活动。
    weighted = _daily_weighted_strength(events, period_days)
    active_days = sum(1 for value in weighted if value > 0)

    highlights = [
        f"{EVENT_TYPE_LABELS[event.event_type]}：{event.title}" for event in events[:4]
    ]
    # 用竞品归属用户自己的配置（开关 / 模型 / Key）
    llm_cfg = await get_user_llm_config(db, competitor.user_id)
    judgment = await get_llm_client(llm_cfg).trend_judgment(
        competitor_name=competitor.name,
        period_days=period_days,
        daily_counts=weighted,
        highlights=highlights,
        raw_event_count=len(events),
    )

    insight = TrendInsight(
        competitor_id=competitor.id,
        period_days=period_days,
        direction=TrendDirection(judgment.direction),
        summary=judgment.summary,
        highlights=judgment.highlights,
        event_count=len(events),
        high_impact_count=sum(1 for event in events if event.priority == "high"),
        coverage_days=active_days,
    )
    db.add(insight)
    await db.flush()
    return insight


async def get_or_generate_insight(
    db: AsyncSession,
    competitor: Competitor,
    period_days: int = 30,
) -> tuple[TrendInsight, bool]:
    """取最新洞察；没有或已过期（超过 TTL）就重新生成。

    返回 (洞察, 是否新生成)——调用方据此决定是否需要 commit。
    """
    latest = (
        await db.execute(
            select(TrendInsight)
            .where(
                TrendInsight.competitor_id == competitor.id,
                TrendInsight.period_days == period_days,
            )
            .order_by(TrendInsight.created_at.desc(), TrendInsight.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if latest is not None and _is_fresh(latest.created_at):
        return latest, False

    return await generate_insight(db, competitor, period_days), True
# 趋势判断的"重要性权重"：同样一天里，一次价格调整比多条文案更新更值得关注。
# 权重 = 事件类型权重 × 优先级系数，聚合成"每日加权强度"后再交给前后半段对比，
# 让"1 次 price_change(high)"的信号强度 >= "3 次 content_update(mid)"。
_EVENT_TYPE_WEIGHTS: dict[EventType, float] = {
    EventType.PRICE_CHANGE: 3.0,
    EventType.NEW_FEATURE: 2.0,
    EventType.PUBLIC_SENTIMENT: 2.0,
    EventType.CONTENT_UPDATE: 1.0,
    EventType.OTHER: 0.5,
}
_PRIORITY_WEIGHTS: dict[str, float] = {"high": 2.0, "mid": 1.0, "low": 0.5}
