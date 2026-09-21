import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntPK, TimestampMixin, enum_values

if TYPE_CHECKING:  # 仅用于类型标注；运行时由 SQLAlchemy 解析字符串引用
    from app.models.source import MonitorSource


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

    # logo_url：竞品真实图标地址（官网 favicon，或 SPA 站点挂在 CDN 上的图标）。
    # 由抓取官网首页时"顺手"解析并落库（复用已下载的 HTML，零额外请求），
    # 之后所有页面共用同一个图标，不必各自去猜；空串表示还没解析到，
    # 前端会按 favicon → apple-touch-icon → 首字母头像逐级回退。
    logo_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[CompetitorStatus] = mapped_column(
        Enum(CompetitorStatus, native_enum=False, length=10, values_callable=enum_values),
        default=CompetitorStatus.ACTIVE,
        nullable=False,
    )

    # 软删除标记：非空表示该竞品已移入回收站。所有"真实"查询都过滤它，
    # 因此软删后竞品全局不可见，但行仍在、id 不变——其监控源/快照/事件全部保留，
    # 重加同竞品（按 official_url 命中）可原样恢复，历史数据自动连回。
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # 该竞品下要监控的页面。lazy="selectin"：查竞品时用一条额外 SELECT 一并把源取回，
    # 避开异步场景下"惰性加载"会报错的问题；级联删除保证删竞品时不留孤儿源。
    sources: Mapped[list["MonitorSource"]] = relationship(
        back_populates="competitor",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
