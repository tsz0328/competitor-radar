from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.source_registry import RenderMode, SourceType
from app.models.base import Base, BigIntPK, TimestampMixin, enum_values

if TYPE_CHECKING:  # 仅用于类型标注；运行时由 SQLAlchemy 解析字符串引用
    from app.models.competitor import Competitor


class MonitorSource(Base, TimestampMixin):
    """监控源：竞品身上一个具体要盯的页面。"""

    __tablename__ = "monitor_sources"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    competitor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("competitors.id"), nullable=False
    )

    # 反向关联：从监控源能回到所属竞品
    competitor: Mapped["Competitor"] = relationship(back_populates="sources")

    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, native_enum=False, length=30, values_callable=enum_values),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 展示名，如 定价页
    url: Mapped[str] = mapped_column(String(1024), nullable=False)

    # 建源时把策略"快照"下来：以后改注册表默认值，也不会影响已建的历史源
    render_mode: Mapped[RenderMode] = mapped_column(
        Enum(RenderMode, native_enum=False, length=10, values_callable=enum_values),
        nullable=False,
    )
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ---- 抓取健康度（里程碑 6 会用到）----
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(10))  # success / failed
    last_error: Mapped[str | None] = mapped_column(Text)
    fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (Index("idx_source_competitor_enabled", "competitor_id", "enabled"),)
