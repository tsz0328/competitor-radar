from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CFG = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LoginRequest(BaseModel):
    """登录入参"""

    account: str
    password: str
    # remember：勾选「记住我」→ 签发长期令牌；不勾 → 只发会话令牌
    remember: bool = False


class RegisterRequest(BaseModel):
    """注册入参"""

    account: str
    password: str
    # remember：注册即登录，语义同登录页的「记住我」（注册页没有勾选框，默认不记住）
    remember: bool = False


class UserBrief(BaseModel):
    """登录后的用户信息（前端存起来渲染头像/昵称/账号/邮箱）"""

    id: int
    # name：展示用昵称（空串时前端回退显示账号）
    name: str = ""
    # username：登录账号，唯一
    username: str
    avatar: str = ""
    email: str = ""
    # is_admin：是否管理员（可访问系统级设置）
    is_admin: bool = False


class AuthResult(BaseModel):
    """登录/注册成功返回"""

    token: str
    user: UserBrief


class UserOut(BaseModel):
    """完整用户信息"""

    model_config = {"from_attributes": True}

    id: int
    username: str
    email: str | None = None
    avatar: str = ""
    is_admin: bool = False


class UserProfileOut(BaseModel):
    """用户中心回显：昵称 / 账号 / 通知邮箱 / 头像。"""

    model_config = _CFG

    id: int
    username: str
    # 展示用昵称，可空；前端回退显示账号
    nickname: str = ""
    # 通知邮箱：高优事件即时通知会发到这里
    email: str = ""
    # 头像 data URL，空串表示还没设置（界面用首字母占位）
    avatar: str = ""
    # 密码位数（不暴露明文）；NULL 表示未知（界面回退"未设置"）
    password_length: int | None = None
    # 是否管理员（可访问系统级设置）；前端据此显示"系统设置"分类
    is_admin: bool = False


class UserProfileUpdate(BaseModel):
    """用户中心保存入参：只传要改的字段，未传的保持不变。"""

    model_config = _CFG

    username: str | None = Field(default=None, min_length=1, max_length=50)
    nickname: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=100)
    # 裁剪压缩后的头像 data URL；传空串表示清除头像
    avatar: str | None = Field(default=None, max_length=400_000)


class PasswordChangeIn(BaseModel):
    """修改密码：必须提供原密码。"""

    model_config = _CFG

    old_password: str = Field(..., min_length=1, max_length=72)
    new_password: str = Field(..., min_length=6, max_length=72)


class PasswordChangeOut(BaseModel):
    """修改密码结果。"""

    model_config = _CFG

    ok: bool = True


class UserPreferencesOut(BaseModel):
    """用户级偏好（跟着账号走，不落浏览器）。"""

    model_config = _CFG

    # 是否允许添加"官网不可达"的竞品
    allow_unreachable_official: bool = False
    # 新增竞品时默认勾选的监控页面类型
    default_source_types: list[str] = Field(default_factory=list)


class UserPreferencesIn(BaseModel):
    """偏好更新入参：只传要改的字段，未传的保持不变。"""

    model_config = _CFG

    allow_unreachable_official: bool | None = None
    default_source_types: list[str] | None = None
