"""周报生成：聚合一周事件 → 统计快照 + AI 叙述。

核心原则：**报表里的每一个数字都由数据库聚合得出，AI 只负责措辞**，
不允许模型生成任何统计数字，避免报告里出现编造的数据。
"""
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.display import icon_text, icon_tone
from app.core.event_types import EVENT_TYPE_LABELS, EVENT_TYPE_TAG_CLASS, EventType
from app.core.llm import get_llm_client
from app.core.timeutil import format_time, to_local
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.source import MonitorSource
from app.models.user import User
from app.models.weekly_report import ReportType, WeeklyReport

# 每类事件给一句固定的"可能影响"提示（规则兜底，真实 LLM 会写得更好）
_IMPACT_HINTS: dict[EventType, str] = {
    EventType.PRICE_CHANGE: "建议核对自身定价与套餐权益，评估是否需要跟进调价。",
    EventType.NEW_FEATURE: "建议评估该能力对自身产品路线图的影响，必要时加快对应功能节奏。",
    EventType.CONTENT_UPDATE: "属于内容层面的调整，关注其对外传播口径的变化即可。",
    EventType.PUBLIC_SENTIMENT: "涉及口碑与舆论，建议持续观察评分与用户反馈走向。",
    EventType.OTHER: "影响暂不明确，建议继续观察后续变化。",
}

_REPORT_WINDOW_DAYS = 7
_MAX_HIGHLIGHTS = 5
_MAX_RELATED_EVENTS = 8


def _window(weeks_ago: int = 0) -> tuple[date, date]:
    """返回 (起始日, 结束日)：**自然周**（周一 ~ 周日），可往前推 N 周。

    起始日固定落在周一，这样"第 N 周"与标题里的 ISO 周号、以及环比的上周区间都能对齐。
    本周尚未结束（如周五生成）时结束日取"今天"，避免把未来日期算进统计。
    """
    today = datetime.now().astimezone().date()
    monday = today - timedelta(days=today.weekday())  # weekday(): 周一=0
    start = monday - timedelta(days=_REPORT_WINDOW_DAYS * weeks_ago)
    week_end = start + timedelta(days=_REPORT_WINDOW_DAYS - 1)
    return start, min(week_end, today)


def _range_text(start: date, end: date) -> str:
    return f"{start.month}月{start.day}日 - {end.month}月{end.day}日"


def current_window() -> tuple[date, date]:
    """本周的 (周一, 今天)，用于手动生成"本周周报"。"""
    return _window(0)


def previous_window() -> tuple[date, date]:
    """上一个自然周的 (周一, 周日)，用于定时任务生成"上周周报"。"""
    return _window(1)


async def window_has_report(db: AsyncSession, user_id: int, start: date) -> bool:
    """该自然周是否已生成过报告——定时任务据此避免对同一周重复生成。

    用 `range_start`（周一）判断：它在一周内固定，不受"生成当天是周几"影响，
    否则同一周每天生成一份就会重复。
    """
    result = await db.execute(
        select(WeeklyReport.id)
        .where(WeeklyReport.user_id == user_id, WeeklyReport.range_start == start)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _day_start_utc(day: date) -> datetime:
    """把本地日期转成该日 00:00 对应的 UTC 时刻。"""
    return datetime(day.year, day.month, day.day).astimezone().astimezone(timezone.utc)


async def _load_events(
    db: AsyncSession, user_id: int, start: date, end: date
) -> list[IntelligenceEvent]:
    result = await db.execute(
        select(IntelligenceEvent)
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .where(
            Competitor.user_id == user_id,
            IntelligenceEvent.created_at >= _day_start_utc(start),
            IntelligenceEvent.created_at < _day_start_utc(end + timedelta(days=1)),
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


async def _count_competitors(db: AsyncSession, user_id: int) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(Competitor).where(Competitor.user_id == user_id)
        )
    ).scalar() or 0


async def _count_monitor_sources(db: AsyncSession, user_id: int) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(MonitorSource)
            .join(Competitor, Competitor.id == MonitorSource.competitor_id)
            .where(Competitor.user_id == user_id)
        )
    ).scalar() or 0


def _delta(current: int, previous: int) -> tuple[int, str]:
    """环比（百分数绝对值 + 方向）。上一期为 0 时按 100% 处理。"""
    if previous == 0:
        return (100 if current else 0), "up"
    rate = round((current - previous) / previous * 100)
    return abs(rate), ("up" if rate >= 0 else "down")


def _build_stats(current: list[IntelligenceEvent], previous: list[IntelligenceEvent]) -> list[dict]:
    def count_of(events: list[IntelligenceEvent], event_type: EventType) -> int:
        return sum(1 for e in events if e.event_type == event_type)

    involved_now = len({e.competitor_id for e in current})
    involved_prev = len({e.competitor_id for e in previous})
    high_now = sum(1 for e in current if e.priority == "high")
    high_prev = sum(1 for e in previous if e.priority == "high")

    feature_now = count_of(current, EventType.NEW_FEATURE)
    feature_prev = count_of(previous, EventType.NEW_FEATURE)
    price_now = count_of(current, EventType.PRICE_CHANGE)
    price_prev = count_of(previous, EventType.PRICE_CHANGE)

    rows = (
        ("events", "重要变化事件", len(current), len(previous)),
        ("competitors", "涉及竞品", involved_now, involved_prev),
        ("feature", "功能更新", feature_now, feature_prev),
        ("price", "价格变化", price_now, price_prev),
        ("impact", "高影响事件", high_now, high_prev),
    )
    stats = []
    for key, label, cur, prev in rows:
        delta, delta_type = _delta(cur, prev)
        stats.append(
            {"key": key, "label": label, "value": cur, "delta": delta, "deltaType": delta_type}
        )
    return stats


def _build_impact_trend(
    start: date,
    end: date,
    current: list[IntelligenceEvent],
    previous: list[IntelligenceEvent],
) -> dict:
    """本周 vs 上周的每日高影响事件数。

    天数按实际窗口算（周五生成本周周报时只有 5 天），避免尾部多出两天恒为 0 的柱子。
    """
    span = (end - start).days + 1
    days = [start + timedelta(days=i) for i in range(span)]
    current_daily = {day: 0 for day in days}
    previous_daily = {day: 0 for day in days}

    for event in current:
        if event.priority != "high":
            continue
        local = to_local(event.created_at)
        if local is not None and local.date() in current_daily:
            current_daily[local.date()] += 1

    prev_start = start - timedelta(days=_REPORT_WINDOW_DAYS)
    for event in previous:
        if event.priority != "high":
            continue
        local = to_local(event.created_at)
        if local is None:
            continue
        offset = (local.date() - prev_start).days
        if 0 <= offset < span:
            previous_daily[days[offset]] += 1

    return {
        "dates": [f"{day.month}/{day.day}" for day in days],
        "current": [current_daily[day] for day in days],
        "previous": [previous_daily[day] for day in days],
    }


def _event_line(event: IntelligenceEvent, names: dict[int, str]) -> str:
    """给 LLM 看的一行事件摘要：类型 ｜ 竞品 ｜ 标题。"""
    parts = [
        EVENT_TYPE_LABELS[event.event_type],
        names.get(event.competitor_id, ""),
        event.title,
    ]
    return "｜".join(part for part in parts if part)


def _build_highlight(event: IntelligenceEvent, others: list[str]) -> dict:
    impact_type = "high" if event.priority == "high" else "mid"
    points = []
    if event.summary:
        points.append(event.summary)
    points.append(f"可能影响：{_IMPACT_HINTS[event.event_type]}")
    return {
        "id": event.id,
        "title": event.title,
        "tag": EVENT_TYPE_LABELS[event.event_type],
        "tagType": EVENT_TYPE_TAG_CLASS[event.event_type],
        "impact": "高影响" if impact_type == "high" else "中影响",
        "impactType": impact_type,
        "points": points[:3],
        "affected": others[:3],
        "foundAt": format_time(event.created_at),
        "aiConfidence": int(round((event.confidence or 0) * 100)),
    }


def _build_ai_steps(
    source_count: int, event_count: int, high_count: int, end: date
) -> list[dict]:
    """AI 处理过程的四个步骤（时间以报告生成日为基准）。"""
    base = datetime(end.year, end.month, end.day, 6, 0).astimezone()
    steps = (
        ("数据采集", f"从 {source_count} 个监控页面抓取竞品公开信息。", 0),
        ("事件识别", f"从采集内容中识别出 {event_count} 条有效变化事件，并完成去重与分类。", 12),
        ("影响评估", f"结合历史数据评估影响等级，标记 {high_count} 条高影响事件。", 20),
        ("报告生成", "汇总核心摘要、重点变化与统计数据，生成本期竞品周报。", 30),
    )
    return [
        {"title": title, "desc": desc, "time": format_time(base + timedelta(minutes=minutes))}
        for title, desc, minutes in steps
    ]


async def generate_weekly_report(
    db: AsyncSession, user: User, *, weeks_ago: int = 0
) -> WeeklyReport:
    """生成一份周报并存库（未提交，由调用方 commit）。"""
    start, end = _window(weeks_ago)
    prev_start = start - timedelta(days=_REPORT_WINDOW_DAYS)
    prev_end = start - timedelta(days=1)

    current = await _load_events(db, user.id, start, end)
    previous = await _load_events(db, user.id, prev_start, prev_end)

    names = await _competitor_names(db, user.id)
    total_competitors = await _count_competitors(db, user.id)
    source_count = await _count_monitor_sources(db, user.id)

    per_competitor = Counter(event.competitor_id for event in current)
    involved_names = [names.get(cid, "") for cid, _ in per_competitor.most_common()]
    involved = {event.competitor_id for event in current}

    stats = _build_stats(current, previous)

    category_dist = [
        {"name": EVENT_TYPE_LABELS[event_type], "value": count}
        for event_type in EventType
        if (count := sum(1 for e in current if e.event_type == event_type))
    ]

    competitor_rank = [
        {"name": names.get(cid, f"竞品{cid}"), "value": count}
        for cid, count in per_competitor.most_common(5)
    ]

    # 高影响优先、其次按置信度
    ranked = sorted(
        current,
        key=lambda e: (0 if e.priority == "high" else 1, -(e.confidence or 0)),
    )

    highlights = [
        _build_highlight(
            event,
            [name for name in involved_names if name and name != names.get(event.competitor_id)],
        )
        for event in ranked[:_MAX_HIGHLIGHTS]
    ]

    related_events = [
        {
            "id": event.id,
            "brand": names.get(event.competitor_id, "未知竞品"),
            "title": event.title,
            "tag": EVENT_TYPE_LABELS[event.event_type],
            "tagType": EVENT_TYPE_TAG_CLASS[event.event_type],
            "time": format_time(event.created_at),
        }
        for event in current[:_MAX_RELATED_EVENTS]
    ]

    related_competitors = []
    for cid, count in per_competitor.most_common():
        name = names.get(cid, f"竞品{cid}")
        bg, color = icon_tone(name)
        related_competitors.append(
            {
                "name": name,
                "iconText": icon_text(name),
                "iconBg": bg,
                "iconColor": color,
                "changes": count,
            }
        )

    range_text = _range_text(start, end)
    high_count = sum(1 for event in current if event.priority == "high")

    # 按竞品聚合（供 AI 做跨事件归因，而不是逐条复述事件）
    competitor_lines: list[str] = []
    for cid, count in per_competitor.most_common():
        name = names.get(cid, f"竞品{cid}")
        type_counter = Counter(
            event.event_type for event in current if event.competitor_id == cid
        )
        type_text = "、".join(
            f"{EVENT_TYPE_LABELS[event_type]} {value}"
            for event_type, value in type_counter.most_common()
        )
        competitor_lines.append(f"{name}：{count} 条（{type_text}）")

    # AI 只写叙述：数字全部由上面的聚合结果提供
    narrative = await get_llm_client().weekly_report(
        range_text=range_text,
        total_events=len(current),
        involved_competitors=len(involved),
        # 只把有值的统计交给叙述，避免出现"功能更新 0 条"这类无意义措辞
        stats_lines=[f"{s['label']} {s['value']} 条" for s in stats if s["value"] > 0]
        or ["本期没有检测到变化"],
        competitor_lines=competitor_lines or ["本期没有检测到竞品变化"],
        event_lines=[_event_line(event, names) for event in ranked[:20]],
    )

    # 用起始日（周一）取 ISO 周号，保证标题与统计窗口一致
    year, week, _ = start.isocalendar()
    report = WeeklyReport(
        user_id=user.id,
        report_type=ReportType.WEEKLY,
        title=f"{year}年第{week}周 竞品周报",
        range_start=start,
        range_end=end,
        competitor_count=total_competitors,
        event_count=len(current),
        summary=narrative.summary,
        content=narrative.markdown,
        payload={
            "stats": stats,
            "highlights": highlights,
            "categoryDist": category_dist,
            "competitorRank": competitor_rank,
            "impactTrend": _build_impact_trend(start, end, current, previous),
            "relatedEvents": related_events,
            "relatedCompetitors": related_competitors,
            "aiSteps": _build_ai_steps(source_count, len(current), high_count, end),
        },
    )
    db.add(report)
    await db.flush()
    return report


def to_list_item(report: WeeklyReport) -> dict:
    """报告列表项（favorite 是前端本地状态，这里恒为 false）。"""
    type_label = "周报" if report.report_type == ReportType.WEEKLY else "月报"
    return {
        "id": report.id,
        "title": report.title,
        "type": report.report_type.value,
        "typeLabel": type_label,
        "range": _range_text(report.range_start, report.range_end),
        "competitors": report.competitor_count,
        "generatedAt": format_time(report.created_at, "%Y-%m-%d"),
        "favorite": False,
        "monthGroup": f"{report.range_end.year}年{report.range_end.month}月",
    }


def to_detail(report: WeeklyReport) -> dict:
    """报告详情：元信息 + AI 叙述 + 冻结的结构化报表内容。"""
    type_label = "周报" if report.report_type == ReportType.WEEKLY else "月报"
    return {
        "id": report.id,
        "title": report.title,
        "typeLabel": type_label,
        "rangeStart": report.range_start.isoformat(),
        "rangeEnd": report.range_end.isoformat(),
        "competitors": report.competitor_count,
        "favorite": False,
        "summary": report.summary or "",
        "content": report.content or "",
        **(report.payload or {}),
    }
