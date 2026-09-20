from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK


class User(Base):
    # 在数据库里这张表叫 users（类名 User 会自动转小写复数，但显式写更保险）
    __tablename__ = "users"

    # 主键 id：BigIntPK 大整数自增（DB 无关：SQLite/MySQL 通用）
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)

    # username：最长 50 字符，唯一，不能为空
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # email：最长 100 字符，可空。同时用作「接收通知的邮箱」：
    # 高优事件即时通知会发给它，留空则回退运维在 .env 里配的收件人。
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # nickname：展示用的昵称（最长 50），可空可重复；留空时界面回退显示账号。
    # 与登录账号 username 区分：账号用于登录且唯一，昵称仅用于展示。
    nickname: Mapped[str] = mapped_column(String(50), default="", nullable=False)

    # password_length：仅存「密码位数」（不存明文），用于在账号页以 * 占位展示。
    # 老数据 / 外部导入的账号可能为 NULL（界面回退显示"未设置"）。
    password_length: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 头像：前端裁剪压缩后的小图 data URL（空串 = 用首字母生成的占位头像）
    avatar: Mapped[str] = mapped_column(Text, default="", nullable=False)

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # is_admin：是否为管理员。管理员可访问系统级设置（如发件邮箱 SMTP_SENDER）。
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)

    # is_active：账号是否启用。管理员可停用账号；停用后无法登录，
    # 已登录的会话会在下次请求时被拦截（401 强制重新登录）。
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # 用户级偏好（跟账号走，不落浏览器）：如"允许添加不可达官网""新增竞品默认勾选的监控页"等
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
