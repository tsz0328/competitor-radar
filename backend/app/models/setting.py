"""系统设置（单行表，主键固定为 1）。

当前只存 LLM（AI 模型）配置；后续新增全局设置时在此扩展字段即可，
无需再建新表。整张表永远只有 id=1 这一行。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK

# 单例主键：读写都认这一行
SETTINGS_ID = 1


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)

    # ---- LLM / AI 模型 ----
    llm_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
