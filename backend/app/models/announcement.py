"""平台公告：管理员发布、用户端只读展示。

管理员在系统设置页发布/下线；用户登录后 AppLayout 顶部横幅展示
is_active=True 的最新公告（可关闭，localStorage 记忆）。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)

    # 公告正文（纯文本，前端作为单行横幅展示）
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 发布人（管理员 id）
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 是否在用户端展示：下线保留历史记录
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )