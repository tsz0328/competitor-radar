from pydantic import BaseModel


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
