"""情报事件的响应模型。

前端事件流页面需要的是"可直接渲染"的数据（标签、配色、相对时间、置信度百分比…），
所以这里和 CompetitorOut 一样，把展示字段都用 computed_field 预制好，
前端不再重复拼装。
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field
from pydantic.alias_generators import to_camel

from app.core.display import clean_host, icon_text, icon_tone
from app.core.event_types import (
    EVENT_TYPE_CATEGORY,
    EVENT_TYPE_LABELS,
    EVENT_TYPE_TAG_CLASS,
    PRIORITY_LABELS,
    EventType,
)
from app.core.timeutil import date_parts, format_time, humanize_ago


class EventRecordOut(BaseModel):
    """一条情报事件（含前端渲染所需的一切派生字段）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: int
    competitor_id: int
    competitor_name: str
    competitor_domain: str
    source_name: str
    event_type: EventType
    title: str
    summary: str
    # AI 对该变化的推断/影响判断（与 summary 事实分离，仅代表模型观点）
    ai_analysis: str | None = None
    keywords: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    priority_level: str = "mid"
    created_at: datetime

    # ---- 以下均为前端直接使用、无需再加工的字段 ----

    @computed_field
    @property
    def date(self) -> str:
        return date_parts(self.created_at)[0]

    @computed_field
    @property
    def time(self) -> str:
        return date_parts(self.created_at)[1]

    @computed_field
    @property
    def date_label(self) -> str:
        return date_parts(self.created_at)[2]

    @computed_field
    @property
    def ago(self) -> str:
        return humanize_ago(self.created_at)

    @computed_field
    @property
    def brand(self) -> str:
        return self.competitor_name

    @computed_field
    @property
    def brand_desc(self) -> str:
        return self.source_name

    @computed_field
    @property
    def desc(self) -> str:
        """列表里跟在标题后的那句说明：摘要的短版，避免一行过长。"""
        text = self.summary.strip()
        return text if len(text) <= 80 else text[:80] + "…"

    @computed_field
    @property
    def source(self) -> str:
        """Dashboard「来源：xxx」用。"""
        return self.source_name

    @computed_field
    @property
    def domain(self) -> str:
        return clean_host(self.competitor_domain)

    @computed_field
    @property
    def logo_url(self) -> str | None:
        host = self.domain
        return f"https://{host}/favicon.ico" if host else None

    @computed_field
    @property
    def icon_text(self) -> str:
        return icon_text(self.competitor_name)

    @computed_field
    @property
    def icon_bg(self) -> str:
        return icon_tone(self.competitor_name)[0]

    @computed_field
    @property
    def icon_color(self) -> str:
        return icon_tone(self.competitor_name)[1]

    @computed_field
    @property
    def tag(self) -> str:
        return EVENT_TYPE_LABELS[self.event_type]

    @computed_field
    @property
    def tag_type(self) -> str:
        return EVENT_TYPE_TAG_CLASS[self.event_type]

    @computed_field
    @property
    def category(self) -> str:
        """与顶部统计卡键位对齐：feature/price/content/negative/other。"""
        return EVENT_TYPE_CATEGORY[self.event_type]

    @computed_field
    @property
    def ai_confidence(self) -> int:
        return int(round(self.confidence * 100))

    @computed_field
    @property
    def priority(self) -> str:
        return PRIORITY_LABELS.get(self.priority_level, "中")

    @computed_field
    @property
    def priority_type(self) -> str:
        return self.priority_level


class EventDetailOut(EventRecordOut):
    """事件详情：在列表字段之外补上差异原文与相关地址。"""

    # 竞品官网
    url: str | None = None
    # 真正发生变化的那张页面
    source_url: str | None = None
    diff_detail: str | None = None


class EventSummaryOut(BaseModel):
    """顶部类型统计（键位与前端 EventSummary 一一对应）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    total: int = 0
    feature: int = 0
    price: int = 0
    content: int = 0
    negative: int = 0
    other: int = 0
    # 优先级分面计数（不被优先级自身筛选清零）
    high: int = 0
    mid: int = 0
    low: int = 0


class EventListOut(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    summary: EventSummaryOut = Field(default_factory=EventSummaryOut)
    # 命中「全部筛选条件（含分类）」的记录总数，用于分页
    total: int = 0
    records: list[EventRecordOut] = Field(default_factory=list)


class SnapshotOut(BaseModel):
    """一条历史快照（情报详情抽屉「查看历史快照」用）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: int
    crawled_at: datetime
    # 是否留了可查看的原始 HTML
    available: bool = False
    # 这次抓取是否检测到变化
    change_detected: bool = False
    # 是否为该事件自身对应的那次抓取
    is_current: bool = False

    @computed_field
    @property
    def crawled_at_label(self) -> str:
        return format_time(self.crawled_at, "%Y-%m-%d %H:%M")


class DailyInsightOut(BaseModel):
    """工作台「AI 今日洞察」：统计数字来自数据库，summary/highlights 来自 LLM（或规则兜底）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    days: int = 1
    period_text: str = "过去 24 小时"
    event_count: int = 0
    high_count: int = 0
    competitor_count: int = 0
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)
    # 是否来自真实模型（false = 规则 Mock）
    from_llm: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now())
