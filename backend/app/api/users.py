from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import (
    ERR_ACCOUNT_EXISTS,
    ERR_EMAIL_INVALID,
    ERR_OLD_PASSWORD_WRONG,
    ERR_USER_NOT_FOUND,
    BusinessError,
)
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import (
    PasswordChangeIn,
    PasswordChangeOut,
    UserOut,
    UserPreferencesIn,
    UserPreferencesOut,
    UserProfileOut,
    UserProfileUpdate,
)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me/preferences", response_model=UserPreferencesOut)
async def get_my_preferences(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """当前账号的偏好设置（跟账号走，换浏览器也在）。"""
    return UserPreferencesOut(**(current_user.preferences or {}))


@router.put("/me/preferences", response_model=UserPreferencesOut)
async def save_my_preferences(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: UserPreferencesIn,
):
    """局部更新偏好：只覆盖传过来的字段，其余保持不变。"""
    merged = dict(current_user.preferences or {})
    merged.update(payload.model_dump(exclude_none=True))
    current_user.preferences = merged
    await db.commit()
    await db.refresh(current_user)
    return UserPreferencesOut(**merged)


def _profile_out(user: User) -> UserProfileOut:
    return UserProfileOut(
        id=user.id,
        username=user.username,
        nickname=user.nickname or "",
        email=user.email or "",
        avatar=user.avatar or "",
        password_length=user.password_length,
        is_admin=user.is_admin,
    )


@router.get("/me", response_model=UserProfileOut)
async def get_my_profile(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """当前账号资料（账号 / 接收通知的邮箱 / 头像）。"""
    return _profile_out(current_user)


@router.put("/me", response_model=UserProfileOut)
async def update_my_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: UserProfileUpdate,
):
    """保存账号资料：只改传了的字段。

    - 账号：唯一，重复报错；
    - 通知邮箱：允许留空（留空 = 不单独收通知，回退运维配置的收件人）；
    - 头像：前端裁剪压缩后的 data URL，传空串表示清除。
    """
    if payload.username is not None:
        new_name = payload.username.strip()
        if not new_name:
            raise BusinessError(ERR_ACCOUNT_EXISTS, "账号不能为空", 400)
        if new_name != current_user.username:
            exists = await db.execute(select(User).where(User.username == new_name))
            if exists.scalar_one_or_none() is not None:
                raise BusinessError(ERR_ACCOUNT_EXISTS, "账号已存在", 400)
            current_user.username = new_name

    if payload.email is not None:
        email = payload.email.strip()
        if email and (
            "@" not in email
            or " " in email
            or email.startswith("@")
            or email.endswith("@")
        ):
            raise BusinessError(ERR_EMAIL_INVALID, "邮箱格式不正确", 400)
        current_user.email = email or None

    if payload.nickname is not None:
        # 昵称仅用于展示，允许留空；超长截断
        current_user.nickname = payload.nickname.strip()[:50]

    if payload.avatar is not None:
        current_user.avatar = payload.avatar

    await db.commit()
    await db.refresh(current_user)
    return _profile_out(current_user)


@router.put("/me/password", response_model=PasswordChangeOut)
async def change_my_password(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: PasswordChangeIn,
):
    """修改密码：必须先通过原密码校验。

    原密码错误刻意用 400xx 而不是 401xx：前端把 401xx 当成"登录失效"会清 token 跳登录页。
    """
    if not verify_password(payload.old_password, current_user.password_hash):
        raise BusinessError(ERR_OLD_PASSWORD_WRONG, "原密码不正确", 400)
    current_user.password_hash = hash_password(payload.new_password)
    current_user.password_length = len(payload.new_password)
    await db.commit()
    return PasswordChangeOut(ok=True)


@router.get("", response_model=list[UserOut])
async def list_users(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """只返回当前账号自己。

    用户资料属于「用户数据」，不对外暴露其它账号（早期版本整表返回，属于越权）。
    若将来需要管理员视角的账号列表，应先引入角色再做权限判断。
    """
    return [current_user]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    current_user: Annotated[User, Depends(get_current_user)],
    user_id: int,
):
    """查看用户资料：只允许查看自己，别人的 id 一律按「不存在」处理。"""
    if user_id != current_user.id:
        raise BusinessError(ERR_USER_NOT_FOUND, "用户不存在", 404)
    return current_user
