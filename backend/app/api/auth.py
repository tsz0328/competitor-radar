from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import ERR_ACCOUNT_EXISTS, ERR_BAD_CREDENTIALS, BusinessError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import (
    AuthResult,
    LoginRequest,
    RegisterRequest,
    UserBrief,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResult)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """注册：account 即用户名，密码哈希存储，注册成功直接返回令牌（免二次登录）。"""
    exists = await db.execute(select(User).where(User.username == payload.account))
    if exists.scalar_one_or_none() is not None:
        raise BusinessError(ERR_ACCOUNT_EXISTS, "账号已存在", 400)

    user = User(username=payload.account, password_hash=hash_password(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return AuthResult(
        token=create_access_token(user.id),
        user=UserBrief(id=user.id, name=user.username),
    )


@router.post("/login", response_model=AuthResult)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """登录：校验账号密码，成功返回令牌 + 用户信息。"""
    result = await db.execute(select(User).where(User.username == payload.account))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise BusinessError(ERR_BAD_CREDENTIALS, "账号或密码错误", 401)

    return AuthResult(
        token=create_access_token(user.id),
        user=UserBrief(id=user.id, name=user.username),
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    """当前登录用户（请求头需带 Bearer 令牌）。"""
    return current_user
