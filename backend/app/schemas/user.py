from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CFG = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LoginRequest(BaseModel):
    """登录入参（密码登录）。

    account 是**账号或邮箱**——两者都能登录。后端 `WHERE username = ? OR email = ?`，
    命中的是谁就以谁为准，所以前端一个输入框即可，字段名也无需区分形态。
    """

    account: str
    password: str
    # remember：勾选「记住我」→ 签发长期令牌；不勾 → 只发会话令牌
    remember: bool = False


class RegisterRequest(BaseModel):
    """注册入参：账号必填，邮箱选填。

    - **username（必填）**：自定义登录账号，3–30 位 `a-z 0-9 _ -`，禁止 `@`。
    - **email（选填）**：填了它就同时获得三个能力——① 也能用它登录
      ② 高优事件通知发到这里 ③ 忘记密码时能自助重置。**选填不等于免检**：
      只要填了就必须通过验证码，否则等于允许抢注别人的邮箱，而它同时是通知收件人，
      抢注成功后该账号的情报会原封不动发到别人信箱里。
    """

    username: str
    password: str
    # 邮箱选填；填了则 code 必填
    email: str | None = None
    # 邮箱验证码（scene=login，注册与验证码登录共用同一场景）
    code: str | None = None
    # remember：注册即登录，语义同登录页的「记住我」（注册页没有勾选框，默认不记住）
    remember: bool = False


class EmailCodeRequest(BaseModel):
    """获取邮箱验证码入参。

    `account` 的形态随 scene 而变：
    - scene=login → 必须是**邮箱**（验证码就发到这个地址）；
    - scene=reset → 可以是**账号或邮箱**：后端先定位账号，再往该账号绑定的邮箱发码，
      这样用账号名也能发起重置。

    两个场景的验证码在缓存里互相隔离，不能混用。
    """

    model_config = _CFG

    account: str = Field(..., min_length=1, max_length=100)
    scene: str = Field(default="login", pattern="^(login|reset)$")


class CodeLoginRequest(BaseModel):
    """邮箱验证码登录入参（该邮箱还没有账号时会自动创建一个）。"""

    model_config = _CFG

    email: str = Field(..., min_length=3, max_length=100)
    code: str = Field(..., min_length=4, max_length=10)
    remember: bool = False


class ResetPasswordRequest(BaseModel):
    """用邮箱验证码重置密码入参。

    account 可以是账号或邮箱；验证码实际是发到「该账号绑定的邮箱」上的。
    """

    model_config = _CFG

    account: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=4, max_length=10)
    new_password: str = Field(..., min_length=6, max_length=72)


class RefreshRequest(BaseModel):
    """令牌续期入参。

    续期本身只要求「当前令牌仍有效」（走 get_current_user）；remember 决定新令牌的
    时长档位——前端从本地「记住我」偏好带过来，与原登录保持一致。
    """

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
    """用户中心回显：昵称 / 账号 / 绑定邮箱 / 头像。"""

    model_config = _CFG

    id: int
    # 登录账号（自定义，唯一）
    username: str
    # 展示用昵称，可空；前端回退显示账号
    nickname: str = ""
    # 绑定的邮箱；空串表示未绑定（未绑定时不能邮箱登录，也收不到邮件通知）
    email: str = ""
    # 头像 data URL，空串表示还没设置（界面用首字母占位）
    avatar: str = ""
    # 密码位数（不暴露明文）；NULL 表示「未设置密码」（只能用验证码登录）
    password_length: int | None = None
    # 是否管理员（可访问系统级设置）；前端据此显示"系统设置"分类
    is_admin: bool = False


class UserProfileUpdate(BaseModel):
    """用户中心保存入参：只传要改的字段，未传的保持不变。

    **不含 email**：邮箱是登录标识之一，改绑必须先证明新邮箱归本人所有，
    所以走独立的 `PUT /api/users/me/email`（带验证码），不混进普通资料更新。
    账号名可以在这里改——它只是个登录把手，改它不会让别人获得任何东西，
    但仍要做「跨列唯一」校验（不能撞别人的邮箱）。
    """

    model_config = _CFG

    username: str | None = Field(default=None, min_length=1, max_length=100)
    nickname: str | None = Field(default=None, max_length=50)
    # 裁剪压缩后的头像 data URL；传空串表示清除头像
    avatar: str | None = Field(default=None, max_length=400_000)


class EmailBindIn(BaseModel):
    """绑定 / 换绑邮箱入参。

    - email 传空串 → 解除绑定（当前登录态已证明身份，解绑不会让谁获得额外能力）；
    - email 非空 → **必须**带上发到该新邮箱的验证码，否则谁都能把别人的邮箱
      绑成自己的登录标识，而那个邮箱的验证码与情报通知也就一并成了他的。
    """

    model_config = _CFG

    email: str = Field(..., max_length=100)
    # 绑定时必填；解绑（email 为空串）时忽略
    code: str | None = Field(default=None, max_length=10)


class PasswordChangeIn(BaseModel):
    """修改密码。

    old_password 可空：用邮箱验证码登录自动创建的账号本来就没有密码，
    这种情况下允许直接设置新密码；已有密码的账号仍然必须校验原密码。
    """

    model_config = _CFG

    old_password: str | None = Field(default=None, max_length=72)
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
