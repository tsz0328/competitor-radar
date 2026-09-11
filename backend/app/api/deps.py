from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ERR_TOKEN_INVALID, ERR_TOKEN_USER_GONE, BusinessError
from app.core.security import decode_access_token
from app.models.user import User

# 声明：令牌从请求头 Authorization: Bearer <token> 里取
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """解析令牌 → 查出用户 → 返回；任何一步失败都直接 401。"""
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise BusinessError(ERR_TOKEN_INVALID, "令牌无效或已过期", 401)

    result = await db.execute(select(User).where(User.id == int(payload.get("sub"))))
    user = result.scalar_one_or_none()
    if user is None:
        raise BusinessError(ERR_TOKEN_USER_GONE, "用户不存在", 401)
    return user
