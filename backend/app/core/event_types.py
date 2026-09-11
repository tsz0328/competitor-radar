"""情报事件类型的唯一口径（v1 共 5 类）。

放在 core 而不是 models，是为了让「规则/Mock 分析」等纯逻辑模块也能引用标签，
同时避免 core 反向依赖 models。`models/event.py` 会把它再导出，
调用方按文档从 `app.models.event` 导入同样可用。
"""
import enum


class EventType(str, enum.Enum):
    """竞品情报事件类型（与前端「功能更新/价格变化/内容更新/舆论动态/其他」一一对应）。"""

    NEW_FEATURE = "new_feature"  # 功能更新
    PRICE_CHANGE = "price_change"  # 价格变化
    CONTENT_UPDATE = "content_update"  # 内容更新
    PUBLIC_SENTIMENT = "public_sentiment"  # 舆论动态（原 negative_review_spike）
    OTHER = "other"  # 其他


EVENT_TYPE_LABELS: dict[EventType, str] = {
    EventType.NEW_FEATURE: "功能更新",
    EventType.PRICE_CHANGE: "价格变化",
    EventType.CONTENT_UPDATE: "内容更新",
    EventType.PUBLIC_SENTIMENT: "舆论动态",
    EventType.OTHER: "其他",
}

# 前端事件流页顶部统计卡/筛选用的短分类键
EVENT_TYPE_CATEGORY: dict[EventType, str] = {
    EventType.NEW_FEATURE: "feature",
    EventType.PRICE_CHANGE: "price",
    EventType.CONTENT_UPDATE: "content",
    EventType.PUBLIC_SENTIMENT: "negative",
    EventType.OTHER: "other",
}

# 前端标签配色类名（对应 Event.vue 中的 .tag-* 样式）
EVENT_TYPE_TAG_CLASS: dict[EventType, str] = {
    EventType.NEW_FEATURE: "tag-new",
    EventType.PRICE_CHANGE: "tag-price",
    EventType.CONTENT_UPDATE: "tag-update",
    EventType.PUBLIC_SENTIMENT: "tag-negative",
    EventType.OTHER: "tag-other",
}

PRIORITY_LABELS: dict[str, str] = {"high": "高", "mid": "中", "low": "低"}
