import enum

from sqlalchemy import JSON, BigInteger, Enum, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK, TimestampMixin, enum_values


class TrendDirection(str, enum.Enum):
    """变化节奏的方向。"""

    RISING = "rising"  # 变化变多，需要关注
    STABLE = "stable"  # 基本平稳
    DECLINING = "declining"  # 变化变少


TREND_DIRECTION_LABELS: dict[TrendDirection, str] = {
    TrendDirection.RISING: "活跃度上升",
    TrendDirection.STABLE: "节奏平稳",
    TrendDirection.DECLINING: "活跃度回落",
}


class TrendInsight(Base, TimestampMixin):
    """某个竞品在一段时间内的趋势判断（聚合真实事件 + LLM/规则结论）。"""

    __tablename__ = "trend_insights"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    competitor_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    period_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    direction: Mapped[TrendDirection] = mapped_column(
        Enum(TrendDirection, native_enum=False, length=16, values_callable=enum_values),
        nullable=False,
    )
    summary: Mapped[str | None] = mapped_column(Text)
    # 趋势要点（字符串数组）
    highlights: Mapped[list[str] | None] = mapped_column(JSON)

    # 统计口径：全部来自真实事件，不由 LLM 编造
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_impact_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coverage_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (Index("idx_trend_competitor_created", "competitor_id", "created_at"),)
