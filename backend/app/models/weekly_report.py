import enum
from datetime import date

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    Enum,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK, TimestampMixin, enum_values


class ReportType(str, enum.Enum):
    WEEKLY = "weekly"  # 周报
    MONTHLY = "monthly"  # 月报（v1 只生成周报，枚举先留着）


class WeeklyReport(Base, TimestampMixin):
    """竞品周报：一份"统计快照 + AI 叙述"的存档。

    设计要点：报表里的数字（stats / 分类分布 / 排行 / 趋势）全部由数据库聚合而来，
    存在 payload 里一起冻结；LLM 只负责写 summary 与 content 两段叙述文字，
    不允许它生成数字——避免报告里出现编造的统计。
    """

    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    report_type: Mapped[ReportType] = mapped_column(
        Enum(ReportType, native_enum=False, length=10, values_callable=enum_values),
        default=ReportType.WEEKLY,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    range_start: Mapped[date] = mapped_column(Date, nullable=False)
    range_end: Mapped[date] = mapped_column(Date, nullable=False)
    competitor_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 收藏：跟着账号走（服务端持久化，前端不再自己存 localStorage）
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    summary: Mapped[str | None] = mapped_column(Text)  # AI 写的核心摘要
    content: Mapped[str | None] = mapped_column(Text)  # AI 写的周报正文（Markdown）
    # 结构化报表内容：stats / highlights / categoryDist / rank / trend / 关联事件等
    payload: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (
        Index("idx_report_user_created", "user_id", "created_at"),
        UniqueConstraint("user_id", "range_start", name="uq_report_user_range_start"),
    )
