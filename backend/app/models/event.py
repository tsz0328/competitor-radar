from sqlalchemy import JSON, BigInteger, Enum, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# 事件类型枚举与标签的唯一定义在 core/event_types.py，
# 这里再导出一次，调用方按文档从 app.models.event 导入同样可用。
from app.core.event_types import (  # noqa: F401
    EVENT_TYPE_CATEGORY,
    EVENT_TYPE_LABELS,
    EVENT_TYPE_TAG_CLASS,
    PRIORITY_LABELS,
    EventType,
)
from app.models.base import Base, BigIntPK, TimestampMixin, enum_values


class IntelligenceEvent(Base, TimestampMixin):
    """情报事件：一次"有意义的变化" + 对它的解释。

    与快照的关系：一条快照最多产出一条事件（变化过于轻微时不产出），
    事件里保留 diff_detail 便于回溯，也保留 snapshot_id 做精确归因。
    """

    __tablename__ = "intelligence_events"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    competitor_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("monitor_sources.id"), nullable=True, index=True
    )
    snapshot_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("page_snapshots.id"), nullable=True
    )

    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, native_enum=False, length=30, values_callable=enum_values),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)  # AI 生成的一句话说明
    diff_detail: Mapped[str | None] = mapped_column(Text)  # 触发本次事件的差异原文
    keywords: Mapped[list[str] | None] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="mid", nullable=False)

    __table_args__ = (Index("idx_event_competitor_created", "competitor_id", "created_at"),)
