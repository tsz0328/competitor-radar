import enum

from sqlalchemy import BigInteger, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntPK, TimestampMixin, enum_values


class CompetitorStatus(str, enum.Enum):
    ACTIVE = "active"  # 监控中
    PAUSED = "paused"  # 已暂停


class Competitor(Base, TimestampMixin):
    """竞品：你持续关注的一个产品。"""

    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)

    # 外键：这个竞品属于哪个用户（ForeignKey 指向 users.id）
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 如 Notion
    official_url: Mapped[str | None] = mapped_column(String(255))  # 官网地址
    category: Mapped[str | None] = mapped_column(String(50))  # 如 协作办公
    description: Mapped[str | None] = mapped_column(Text)  # 一句话描述
    status: Mapped[CompetitorStatus] = mapped_column(
        Enum(CompetitorStatus, native_enum=False, length=10, values_callable=enum_values),
        default=CompetitorStatus.ACTIVE,
        nullable=False,
    )

    # 该竞品下要监控的页面。lazy="selectin"：查竞品时用一条额外 SELECT 一并把源取回，
    # 避开异步场景下"惰性加载"会报错的问题；级联删除保证删竞品时不留孤儿源。
    sources: Mapped[list["MonitorSource"]] = relationship(
        back_populates="competitor",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
