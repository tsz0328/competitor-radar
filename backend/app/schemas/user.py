from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CFG = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LoginRequest(BaseModel):
    """登录入参"""

    account: str
    password: str


class RegisterRequest(BaseModel):
    """注册入参"""

    account: str
    password: str


class UserBrief(BaseModel):
    """登录后的用户信息"""

    id: int
    name: str
    avatar: str = ""


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
