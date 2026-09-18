"""LLM 统一调用层（里程碑 7）。

- 配了 Key 且 LLM_ENABLED=true → 走 OpenAI 兼容的 /chat/completions
- 否则 → 规则驱动的 Mock，保证没有 Key 也能端到端跑通整条链路
- 任何异常都退回 Mock：LLM 不可用绝不能打断抓取主流程

安全：日志只记录异常类型与摘要，绝不记录 API Key；Prompt 里不含 Key。
"""
import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache

import httpx

from app.core.config import get_settings
from app.core.event_types import EVENT_TYPE_LABELS, EventType
from app.core.runtime_config import get_llm_config
from app.core.source_registry import SourceType, get_source_config

logger = logging.getLogger(__name__)

VALID_PRIORITIES = ("high", "mid", "low")

# 规则分类用的关键词线索（命中即判定，简单但可解释）
_PRICE_HINTS = (
    "价格", "定价", "费用", "套餐", "计费", "订阅", "涨价", "降价", "折扣",
    "￥", "$", "元/", "/月", "/年", "price", "pricing", "per month", "per year", "usd",
)
_FEATURE_HINTS = (
    "新增", "上线", "发布", "推出", "支持", "优化", "重构", "灰度", "内测",
    "release", "changelog", "launch", "beta", "new feature", "version",
)
_SENTIMENT_HINTS = (
    "评分", "评价", "评论", "差评", "投诉", "反馈", "舆情", "争议",
    "review", "rating", "sentiment", "complaint",
)

_SYSTEM_PROMPT = (
    "你是一名竞品情报分析师。用户会给你某个竞品页面的两次快照差异（unified diff，"
    "+ 表示新增行，- 表示删除行）。请判断这次变化属于哪一类，并用中文写出人能一眼看懂的结论。\n"
    "只输出一个 JSON 对象，不要输出解释文字，也不要包裹代码块标记，格式：\n"
    '{"event_type": "new_feature|price_change|content_update|public_sentiment|other", '
    '"title": "一句话标题，不超过 40 字", '
    '"summary": "一到两句话客观说明页面实际发生了什么变化，不超过 120 字（只写事实，不要推断）", '
    '"analysis": "基于上述变化，推测其可能意味着什么、对自身的潜在影响，一到两句话不超过 120 字'
    '（这是 AI 的推断，不是页面事实，务必用\'可能/或/倾向于\'等措辞，不要当作确定结论）", '
    '"keywords": ["关键词", "关键词"], '
    '"confidence": 0.0 到 1.0 之间的小数, '
    '"priority": "high|mid|low"}\n'
    "判断口径：涉及价格/套餐/计费 → price_change；新功能/新版本/上线 → new_feature；"
    "文案或文档内容调整 → content_update；评分口碑/用户评价/舆情争议 → public_sentiment；"
    "无法归类 → other。`summary` 与 `analysis` 必须区分：前者是页面上可见的事实，"
    "后者是你对它的解读。"
)

_TOKEN_PATTERNS = (
    r"v?\d+\.\d+(?:\.\d+)?",  # 版本号
    r"[￥$]\s?\d[\d,.]*",  # 价格
    r"\d+\s?(?:元|美元|刀)",  # 中文价格
    r"\b[A-Z][A-Za-z0-9.+-]{2,}\b",  # 英文专有名词
)


@dataclass
class EventAnalysis:
    """一次分析结论（字段与 intelligence_events 对齐）。"""

    event_type: EventType
    title: str
    summary: str
    # AI 对该变化的推断/影响判断（明确为"分析"而非"事实"）
    analysis: str = ""
    keywords: list[str] = field(default_factory=list)
    confidence: float = 0.6
    priority: str = "mid"
    from_llm: bool = False


def split_changed_lines(diff_text: str) -> tuple[list[str], list[str]]:
    """从 unified diff 里取出真正的新增行与删除行。"""
    added: list[str] = []
    removed: list[str] = []
    for line in (diff_text or "").splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            text = line[1:].strip()
            if text:
                added.append(text)
        elif line.startswith("-"):
            text = line[1:].strip()
            if text:
                removed.append(text)
    return added, removed


def count_changed_lines(diff_text: str) -> int:
    added, removed = split_changed_lines(diff_text)
    return len(added) + len(removed)


# 高价值信号：命中即视为"值得生成事件"，不再受变更行数阈值约束。
# 单行改动也可能极重要——「专业版 ￥99 → ￥129」只有一行，
# 但它恰恰是竞品雷达最该捕捉的情报，不能因为行数少就丢掉。
_SIGNAL_PATTERNS = (
    # 价格符号 + 数字。必须同时覆盖全角 ￥(U+FFE5) 与半角 ¥(U+00A5)：
    # 正文提取会做 NFKC 归一化，源页面里的 ￥ 到这一步已经变成 ¥。
    r"[￥¥$€£]\s?\d",
    r"\d+\s?(?:元|美元|刀)",  # 中文计价
    r"\d+\s?/\s?(?:月|年|季)",  # 计价周期，如 129/月（要求斜杠，避免把"2026 年"误判成价格）
    r"v?\d+\.\d+(?:\.\d+)?",  # 版本号
    r"新增|上线|发布|推出|支持|下线|停售|涨价|降价|免费|公测|内测|调整",  # 变更动词
)


def is_significant_change(diff_text: str, min_lines: int) -> bool:
    """这次变化值不值得交给 LLM 分析。

    两条通路任一成立即可：
    1. 变更行数达到阈值（覆盖"整段改写"这类大规模变化）；
    2. 变更内容命中高价值信号（价格 / 版本号 / 变更动词），覆盖"单行但关键"的变化。

    只看 +/- 行，不看 diff 里带出来的上下文行，避免被未改动的正文误触发。
    """
    if count_changed_lines(diff_text) >= min_lines:
        return True
    added, removed = split_changed_lines(diff_text)
    changed_text = "\n".join(added + removed)
    return any(re.search(pattern, changed_text) for pattern in _SIGNAL_PATTERNS)


def _classify_by_rules(source_type: SourceType, text: str) -> EventType:
    """关键词优先、页面类型兜底，得到可解释的分类结果。"""
    lowered = text.lower()
    if source_type == SourceType.APP_STORE or any(h in lowered for h in _SENTIMENT_HINTS):
        return EventType.PUBLIC_SENTIMENT
    if any(h in lowered for h in _PRICE_HINTS):
        return EventType.PRICE_CHANGE
    if any(h in lowered for h in _FEATURE_HINTS):
        return EventType.NEW_FEATURE
    if source_type in (
        SourceType.HOMEPAGE,
        SourceType.PRICING,
        SourceType.CHANGELOG,
        SourceType.BLOG,
        SourceType.DOCS,
        SourceType.STATUS,
        SourceType.RSS,
    ):
        return EventType.CONTENT_UPDATE
    return EventType.OTHER


def _extract_keywords(text: str, fallback: list[str]) -> list[str]:
    found: list[str] = []
    for pattern in _TOKEN_PATTERNS:
        for token in re.findall(pattern, text or ""):
            token = token.strip()
            if token and token not in found:
                found.append(token)
    return (found or fallback)[:4]


def _mock_analysis_by_type(event_type: EventType) -> str:
    """规则兜底的"影响推断"：固定文案，明确是推断而非事实。"""
    return {
        EventType.PRICE_CHANGE: "价格变动可能直接影响用户使用成本与竞品间性价比对比，建议评估是否需跟进调价。",
        EventType.NEW_FEATURE: "新能力可能改变用户侧体验或能力边界，建议评估对自有产品路线图的冲击。",
        EventType.PUBLIC_SENTIMENT: "口碑波动可能放大或削弱品牌信任，建议结合评分与评论走向持续观察。",
        EventType.CONTENT_UPDATE: "内容调整通常反映对外口径或重点的变化，影响相对有限，可关注传播口径。",
        EventType.OTHER: "变化性质暂不明确，建议结合上下文继续观察。",
    }.get(event_type, "变化性质暂不明确，建议结合上下文继续观察。")


def _mock_analyze(
    *,
    competitor_name: str,
    source_type: SourceType,
    source_label: str,
    diff_text: str,
) -> EventAnalysis:
    """无 Key 时的规则兜底：产出结构完整、可解释的分析结论。"""
    added, removed = split_changed_lines(diff_text)
    changed = len(added) + len(removed)
    headline = (added or removed or [""])[0]
    event_type = _classify_by_rules(source_type, "\n".join(added[:10]) or diff_text)
    type_label = EVENT_TYPE_LABELS[event_type]

    title = f"{competitor_name} {type_label}"
    if headline:
        title = f"{title}：{headline[:36]}"
    summary = (
        f"对比上次快照，{source_label}新增 {len(added)} 行、移除 {len(removed)} 行。"
        f"首处变化：{headline or '（无正文变化）'}"
    )[:300]
    keywords = _extract_keywords("\n".join(added[:10]), [source_label, type_label])

    if event_type in (EventType.PRICE_CHANGE, EventType.PUBLIC_SENTIMENT) or changed >= 15:
        priority = "high"
    elif changed >= 5:
        priority = "mid"
    else:
        priority = "low"

    return EventAnalysis(
        event_type=event_type,
        title=title[:120],
        summary=summary,
        analysis=_mock_analysis_by_type(event_type),
        keywords=keywords,
        confidence=round(min(0.92, 0.60 + changed * 0.02), 2),
        priority=priority,
        from_llm=False,
    )


def _strip_code_fence(content: str) -> str:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _normalize(raw: dict, fallback: EventAnalysis) -> EventAnalysis:
    """把模型返回的内容逐字段校验，非法值一律退回规则结果。"""
    try:
        event_type = EventType(str(raw.get("event_type", "")).strip())
    except ValueError:
        event_type = fallback.event_type

    priority = str(raw.get("priority", "")).strip().lower()
    if priority not in VALID_PRIORITIES:
        priority = fallback.priority

    try:
        confidence = float(raw.get("confidence", fallback.confidence))
    except (TypeError, ValueError):
        confidence = fallback.confidence
    confidence = min(1.0, max(0.0, round(confidence, 2)))

    keywords = raw.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        keywords = fallback.keywords
    keywords = [str(k).strip() for k in keywords if str(k).strip()][:6]

    title = str(raw.get("title") or "").strip() or fallback.title
    summary = str(raw.get("summary") or "").strip() or fallback.summary
    analysis = str(raw.get("analysis") or "").strip() or fallback.analysis

    return EventAnalysis(
        event_type=event_type,
        title=title[:120],
        summary=summary[:300],
        analysis=analysis[:300],
        keywords=keywords,
        confidence=confidence,
        priority=priority,
        from_llm=True,
    )


_TREND_PROMPT = (
    "你是一名竞品情报分析师。用户会给你某个竞品最近一段时间的每日事件数量与若干条事件摘要，"
    "请判断该竞品近期的变化节奏。\n"
    "只输出一个 JSON 对象，不要解释文字，也不要包裹代码块标记，格式：\n"
    '{"direction": "rising|stable|declining", '
    '"summary": "两三句话说明节奏与最值得关注的点，不超过 150 字", '
    '"highlights": ["要点1", "要点2", "要点3"]}\n'
    "判断口径：后半段明显多于前半段 → rising；明显少于 → declining；否则 stable。"
)

_REPORT_PROMPT = (
    "你是一名竞品情报分析师。用户会给你一个时间段内的竞品事件统计、按竞品聚合的明细与关键事件清单，"
    "请写一份简短的中文竞品周报。\n"
    "只输出一个 JSON 对象，不要解释文字，也不要包裹代码块标记，格式：\n"
    '{"summary": "本周核心摘要，3-4 句，不超过 220 字", '
    '"markdown": "周报正文，Markdown 格式，必须包含 本周概览 / 重点变化 / 竞争动态 / 建议关注 四个小节"}\n'
    "写作要求：\n"
    "1. 「竞争动态」要跨事件归纳，而不是复述事件：按竞品说明它本周的动作方向"
    "（偏产品能力、偏价格、偏内容运营）、节奏快慢，以及竞品之间的差异；\n"
    "2. 「重点变化」只挑最重要的几条，说清变化本身与可能影响，不要罗列全部事件；\n"
    "3. 「建议关注」给出可执行的下一步（跟进什么、观察什么）。\n"
    "严格要求：只能使用用户给出的数字与事实，绝对不要编造任何统计数字或事件。"
)

_DAILY_PROMPT = (
    "你是一名竞品情报分析师。用户会给你最近一段时间（通常是过去一天）内所有竞品的情报事件统计与清单，"
    "请用中文总结这段时间整体上发生了什么、有什么值得注意。\n"
    "只输出一个 JSON 对象，不要解释文字，也不要包裹代码块标记，格式：\n"
    '{"summary": "总体洞察，三四句话，不超过 200 字", '
    '"highlights": ["要点1", "要点2", "要点3"]}\n'
    "判断口径：把多条事件放在一起看，指出变化的共性方向（如价格、产品能力、内容），"
    "并点明最值得关注的地方。"
    "严格要求：只能使用用户给出的数字与事实，绝对不要编造任何统计数字或事件。"
)

_BRAND_PROMPT = (
    "你是竞品资料助手。用户会给一个产品/公司名称，请给出它的**官方网站域名**与**所属分类**。\n"
    "只输出一个 JSON 对象，不要解释文字，也不要包裹代码块标记，格式：\n"
    '{"domain": "官方网站域名，如 notion.so；不确定就留空字符串", '
    '"category": "从用户给出的分类列表里选最贴切的一个"}\n'
    "注意：domain 只填域名，不要带 http:// 或 https://、不要带路径与 www.；"
    "绝对不要编造不存在的域名，不确定就留空。"
)


@dataclass
class TrendJudgment:
    """趋势判断结论。"""

    direction: str  # rising | stable | declining
    summary: str
    highlights: list[str] = field(default_factory=list)
    from_llm: bool = False


@dataclass
class ReportNarrative:
    """周报的叙述部分（数字由调用方提供，AI 只写文字）。"""

    summary: str
    markdown: str
    from_llm: bool = False


@dataclass
class DailyInsightNarrative:
    """工作台「AI 今日洞察」的叙述部分（数字由调用方提供，AI 只写文字）。"""

    summary: str
    highlights: list[str] = field(default_factory=list)
    from_llm: bool = False


@dataclass
class BrandProfile:
    """竞品名称 → 官网域名 / 分类的推断结果。"""

    domain: str = ""
    category: str = ""
    from_llm: bool = False


def _compare_halves(daily_counts: list[int]) -> str:
    """按"后半段 vs 前半段"的日均变化判断方向。"""
    if not daily_counts:
        return "stable"
    mid = len(daily_counts) // 2 or 1
    first = sum(daily_counts[:mid]) / mid
    rest = daily_counts[mid:] or [0]
    second = sum(rest) / len(rest)
    if first == 0 and second == 0:
        return "stable"
    if first == 0:
        return "rising"
    ratio = (second - first) / first
    if ratio >= 0.2:
        return "rising"
    if ratio <= -0.2:
        return "declining"
    return "stable"


def _mock_trend_judgment(
    *,
    competitor_name: str,
    period_days: int,
    daily_counts: list[int],
    highlights: list[str],
) -> TrendJudgment:
    direction = _compare_halves(daily_counts)
    total = sum(daily_counts)
    active_days = sum(1 for count in daily_counts if count)
    pace = {
        "rising": "变化节奏在加快",
        "declining": "变化节奏在放缓",
        "stable": "变化节奏基本平稳",
    }[direction]
    summary = (
        f"近 {period_days} 天，{competitor_name} 共检测到 {total} 条变化，"
        f"有变化的天数 {active_days} 天，{pace}。"
    )
    if highlights:
        summary += f"最值得关注：{highlights[0]}"
    return TrendJudgment(
        direction=direction,
        summary=summary[:300],
        highlights=highlights[:4],
        from_llm=False,
    )


def _mock_report_narrative(
    *,
    range_text: str,
    total_events: int,
    involved_competitors: int,
    stats_lines: list[str],
    competitor_lines: list[str],
) -> ReportNarrative:
    summary = (
        f"{range_text}，共监控 {involved_competitors} 个竞品，检测到 {total_events} 条变化事件。"
        f"{'；'.join(stats_lines[:3])}。整体来看变化集中在功能迭代与内容更新，"
        "建议优先跟进高优先级事件的后续动作。"
    )
    markdown = "\n".join(
        [
            "## 本周概览",
            "",
            f"- 统计周期：{range_text}",
            f"- 涉及竞品：{involved_competitors} 个",
            f"- 变化事件：{total_events} 条",
            "",
            "## 重点变化",
            "",
            *([f"- {line}" for line in stats_lines] or ["- 本期没有检测到变化。"]),
            "",
            "## 竞争动态",
            "",
            *(
                [f"- {line}" for line in competitor_lines]
                or ["- 本期没有检测到竞品变化。"]
            ),
            "",
            "## 建议关注",
            "",
            "- 优先跟进高优先级事件（价格调整、舆论动态），评估是否需要响应。",
            "- 对连续多周活跃的竞品，保持更高频率的检查。",
        ]
    )
    return ReportNarrative(summary=summary[:400], markdown=markdown, from_llm=False)


def _mock_daily_insight(
    *,
    period_text: str,
    total_events: int,
    high_count: int,
    involved_competitors: int,
    type_lines: list[str],
    event_lines: list[str],
) -> DailyInsightNarrative:
    """规则兜底的今日洞察：只用调用方给的真实聚合数字组织语言。"""
    if total_events <= 0:
        return DailyInsightNarrative(
            summary=f"{period_text}内没有检测到新的竞品变化，各监控页面与上一版一致。",
            highlights=[],
            from_llm=False,
        )
    focus = "、".join(line.split(" ")[0] for line in type_lines[:2]) or "功能与内容调整"
    summary = (
        f"{period_text}内共监测到 {total_events} 条竞品变化，涉及 {involved_competitors} 个竞品，"
        f"其中 {high_count} 条为高优先级；变化主要集中在{focus}。"
    )
    if event_lines:
        summary += f"最值得关注：{event_lines[0]}。"
    return DailyInsightNarrative(
        summary=summary[:300],
        highlights=event_lines[:3],
        from_llm=False,
    )


def _normalize_trend(raw: dict, fallback: TrendJudgment) -> TrendJudgment:
    direction = str(raw.get("direction", "")).strip().lower()
    if direction not in ("rising", "stable", "declining"):
        direction = fallback.direction
    highlights = raw.get("highlights")
    if not isinstance(highlights, list) or not highlights:
        highlights = fallback.highlights
    highlights = [str(h).strip() for h in highlights if str(h).strip()][:5]
    summary = str(raw.get("summary") or "").strip() or fallback.summary
    return TrendJudgment(
        direction=direction,
        summary=summary[:300],
        highlights=highlights,
        from_llm=True,
    )


def _normalize_report(raw: dict, fallback: ReportNarrative) -> ReportNarrative:
    summary = str(raw.get("summary") or "").strip() or fallback.summary
    markdown = str(raw.get("markdown") or "").strip() or fallback.markdown
    return ReportNarrative(summary=summary[:400], markdown=markdown, from_llm=True)


def _normalize_daily(raw: dict, fallback: DailyInsightNarrative) -> DailyInsightNarrative:
    summary = str(raw.get("summary") or "").strip() or fallback.summary
    highlights = raw.get("highlights")
    if not isinstance(highlights, list) or not highlights:
        highlights = fallback.highlights
    highlights = [str(h).strip() for h in highlights if str(h).strip()][:4]
    return DailyInsightNarrative(summary=summary[:400], highlights=highlights, from_llm=True)


class LLMClient:
    """LLM 调用入口：事件分类摘要、趋势判断、周报撰写。

    统一约定：AI 只负责"把事实翻译成人话"，所有数字统计都由调用方从数据库算好传进来。
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        # 读运行时配置：设置页保存后无需重启即可生效
        return get_llm_config().ready

    async def classify_and_summarize(
        self,
        *,
        competitor_name: str,
        source_type: SourceType,
        url: str,
        diff_text: str,
    ) -> EventAnalysis:
        """把「页面变了什么」翻译成「这是什么类型的事件、意味着什么」。"""
        source_label = get_source_config(source_type).label
        fallback = _mock_analyze(
            competitor_name=competitor_name,
            source_type=source_type,
            source_label=source_label,
            diff_text=diff_text,
        )
        if not self.enabled:
            return fallback

        try:
            raw = await self._chat_json(
                self._build_prompt(competitor_name, source_label, url, diff_text)
            )
            return _normalize(raw, fallback)
        except Exception as exc:  # noqa: BLE001 - LLM 不可用必须降级而非中断
            logger.warning(
                "LLM 分析失败，已回退规则分析：%s: %s",
                type(exc).__name__,
                str(exc)[:160],
            )
            return fallback

    async def trend_judgment(
        self,
        *,
        competitor_name: str,
        period_days: int,
        daily_counts: list[int],
        highlights: list[str],
    ) -> TrendJudgment:
        """判断竞品近期的变化节奏；无 Key 时按"前后半段对比"给出规则结论。"""
        fallback = _mock_trend_judgment(
            competitor_name=competitor_name,
            period_days=period_days,
            daily_counts=daily_counts,
            highlights=highlights,
        )
        if not self.enabled:
            return fallback

        prompt = (
            f"竞品：{competitor_name}\n"
            f"统计周期：{period_days} 天\n"
            f"每日事件数（从早到晚）：{daily_counts}\n"
            "近期事件摘要：\n" + "\n".join(f"- {item}" for item in highlights[:12])
        )
        try:
            raw = await self._chat_json(prompt, system=_TREND_PROMPT)
            return _normalize_trend(raw, fallback)
        except Exception as exc:  # noqa: BLE001 - 不可用则降级
            logger.warning(
                "LLM 趋势判断失败，已回退规则结论：%s: %s", type(exc).__name__, str(exc)[:160]
            )
            return fallback

    async def weekly_report(
        self,
        *,
        range_text: str,
        total_events: int,
        involved_competitors: int,
        stats_lines: list[str],
        competitor_lines: list[str],
        event_lines: list[str],
    ) -> ReportNarrative:
        """撰写周报的叙述部分：数字由调用方给定，AI 只负责措辞、不得编造。"""
        fallback = _mock_report_narrative(
            range_text=range_text,
            total_events=total_events,
            involved_competitors=involved_competitors,
            stats_lines=stats_lines,
            competitor_lines=competitor_lines,
        )
        if not self.enabled:
            return fallback

        prompt = (
            f"统计周期：{range_text}\n"
            f"事件总数：{total_events}\n"
            f"涉及竞品数：{involved_competitors}\n"
            "统计明细：\n" + "\n".join(f"- {line}" for line in stats_lines)
            + "\n按竞品聚合：\n" + "\n".join(f"- {line}" for line in competitor_lines)
            + "\n关键事件清单：\n" + "\n".join(f"- {line}" for line in event_lines[:20])
        )
        try:
            raw = await self._chat_json(prompt, system=_REPORT_PROMPT)
            return _normalize_report(raw, fallback)
        except Exception as exc:  # noqa: BLE001 - 不可用则降级
            logger.warning(
                "LLM 周报生成失败，已回退规则文案：%s: %s", type(exc).__name__, str(exc)[:160]
            )
            return fallback

    async def daily_insight(
        self,
        *,
        period_text: str,
        total_events: int,
        high_count: int,
        involved_competitors: int,
        type_lines: list[str],
        event_lines: list[str],
    ) -> DailyInsightNarrative:
        """把「一段时间内所有竞品的变化」总结成一段洞察；无 Key 时走规则兜底。"""
        fallback = _mock_daily_insight(
            period_text=period_text,
            total_events=total_events,
            high_count=high_count,
            involved_competitors=involved_competitors,
            type_lines=type_lines,
            event_lines=event_lines,
        )
        # 没有任何事件时直接给规则结论，省一次无意义的模型调用
        if not self.enabled or total_events <= 0:
            return fallback

        prompt = (
            f"时间范围：{period_text}\n"
            f"变化事件总数：{total_events}\n"
            f"涉及竞品数：{involved_competitors}\n"
            f"高优先级事件数：{high_count}\n"
            "按类型的分布：\n" + "\n".join(f"- {line}" for line in type_lines)
            + "\n事件清单：\n" + "\n".join(f"- {line}" for line in event_lines[:20])
        )
        try:
            raw = await self._chat_json(prompt, system=_DAILY_PROMPT)
            return _normalize_daily(raw, fallback)
        except Exception as exc:  # noqa: BLE001 - 不可用则降级
            logger.warning(
                "LLM 今日洞察生成失败，已回退规则文案：%s: %s",
                type(exc).__name__,
                str(exc)[:160],
            )
            return fallback

    async def brand_profile(self, name: str, categories: list[str]) -> BrandProfile | None:
        """根据竞品名称猜官网域名与分类。

        没配 Key / 调用失败时返回 None，交给调用方走"域名探测"兜底，
        绝不让预填功能依赖 LLM 可用性。
        """
        if not self.enabled:
            return None
        cats = "、".join(categories) if categories else (
            "SaaS工具、AI产品、协作办公、开发者工具、设计工具、其他"
        )
        prompt = f"竞品名称：{name}\n可选分类：{cats}"
        try:
            raw = await self._chat_json(prompt, system=_BRAND_PROMPT)
        except Exception as exc:  # noqa: BLE001 - 不可用则返回 None 交给兜底
            logger.warning(
                "LLM 品牌推断失败：%s: %s", type(exc).__name__, str(exc)[:160]
            )
            return None

        domain = str(raw.get("domain") or "").strip().lower()
        domain = re.sub(r"^https?://", "", domain).split("/")[0].removeprefix("www.")
        category = str(raw.get("category") or "").strip()
        return BrandProfile(domain=domain, category=category, from_llm=True)

    def _build_prompt(
        self,
        competitor_name: str,
        source_label: str,
        url: str,
        diff_text: str,
    ) -> str:
        diff = (diff_text or "")[: self.settings.llm_max_diff_chars]
        return (
            f"竞品名称：{competitor_name}\n"
            f"页面类型：{source_label}\n"
            f"页面地址：{url}\n"
            f"快照差异：\n{diff}"
        )

    async def _chat_json(self, prompt: str, system: str = _SYSTEM_PROMPT) -> dict:
        cfg = get_llm_config()
        base = cfg.base_url.rstrip("/")
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": cfg.model,
            "temperature": 0.2,
            "max_tokens": 1500,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        # 尽量让模型直接吐合法 JSON，省去后续解析失败时降级成 Mock 的概率。
        # 部分 OpenAI 兼容端点不支持 response_format 会返回 400/422，捕获后去掉该字段重试一次。
        payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            try:
                response = await client.post(
                    f"{base}/chat/completions", headers=headers, json=payload
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if (
                    payload.get("response_format") is not None
                    and exc.response.status_code in (400, 422)
                ):
                    payload.pop("response_format", None)
                    response = await client.post(
                        f"{base}/chat/completions", headers=headers, json=payload
                    )
                    response.raise_for_status()
                else:
                    raise
            content = response.json()["choices"][0]["message"]["content"]
        return json.loads(_strip_code_fence(content))


@lru_cache
def get_llm_client() -> LLMClient:
    """全局单例（配置只读一次）。"""
    client = LLMClient()
    if client.enabled:
        cfg = get_llm_config()
        logger.info("LLM 已启用真实模型：%s @ %s", cfg.model, cfg.base_url)
    else:
        logger.info("LLM 未配置 Key，使用规则 Mock 兜底（可在「设置」页配置模型）")
    return client
