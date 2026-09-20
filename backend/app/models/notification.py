from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK, TimestampMixin


class EventRead(Base, TimestampMixin):
    """用户对高优情报事件的已读标记（懒标记：表里没有记录 = 未读）。

    多端已读态一致靠服务端落库，而非浏览器 localStorage：同一账号在手机/电脑上
    看到的未读数相同。read-all 时为该用户对所有当前高优事件插一行已读记录。
    """

    __tablename__ = "event_reads"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("intelligence_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_event_read_user_event"),
    )
