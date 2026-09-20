from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SystemSetting(Base):
    """系统级全局配置（键值对），跟具体账号无关。

    目前用于「发件邮箱 SMTP_SENDER」这类运维配置——原先只能写在 .env，
    现在管理员可在界面改，落库后覆盖 .env 的同名项。留空表示回退 .env。
    """

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
