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
    '"summary": "一到两句话说明变化内容与可能影响，不超过 120 字", '
    '"keywords": ["关键词", "关键词"], '
    '"confidence": 0.0 到 1.0 之间的小数, '
    '"priority": "high|mid|low"}\n'
    "判断口径：涉及价格/套餐/计费 → price_change；新功能/新版本/上线 → new_feature；"
    "文案或文档内容调整 → content_update；评分口碑/用户评价/舆情争议 → public_sentiment；"
    "无法归类 → other。"
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

    return EventAnalysis(
        event_type=event_type,
        title=title[:120],
        summary=summary[:300],
        keywords=keywords,
        confidence=confidence,
        priority=priority,
        from_llm=True,
    )


class LLMClient:
    """LLM 调用入口：classify_and_summarize 之外的方法留给里程碑 8（趋势/周报）。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.llm_enabled and self.settings.llm_api_key)

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
            logger.warning("LLM 分析失败，已回退规则分析：%s: %s", type(exc).__name__, str(exc)[:160])
            return fallback

    def _build_prompt(self, competitor_name: str, source_label: str, url: str, diff_text: str) -> str:
        diff = (diff_text or "")[: self.settings.llm_max_diff_chars]
        return (
            f"竞品名称：{competitor_name}\n"
            f"页面类型：{source_label}\n"
            f"页面地址：{url}\n"
            f"快照差异：\n{diff}"
        )

    async def _chat_json(self, prompt: str) -> dict:
        base = self.settings.llm_base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.settings.llm_model,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        return json.loads(_strip_code_fence(content))


@lru_cache
def get_llm_client() -> LLMClient:
    """全局单例（配置只读一次）。"""
    return LLMClient()
