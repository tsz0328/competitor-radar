from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import (
    ERR_ACCOUNT_DISABLED,
    ERR_TOKEN_INVALID,
    ERR_TOKEN_USER_GONE,
    BusinessError,
)
from app.core.security import decode_access_token
from app.models.user import User

# 声明：令牌从请求头 Authorization: Bearer <token> 里取
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """解析令牌 → 查出用户 → 返回；任何一步失败都直接 401。"""
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise BusinessError(ERR_TOKEN_INVALID, "令牌无效或已过期", 401)

    result = await db.execute(select(User).where(User.id == int(payload.get("sub"))))
    user = result.scalar_one_or_none()
    if user is None:
        raise BusinessError(ERR_TOKEN_USER_GONE, "用户不存在", 401)
    if not user.is_active:
        raise BusinessError(ERR_ACCOUNT_DISABLED, "账号已被停用", 401)
    return user


async def get_current_user_sse(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """SSE 鉴权：浏览器 EventSource 不能自定义请求头，令牌放 ?token= 或 Authorization 头。

    仅用于 /api/notifications/stream。令牌出现在 URL 中（可能被代理日志记到），
    因此该端点只推「未读数」这种非敏感数据，绝不透出事件正文。
    """
    token = request.query_params.get("token")
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:]
    if not token:
        raise BusinessError(ERR_TOKEN_INVALID, "缺少令牌", 401)

    payload = decode_access_token(token)
    if payload is None:
        raise BusinessError(ERR_TOKEN_INVALID, "令牌无效或已过期", 401)

    user = (
        await db.execute(select(User).where(User.id == int(payload.get("sub"))))
    ).scalar_one_or_none()
    if user is None:
        raise BusinessError(ERR_TOKEN_USER_GONE, "用户不存在", 401)
    if not user.is_active:
        raise BusinessError(ERR_ACCOUNT_DISABLED, "账号已被停用", 401)
    return user
