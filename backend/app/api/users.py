from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import (
    ERR_EMAIL_CODE_INVALID,
    ERR_OLD_PASSWORD_WRONG,
    ERR_USER_NOT_FOUND,
    BusinessError,
)
from app.core.security import hash_password, verify_password
from app.core.validators import require_valid_account, require_valid_email
from app.models.user import User
from app.schemas.user import (
    EmailBindIn,
    PasswordChangeIn,
    PasswordChangeOut,
    UserOut,
    UserPreferencesIn,
    UserPreferencesOut,
    UserProfileOut,
    UserProfileUpdate,
)
from app.services import email_code as email_code_service
from app.services.accounts import assert_identifier_free

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
    """保存账号资料：只改传了的字段（账号名 / 昵称 / 头像）。

    改账号名不需要验证码——它只是个登录把手，改它不会让别人获得任何东西。
    但**必须做跨列唯一校验**：账号名与邮箱共享同一个登录命名空间，改成一个
    别人已绑定的邮箱会让登录查询命中两行（详见 services/accounts.py）。

    改邮箱**不在这里**：邮箱是第二登录标识 + 通知收件人 + 重置密码的收件人，
    换绑必须先用验证码证明新邮箱归本人所有，走 PUT /me/email。
    """
    if payload.username is not None:
        new_name = require_valid_account(payload.username)
        if new_name != current_user.username:
            await assert_identifier_free(
                db, new_name, exclude_user_id=current_user.id
            )
            current_user.username = new_name

    if payload.nickname is not None:
        # 昵称仅用于展示，允许留空；超长截断
        current_user.nickname = payload.nickname.strip()[:50]

    if payload.avatar is not None:
        current_user.avatar = payload.avatar

    await db.commit()
    await db.refresh(current_user)
    return _profile_out(current_user)


@router.put("/me/email", response_model=UserProfileOut)
async def bind_my_email(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: EmailBindIn,
):
    """绑定 / 换绑 / 解绑邮箱。

    - 传空邮箱 → 解绑：当前已是登录态，解绑不会让谁获得额外能力（只是放弃邮箱登录
      与邮件通知），所以不需要验证码；但要求账号至少留有密码，否则解绑后既没密码
      也没邮箱，这个账号就再也登不进来了。
    - 传非空邮箱 → **必须**带发到该新邮箱的验证码（scene=login）。不验码的话，
      任何登录用户都能把别人的邮箱绑成自己的登录标识，而那个邮箱收到的验证码和
      情报通知也就一并归他了。

    顺带解决一个结构性问题：注册时邮箱是选填的，选了「不填」的用户之后可以在这里
    补绑，从而拿回邮箱登录与自助重置密码的能力，不必麻烦管理员。
    """
    email = (payload.email or "").strip()

    if not email:
        # 解绑前先确认还有别的登录方式，别把自己锁在门外
        if not current_user.password_hash:
            raise BusinessError(
                ERR_EMAIL_CODE_INVALID,
                "该账号没有设置密码，解绑邮箱后将无法再登录，请先设置密码",
                400,
            )
        current_user.email = None
        await db.commit()
        await db.refresh(current_user)
        return _profile_out(current_user)

    new_email = require_valid_email(email)
    if not payload.code:
        raise BusinessError(ERR_EMAIL_CODE_INVALID, "请先获取邮箱验证码", 400)

    # 先查占用再验码：撞车时不必让用户先等一封注定用不上的信
    if new_email != (current_user.email or ""):
        await assert_identifier_free(db, new_email, exclude_user_id=current_user.id)

    # 绑定与登录共用 login 场景：两者的证明要求完全一样（「你能收到这个信箱的信」），
    # 没必要为绑定单开一个场景，多一个场景就多一处可能忘记做隔离的地方。
    await email_code_service.verify_code(
        new_email, email_code_service.SCENE_LOGIN, payload.code
    )

    current_user.email = new_email
    await db.commit()
    await db.refresh(current_user)
    return _profile_out(current_user)


@router.put("/me/password", response_model=PasswordChangeOut)
async def change_my_password(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: PasswordChangeIn,
):
    """修改密码 / 首次设置密码。

    - 已有密码：必须通过原密码校验；
    - 还没有密码（邮箱验证码登录自动创建的账号）：允许直接设置，不需要原密码
      —— 用户此刻已是登录态，身份已经验证过了。

    原密码错误刻意用 400xx 而不是 401xx：前端把 401xx 当成"登录失效"会清 token 跳登录页。
    """
    # 已有密码才校验原密码；没有密码的账号跳过这一步
    if current_user.password_hash and (
        not payload.old_password
        or not verify_password(payload.old_password, current_user.password_hash)
    ):
        raise BusinessError(ERR_OLD_PASSWORD_WRONG, "原密码不正确，请确认后重试", 400)
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
        raise BusinessError(ERR_USER_NOT_FOUND, "用户不存在或已被删除，请刷新后重试", 404)
    return current_user
