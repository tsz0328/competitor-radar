from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK


class User(Base):
    # 在数据库里这张表叫 users（类名 User 会自动转小写复数，但显式写更保险）
    __tablename__ = "users"

    # 主键 id：BigIntPK 大整数自增（DB 无关：SQLite/MySQL 通用）
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)

    # username：账号名，就是登录标识。最长 100（自动建号时会写入邮箱，邮箱最长 100），
    # 唯一、不可为空。规则：3–30 位 `a-z 0-9 _ -`，**禁止 `@`**（见 core/validators）。
    # 自动建号（邮箱验证码首次登录）也遵守同一规则：username 取邮箱本地部分（不含 `@`），
    # 清洗 / 去重逻辑见 services/accounts.py:derive_username_from_email，不再有「含 @ 例外」。
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # email：**选填**的联系邮箱（归一化小写）。一旦绑定，它同时是：
    # ① 第二个登录标识（登录时 `username = ? OR email = ?`）② 高优事件通知的收件人
    #   ③ 忘记密码时验证码的收件人。
    # 空值统一存 NULL，**绝不存空串**——空串会撞 uq_users_email，导致第二个
    # 「不填邮箱」的用户直接 IntegrityError 注册失败。
    # ⚠️ username 与 email **共享同一个命名空间**：写任一列前都要检查是否撞了另一列
    #   （DB 唯一索引只管单列，跨列得靠应用层，见 api/auth.py 的 _assert_identifier_free）。
    email: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)

    # nickname：展示用的昵称（最长 50），可空可重复；留空时界面回退显示账号。
    # 与登录账号 username 区分：账号用于登录且唯一，昵称仅用于展示。
    nickname: Mapped[str] = mapped_column(String(50), default="", nullable=False)

    # password_length：仅存「密码位数」（不存明文），用于在账号页以 * 占位展示。
    # NULL 表示「未设置密码」：既包括老数据 / 外部导入的账号，
    # 也包括用邮箱验证码登录时自动创建、还没设过密码的账号。
    password_length: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 头像：前端裁剪压缩后的小图 data URL（空串 = 用首字母生成的占位头像）
    avatar: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # password_hash：NULL 表示该账号尚未设置密码（邮箱验证码登录自动创建）。
    # 这类账号只能用验证码登录；想启用密码登录，去用户中心设置新密码即可
    # （未设密码时不需要校验原密码）。
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # is_admin：是否为管理员。管理员可访问系统级设置（如发件邮箱 SMTP_SENDER）。
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)

    # is_active：账号是否启用。管理员可停用账号；停用后无法登录，
    # 已登录的会话会在下次请求时被拦截（401 强制重新登录）。
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # 用户级偏好（跟账号走，不落浏览器）：如"允许添加不可达官网""新增竞品默认勾选的监控页"等
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
