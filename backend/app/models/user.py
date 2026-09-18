from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK


class User(Base):
    # 在数据库里这张表叫 users（类名 User 会自动转小写复数，但显式写更保险）
    __tablename__ = "users"

    # 主键 id：BigIntPK 大整数自增（DB 无关：SQLite/MySQL 通用）
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)

    # username：最长 50 字符，唯一，不能为空
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # email：最长 100 字符，可空（| None 表示这一列可以没有值）
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # 用户级偏好（跟账号走，不落浏览器）：如"允许添加不可达官网""新增竞品默认勾选的监控页"等
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
