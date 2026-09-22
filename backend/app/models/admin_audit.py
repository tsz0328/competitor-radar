"""管理员审计日志：留痕管理员对平台的关键操作（用户管理、系统设置）。

写审计的时机约定：审计记录跟业务变更落在**同一事务**里提交——操作成功
必有日志、失败必无残留。detail 是给人看的变更摘要，绝不写敏感值
（如 SMTP 授权码、密码明文）。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)

    # 操作人：即使该管理员日后被删除，日志里仍保留当时的 id 与账号名
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    admin_username: Mapped[str] = mapped_column(String(100), nullable=False)

    # 动作标识（如 update_user / delete_user / update_system_settings）
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 目标对象类型（user / system_settings / announcement）
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 目标对象 id（system_settings 这类无 id 的对象为 NULL）
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # 变更摘要（如「角色: 普通用户→管理员」「状态: 启用→停用」）
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )