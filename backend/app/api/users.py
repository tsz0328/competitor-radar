from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import ERR_USER_NOT_FOUND, BusinessError
from app.models.user import User
from app.schemas.user import UserOut, UserPreferencesIn, UserPreferencesOut

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me/preferences", response_model=UserPreferencesOut)
async def get_my_preferences(current_user: User = Depends(get_current_user)):
    """当前账号的偏好设置（跟账号走，换浏览器也在）。"""
    return UserPreferencesOut(**(current_user.preferences or {}))


@router.put("/me/preferences", response_model=UserPreferencesOut)
async def save_my_preferences(
    payload: UserPreferencesIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """局部更新偏好：只覆盖传过来的字段，其余保持不变。"""
    merged = dict(current_user.preferences or {})
    merged.update(payload.model_dump(exclude_none=True))
    current_user.preferences = merged
    await db.commit()
    await db.refresh(current_user)
    return UserPreferencesOut(**merged)


@router.get("", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return result.scalars().all()


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise BusinessError(ERR_USER_NOT_FOUND, "用户不存在", 404)
    return user
