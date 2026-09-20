"""系统设置（每个用户一行）。

只存该用户的 LLM 全局开关（启用 AI、超时、最小变更行数）；凭证类信息
（地址 / 模型 / Key）在 llm_providers 表，按用户隔离。
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK


class AppSetting(Base):
    """某个用户的全局设置（一人一行，按 user_id 唯一）。"""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)

    # 归属用户：设置属于每个用户自己
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, unique=True, index=True
    )

    # ---- LLM / AI 模型 ----
    llm_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 遗留列：早期「单行存凭证」的字段，仅供旧数据迁移读取，新写入一律置空
    llm_api_key: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    llm_base_url: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    llm_model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    llm_timeout_seconds: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    llm_min_change_lines: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
