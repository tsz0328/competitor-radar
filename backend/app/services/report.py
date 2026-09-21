"""周报生成：聚合一周事件 → 统计快照 + AI 叙述。

核心原则：**报表里的每一个数字都由数据库聚合得出，AI 只负责措辞**，
不允许模型生成任何统计数字，避免报告里出现编造的数据。
"""
import html as html_lib
import io
import re
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape as xml_escape

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.display import clean_host, icon_text, icon_tone
from app.core.event_types import EVENT_TYPE_LABELS, EVENT_TYPE_TAG_CLASS, EventType
from app.core.llm import get_llm_client
from app.core.timeutil import app_timezone, format_time, local_day_start_utc, to_local
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.source import MonitorSource
from app.models.user import User
from app.models.weekly_report import ReportType, WeeklyReport
from app.services.settings import get_user_llm_config

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


def _month_bounds(month_start: date) -> date:
    """返回 month_start 所在自然月的最后一天。"""
    if month_start.month == 12:
        next_first = date(month_start.year + 1, 1, 1)
    else:
        next_first = date(month_start.year, month_start.month + 1, 1)
    return next_first - timedelta(days=1)


def _window(report_type: ReportType, weeks_ago: int = 0) -> tuple[date, date]:
    """返回 (起始日, 结束日)。

    周报：自然周（周一 ~ 今天），可往前推 N 周；
    月报：自然月（本月 1 号 ~ 今天）。
    结束日均取「今天」，避免把未来日期算进统计。
    """
    today = datetime.now(app_timezone()).date()
    if report_type == ReportType.MONTHLY:
        start = today.replace(day=1)
        return start, today
    monday = today - timedelta(days=today.weekday())  # weekday(): 周一=0
    start = monday - timedelta(days=_REPORT_WINDOW_DAYS * weeks_ago)
    week_end = start + timedelta(days=_REPORT_WINDOW_DAYS - 1)
    return start, min(week_end, today)


def _previous_window(report_type: ReportType, start: date) -> tuple[date, date]:
    """返回上一自然期（用于环比与趋势）：
    周报 = 上周一 ~ 上周日；月报 = 上一个完整自然月。
    """
    if report_type == ReportType.MONTHLY:
        prev_end = start - timedelta(days=1)  # 上月末
        prev_start = prev_end.replace(day=1)
        return prev_start, prev_end
    prev_start = start - timedelta(days=_REPORT_WINDOW_DAYS)
    return prev_start, start - timedelta(days=1)


def _range_text(start: date, end: date) -> str:
    return f"{start.month}月{start.day}日 - {end.month}月{end.day}日"


def period_label(report_type: ReportType = ReportType.WEEKLY) -> str:
    """环比对象描述：周报称「上周」，月报称「上月」。"""
    return "上月" if report_type == ReportType.MONTHLY else "上周"


def current_window(report_type: ReportType = ReportType.WEEKLY) -> tuple[date, date]:
    """当前自然期（周一/月初, 今天），用于手动生成本期报告。"""
    return _window(report_type, 0)


def previous_window(report_type: ReportType = ReportType.WEEKLY) -> tuple[date, date]:
    """上一个自然期（周一~周日 / 完整上月），用于定时任务生成上一期报告。

    定时任务触发时（每周日 / 每月末）`_window(report_type, 0)` 已恰好覆盖上一
    完整自然期，此处保留向后兼容的「上一期」语义。
    """
    return _window(report_type, 1)


def window_for(
    weeks_ago: int = 0, report_type: ReportType = ReportType.WEEKLY
) -> tuple[date, date]:
    """按周偏移量返回自然窗口。"""
    return _window(report_type, weeks_ago)


async def get_report_for_window(
    db: AsyncSession, user_id: int, start: date
) -> WeeklyReport | None:
    """取某账号在该 range_start 下最早的一份报告（历史兼容，旧逻辑催生）。"""
    result = await db.execute(
        select(WeeklyReport)
        .where(WeeklyReport.user_id == user_id, WeeklyReport.range_start == start)
        .order_by(WeeklyReport.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_existing_for_period(
    db: AsyncSession, user_id: int, report_type: ReportType, start: date
) -> list[WeeklyReport]:
    """取某账号在当前自然期（按 range_start + 类型锚定）下的全部已有报告。

    允许同一周期存多份，按 range_end 升序、id 升序返回，便于重叠判断。
    """
    result = await db.execute(
        select(WeeklyReport)
        .where(
            WeeklyReport.user_id == user_id,
            WeeklyReport.report_type == report_type,
            WeeklyReport.range_start == start,
            WeeklyReport.deleted_at.is_(None),
        )
        .order_by(WeeklyReport.range_end, WeeklyReport.id)
    )
    return list(result.scalars().all())


async def window_has_report(
    db: AsyncSession, user_id: int, start: date, report_type: ReportType = ReportType.WEEKLY
) -> bool:
    """该自然期是否已生成过报告——定时任务据此避免对同一期重复生成。

    用 `range_start`（周一 / 月初）判断：它在自然期内固定，不受「生成当天是周几/几号」
    影响，避免同一期每天生成一份才重复。
    """
    result = await db.execute(
        select(WeeklyReport.id)
        .where(
            WeeklyReport.user_id == user_id,
            WeeklyReport.report_type == report_type,
            WeeklyReport.range_start == start,
            WeeklyReport.deleted_at.is_(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def classify_overlap(
    existing: list[WeeklyReport], end: date
) -> tuple[WeeklyReport | None, str]:
    """把请求的结束日与同周期已有报告比对，给出处理建议。

    已有报告按 range_end 升序传入。返回 (目标报告或 None, 建议)：
    - ("none", "none")      本周期无已有报告 → 直接新建
    - (report, "covered")   已有报告跨度已>=本次 → 直接展示已有（本次是其子集）
    - (report, "duplicate") 已有报告跨度==本次 → 日期重复，提示覆盖/新建
    - (report, "expanded")  已有报告跨度<本次   → 本次跨度更大，提示覆盖/新建
    其中 duplicate / expanded 取覆盖跨度最大的那份作为「覆盖」目标。
    """
    if not existing:
        return None, "none"
    # 覆盖跨度最大的（range_end 最大、其次最新 id）
    target = max(existing, key=lambda r: (r.range_end, r.id))
    if target.range_end > end:
        return target, "covered"
    if target.range_end == end:
        return target, "duplicate"
    return target, "expanded"


def _day_start_utc(day: date) -> datetime:
    """把本地日期转成该日 00:00 对应的 UTC 时刻。"""
    return local_day_start_utc(day)


async def _load_events(
    db: AsyncSession, user_id: int, start: date, end: date
) -> list[IntelligenceEvent]:
    result = await db.execute(
        select(IntelligenceEvent)
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .where(
            Competitor.user_id == user_id,
            Competitor.deleted_at.is_(None),
            IntelligenceEvent.created_at >= _day_start_utc(start),
            IntelligenceEvent.created_at < _day_start_utc(end + timedelta(days=1)),
        )
        .order_by(IntelligenceEvent.created_at.desc(), IntelligenceEvent.id.desc())
    )
    return list(result.scalars().all())


async def _competitor_names(db: AsyncSession, user_id: int) -> dict[int, str]:
    rows = (
        await db.execute(
            select(Competitor.id, Competitor.name).where(
                Competitor.user_id == user_id, Competitor.deleted_at.is_(None)
            )
        )
    ).all()
    return {cid: (name or f"竞品{cid}") for cid, name in rows}


async def _competitor_domains(db: AsyncSession, user_id: int) -> dict[int, str]:
    """竞品 id → 官网主机名。

    周报里的竞品图标由前端按域名去取（favicon → apple-touch-icon → 后端解析
    → 首字母兜底），所以这里只要给出主机名，不用存图标地址。
    """
    rows = (
        await db.execute(
            select(Competitor.id, Competitor.official_url).where(
                Competitor.user_id == user_id, Competitor.deleted_at.is_(None)
            )
        )
    ).all()
    return {cid: clean_host(url or "") for cid, url in rows}


async def _count_competitors(db: AsyncSession, user_id: int) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Competitor)
            .where(Competitor.user_id == user_id, Competitor.deleted_at.is_(None))
        )
    ).scalar() or 0


async def _count_monitor_sources(db: AsyncSession, user_id: int) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(MonitorSource)
            .join(Competitor, Competitor.id == MonitorSource.competitor_id)
            .where(Competitor.user_id == user_id, Competitor.deleted_at.is_(None))
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
    report_type: ReportType,
    start: date,
    end: date,
    current: list[IntelligenceEvent],
    previous: list[IntelligenceEvent],
) -> dict:
    """本期 vs 上一自然期的高影响事件数。

    天数按实际窗口算（周五生成本周周报时只有 5 天；月中生成本月报时不足整月），
    避免尾部多出几天恒为 0 的柱子。
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

    prev_start = _previous_window(report_type, start)[0]
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
    base = datetime(end.year, end.month, end.day, 6, 0, tzinfo=app_timezone())
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


async def generate_report(
    db: AsyncSession,
    user: User,
    *,
    report_type: ReportType = ReportType.WEEKLY,
    weeks_ago: int = 0,
    overwrite: WeeklyReport | None = None,
) -> WeeklyReport:
    """生成一份周报/月报并存库（未提交，由调用方 commit）。

    - `overwrite` 为空 → 新建一份；
    - `overwrite` 非空 → 复用其 id/created_at，用新数据整体重写该报告（覆盖）。
    """
    start, end = _window(report_type, weeks_ago)
    prev_start, prev_end = _previous_window(report_type, start)

    current = await _load_events(db, user.id, start, end)
    previous = await _load_events(db, user.id, prev_start, prev_end)

    names = await _competitor_names(db, user.id)
    domains = await _competitor_domains(db, user.id)
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
                # 主机名交给前端取图标；取不到就用下面的首字母头像兜底
                "domain": domains.get(cid, ""),
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

    # AI 只写叙述：数字全部由上面的聚合结果提供；配置用报表归属用户自己的
    llm_cfg = await get_user_llm_config(db, user.id)
    narrative = await get_llm_client(llm_cfg).weekly_report(
        range_text=range_text,
        total_events=len(current),
        involved_competitors=len(involved),
        # 只把有值的统计交给叙述，避免出现"功能更新 0 条"这类无意义措辞
        stats_lines=[f"{s['label']} {s['value']} 条" for s in stats if s["value"] > 0]
        or ["本期没有检测到变化"],
        competitor_lines=competitor_lines or ["本期没有检测到竞品变化"],
        event_lines=[_event_line(event, names) for event in ranked[:20]],
    )

    if report_type == ReportType.WEEKLY:
        # 用起始日（周一）取 ISO 周号，保证标题与统计窗口一致
        year, week, _ = start.isocalendar()
        title = f"{year}年第{week}周 竞品周报"
    else:
        title = f"{start.year}年{start.month}月 竞品月报"

    if overwrite is not None:
        report = overwrite
        report.title = title
        report.range_start = start
        report.range_end = end
        report.competitor_count = total_competitors
        report.event_count = len(current)
        report.summary = narrative.summary
        report.content = narrative.markdown
        report.payload = {
            "stats": stats,
            "highlights": highlights,
            "categoryDist": category_dist,
            "competitorRank": competitor_rank,
            "impactTrend": _build_impact_trend(
                report_type, start, end, current, previous
            ),
            "relatedEvents": related_events,
            "relatedCompetitors": related_competitors,
            "aiSteps": _build_ai_steps(source_count, len(current), high_count, end),
        }
        return report

    report = WeeklyReport(
        user_id=user.id,
        report_type=report_type,
        title=title,
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
            "impactTrend": _build_impact_trend(
                report_type, start, end, current, previous
            ),
            "relatedEvents": related_events,
            "relatedCompetitors": related_competitors,
            "aiSteps": _build_ai_steps(source_count, len(current), high_count, end),
        },
    )
    db.add(report)
    await db.flush()
    return report


# 历史兼容：旧调用方用 generate_weekly_report 生成周报
generate_weekly_report = generate_report


def to_list_item(report: WeeklyReport) -> dict:
    """报告列表项。"""
    type_label = "周报" if report.report_type == ReportType.WEEKLY else "月报"
    return {
        "id": report.id,
        "title": report.title,
        "type": report.report_type.value,
        "typeLabel": type_label,
        "range": _range_text(report.range_start, report.range_end),
        "competitors": report.competitor_count,
        "generatedAt": format_time(report.created_at, "%Y-%m-%d"),
        "favorite": bool(report.favorite),
        "monthGroup": f"{report.range_end.year}年{report.range_end.month}月",
        "deletedAt": (
            format_time(report.deleted_at, "%Y-%m-%d %H:%M") if report.deleted_at else ""
        ),
    }


def to_detail(report: WeeklyReport) -> dict:
    """报告详情：元信息 + AI 叙述 + 冻结的结构化报表内容。"""
    type_label = "周报" if report.report_type == ReportType.WEEKLY else "月报"
    return {
        "id": report.id,
        "title": report.title,
        "type": report.report_type.value,
        "typeLabel": type_label,
        "rangeStart": report.range_start.isoformat(),
        "rangeEnd": report.range_end.isoformat(),
        "competitors": report.competitor_count,
        "favorite": bool(report.favorite),
        "summary": report.summary or "",
        "content": report.content or "",
        **(report.payload or {}),
    }


def _md_inline_html(text: str) -> str:
    """渲染行内 Markdown（输入须已 HTML 转义）：加粗 / 斜体 / 行内代码 / 链接。"""
    # 先处理行内代码与链接，避免其中的 *、_ 被误判为强调
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        r'<a href="\2" rel="noopener">\1</a>',
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def _markdown_to_html(md: str) -> str:
    """把 AI 正文（Markdown 子集）渲染成安全 HTML，用于打印/下载页展示。

    与网页端用 marked 的渲染不同，这里不引入前端依赖，用轻量正则足够覆盖
    常见正文结构（标题 / 列表 / 代码块 / 段落 / 分割线），并统一先 HTML 转义防注入。
    """
    lines = md.splitlines()
    n = len(lines)
    out: list[str] = []
    i = 0

    def esc_inline(t: str) -> str:
        return _md_inline_html(html_lib.escape(t))

    while i < n:
        raw = lines[i].rstrip()

        # 代码围栏
        if raw.lstrip().startswith("```"):
            i += 1
            code: list[str] = []
            while i < n and not lines[i].lstrip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # 跳过结束围栏
            out.append(f"<pre><code>{html_lib.escape(chr(10).join(code))}</code></pre>")
            continue

        # 标题
        heading = re.match(r"^(#{1,6})\s+(.*)$", raw)
        if heading:
            lvl = min(len(heading.group(1)), 6)
            out.append(f"<h{lvl}>{esc_inline(heading.group(2))}</h{lvl}>")
            i += 1
            continue

        # 无序列表
        if re.match(r"^\s*[-*+]\s+", raw):
            items: list[str] = []
            while i < n and (m := re.match(r"^\s*[-*+]\s+(.*)$", lines[i])):
                items.append(f"<li>{esc_inline(m.group(1))}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        # 有序列表
        if re.match(r"^\s*\d+\.\s+", raw):
            items: list[str] = []
            while i < n and (m := re.match(r"^\s*\d+\.\s+(.*)$", lines[i])):
                items.append(f"<li>{esc_inline(m.group(1))}</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue

        # 分割线
        if re.match(r"^\s*([-*_])\s*\1\s*\1\s*$", raw):
            out.append("<hr/>")
            i += 1
            continue

        # 普通段落：连续非空行合并，段内换行用 <br>
        para: list[str] = []
        while i < n and lines[i].strip():
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append("<p>" + "<br/>".join(esc_inline(p) for p in para) + "</p>")
        i += 1  # 跳过空行

    return "\n".join(part for part in out if part)


def to_print_html(report: WeeklyReport) -> str:
    """把周报渲染成独立可打印页面；浏览器可直接保存为 PDF。"""
    detail = to_detail(report)
    esc = html_lib.escape

    stats = "".join(
        f"""
        <div class="stat">
          <span>{esc(item['label'])}</span>
          <strong>{item['value']}</strong>
          <small>较{period_label(report.report_type)} {'↑' if item['deltaType'] == 'up' else '↓'} {item['delta']}%</small>
        </div>"""
        for item in detail["stats"]
    )
    highlights = "".join(
        f"""
        <li>
          <strong>{esc(item['title'])}</strong>
          <span class="tag">{esc(item['tag'])}</span>
          <span class="impact">{esc(item['impact'])}</span>
          <div>{esc(' · '.join(item['points']))}</div>
        </li>"""
        for item in detail["highlights"]
    )
    related = "".join(
        f'<li><span class="tag">{esc(item["tag"])}</span>'
        f'<strong>{esc(item["title"])}</strong>'
        f"<small>{esc(item['brand'])} · {esc(item['time'])}</small></li>"
        for item in detail["relatedEvents"]
    )
    competitors = "".join(
        f"<li><strong>{esc(item['name'])}</strong><span>{item['changes']} 条变化</span></li>"
        for item in detail["relatedCompetitors"]
    )
    categories = "".join(
        f"<li><span>{esc(item['name'])}</span><strong>{item['value']}</strong></li>"
        for item in detail["categoryDist"]
    )

    report_meta = (
        f"{esc(detail['rangeStart'])} ~ {esc(detail['rangeEnd'])} · "
        f"监控 {detail['competitors']} 个竞品"
    )

    content_html = _markdown_to_html(detail["content"]) if detail.get("content") else "本期报告暂无 AI 正文"


    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(detail['title'])}</title>
<style>
:root {{ color: #1f2937; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ max-width: 960px; margin: 0 auto; padding: 32px; background: #fff; }}
h1 {{ font-size: 26px; margin: 0 0 8px; }}
h2 {{ margin-top: 28px; font-size: 18px; border-bottom: 1px solid #dbe4f0; padding-bottom: 8px; }}
.meta {{ color: #667085; margin-bottom: 24px; }}
.summary {{ line-height: 1.8; }}
.stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-top: 12px; }}
.stat {{ padding: 14px; border: 1px solid #dbe4f0; border-radius: 8px; }}
.stat span, .stat small {{ display: block; color: #667085; font-size: 12px; }}
.stat strong {{ display: block; font-size: 24px; margin: 4px 0; }}
ul {{ padding-left: 20px; line-height: 1.75; }}
li {{ margin-bottom: 8px; }}
.tag {{
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  background: #eef2ff;
  color: #4f46e5;
  font-size: 12px;
  margin: 0 6px;
}}
.impact {{ color: #dc2626; font-size: 12px; }}
.content {{ line-height: 1.8; }}
.content p {{ margin: 0.8em 0; }}
.content h3, .content h4 {{ margin: 1.2em 0 0.4em; font-size: 16px; }}
.content ul, .content ol {{ padding-left: 22px; }}
.content li {{ margin-bottom: 6px; }}
.content code {{ padding: 1px 5px; border-radius: 4px; background: #f3f4f6; font-family: Consolas, Menlo, monospace; }}
.content pre {{ padding: 12px; overflow: auto; background: #f9fafb; border-radius: 6px; }}
.content pre code {{ padding: 0; background: transparent; }}
.content a {{ color: #4f46e5; }}
@media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>
<h1>{esc(detail['title'])}</h1>
<div class="meta">{report_meta}</div>
<h2>核心摘要</h2>
<div class="summary">{esc(detail['summary'])}</div>
<div class="stats">{stats}</div>
<h2>重点变化</h2>
<ul>{highlights or '<li>本期没有重点变化</li>'}</ul>
<h2>竞争动态</h2>
<ul>{competitors or '<li>本期暂无涉及竞品</li>'}</ul>
<h2>事件类型分布</h2>
<ul>{categories or '<li>本期没有检测到变化</li>'}</ul>
<h2>相关事件</h2>
<ul>{related or '<li>本期没有关联事件</li>'}</ul>
<h2>AI 正文</h2>
<div class="content">{content_html}</div>
</body>
</html>"""


def to_markdown(report: WeeklyReport) -> str:
    """把周报渲染为 Markdown，便于贴进文档或二次编辑。

    与 to_print_html 共用 to_detail 这一份结构化数据，保证两种导出口径一致。
    """
    d = to_detail(report)

    def esc(s: object) -> str:
        return (
            str(s or "")
            .replace("\\", "\\\\")
            .replace("*", "\\*")
            .replace("`", "\\`")
            .replace("_", "\\_")
            .replace("[", "\\[")
            .replace("]", "\\]")
        )

    lines: list[str] = [f"# {esc(d['title'])}", ""]
    lines.append(f"> 覆盖周期：{d['rangeStart']} ~ {d['rangeEnd']} · 监控 {d['competitors']} 个竞品")
    lines.append("")

    if d.get("summary"):
        lines += ["## 核心摘要", "", esc(d["summary"]), ""]

    if d.get("stats"):
        lines.append("## 关键指标")
        for it in d["stats"]:
            arrow = "↑" if it.get("deltaType") == "up" else "↓"
            lines.append(
                f"- **{esc(it['label'])}**：{it['value']}（较{period_label(report.report_type)} {arrow} {it['delta']}%）"
            )
        lines.append("")

    if d.get("highlights"):
        lines.append("## 重点变化")
        for it in d["highlights"]:
            points = "；".join(esc(p) for p in (it.get("points") or []))
            lines.append(
                f"- **{esc(it['title'])}** `{esc(it['tag'])}` {esc(it.get('impact', ''))}：{points}"
            )
        lines.append("")

    if d.get("relatedCompetitors"):
        lines.append("## 竞争动态")
        for it in d["relatedCompetitors"]:
            lines.append(f"- **{esc(it['name'])}**：{it['changes']} 条变化")
        lines.append("")

    if d.get("categoryDist"):
        lines.append("## 事件类型分布")
        for it in d["categoryDist"]:
            lines.append(f"- {esc(it['name'])}：{it['value']}")
        lines.append("")

    if d.get("relatedEvents"):
        lines.append("## 相关事件")
        for it in d["relatedEvents"]:
            lines.append(
                f"- `{esc(it['tag'])}` **{esc(it['title'])}** _{esc(it['brand'])} · {esc(it['time'])}_"
            )
        lines.append("")

    if d.get("content"):
        # content 本身就是 Markdown（AI 正文），原样输出，避免破坏其排版语法
        lines += ["## AI 正文", "", d["content"], ""]

    return "\n".join(lines)


# ---- Word（.docx）导出 ----------------------------------------------------
# 为不引入 python-docx 依赖，这里手写一个最小合法 docx（ZIP + 若干 OOXML 部件），
# Word / WPS 均可正常打开、编辑。w:sz 单位为「半磅」，如 28 = 14pt。

_DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

_DOCX_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOCX_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_DOCX_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Microsoft YaHei"/>
<w:sz w:val="21"/><w:szCs w:val="21"/>
</w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
</w:styles>"""


def _docx_para(
    text: str,
    *,
    size: int | None = None,
    bold: bool = False,
    color: str | None = None,
    indent: int = 0,
) -> str:
    """生成一个段落（单 run）；indent 单位为 twips（420 ≈ 2 字符缩进）。"""
    rpr = ""
    if bold:
        rpr += "<w:b/>"
    if color:
        rpr += f'<w:color w:val="{color}"/>'
    if size:
        rpr += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    run_rpr = f"<w:rPr>{rpr}</w:rPr>"
    ppr = f'<w:pPr><w:spacing w:after="120"/><w:ind w:left="{indent}"/></w:pPr>'
    return (
        f"<w:p>{ppr}<w:r>{run_rpr}"
        f'<w:t xml:space="preserve">{xml_escape(text)}</w:t></w:r></w:p>'
    )


def _md_inline(text: str) -> str:
    """去掉行内 Markdown 标记，得到适合 Word 的纯文本。"""
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)  # 链接 → 文本(地址)
    text = re.sub(r"\*\*|__|~~|`", "", text)
    return text.replace("\\*", "*").replace("\\_", "_").replace("\\`", "`")


def _docx_markdown_paragraphs(md: str) -> list[str]:
    """把 AI 正文（Markdown）转成 Word 段落：标题加粗放大、列表加项目符号。"""
    paras: list[str] = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            paras.append(
                _docx_para(_md_inline(heading.group(2)), size=max(24, 30 - level * 2), bold=True)
            )
            continue
        bullet = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if bullet:
            paras.append(_docx_para(f"• {_md_inline(bullet.group(1))}", indent=420))
            continue
        ordered = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if ordered:
            paras.append(
                _docx_para(f"{ordered.group(1)}. {_md_inline(ordered.group(2))}", indent=420)
            )
            continue
        paras.append(_docx_para(_md_inline(line)))
    return paras


def to_docx(report: WeeklyReport) -> bytes:
    """把周报渲染为 .docx 字节流，与 PDF/HTML/Markdown 共用 to_detail 口径。"""
    d = to_detail(report)

    paras: list[str] = [
        _docx_para(d["title"], size=36, bold=True),
        _docx_para(
            f"覆盖周期：{d['rangeStart']} ~ {d['rangeEnd']} · 监控 {d['competitors']} 个竞品",
            color="808080",
        ),
    ]

    if d.get("summary"):
        paras += [_docx_para("核心摘要", size=28, bold=True), _docx_para(d["summary"])]

    if d.get("stats"):
        paras.append(_docx_para("关键指标", size=28, bold=True))
        for it in d["stats"]:
            arrow = "↑" if it.get("deltaType") == "up" else "↓"
            paras.append(
                _docx_para(
                    f"• {it['label']}：{it['value']}（较{period_label(report.report_type)} {arrow} {it['delta']}%）",
                    indent=420,
                )
            )

    if d.get("highlights"):
        paras.append(_docx_para("重点变化", size=28, bold=True))
        for it in d["highlights"]:
            points = "；".join(it.get("points") or [])
            paras.append(
                _docx_para(
                    f"• {it['title']}（{it['tag']} · {it.get('impact', '')}）：{points}",
                    indent=420,
                )
            )

    if d.get("relatedCompetitors"):
        paras.append(_docx_para("竞争动态", size=28, bold=True))
        for it in d["relatedCompetitors"]:
            paras.append(_docx_para(f"• {it['name']}：{it['changes']} 条变化", indent=420))

    if d.get("categoryDist"):
        paras.append(_docx_para("事件类型分布", size=28, bold=True))
        for it in d["categoryDist"]:
            paras.append(_docx_para(f"• {it['name']}：{it['value']}", indent=420))

    if d.get("relatedEvents"):
        paras.append(_docx_para("相关事件", size=28, bold=True))
        for it in d["relatedEvents"]:
            paras.append(
                _docx_para(
                    f"• {it['title']}（{it['tag']}）— {it['brand']} · {it['time']}",
                    indent=420,
                )
            )

    if d.get("content"):
        paras.append(_docx_para("AI 正文", size=28, bold=True))
        paras += _docx_markdown_paragraphs(d["content"])

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{"".join(paras)}'
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'  # A4
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
        "</w:sectPr></w:body></w:document>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        zf.writestr("_rels/.rels", _DOCX_ROOT_RELS)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/_rels/document.xml.rels", _DOCX_DOC_RELS)
        zf.writestr("word/styles.xml", _DOCX_STYLES)
    return buf.getvalue()
