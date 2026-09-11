from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

BigIntPK = BigInteger().with_variant(Integer, "sqlite")


def enum_values(enum_cls):
    return [m.value for m in enum_cls]


class Base(DeclarativeBase):
    """所有数据库表的公共基类。"""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
