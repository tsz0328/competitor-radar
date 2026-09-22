"""鉴权接口。

设计要点（改这里前先读一遍）：

1. **两个登录标识，一个命名空间**：`username`（自定义账号名）与 `email`（选填邮箱）
   都能登录，登录查询是 `WHERE username = ? OR email = ?`。因此两者**共享同一命名空间**
   ——写任一列前都必须检查它是否撞了另一列（`_assert_identifier_free`）。数据库的
   唯一索引只管单列，跨列只能靠应用层，这是本模块最容易埋 bug 的地方。
2. **邮箱选填，但填了就必须验码**：邮箱同时是高优事件通知的收件人，不验码让它生效
   就等于允许抢注别人的信箱。
3. **验证码登录（邮箱首次登录）会自动建号**：账号名取邮箱 `@` 前的本地部分（不含
   `@`），与「账号名禁 `@`」规则一致；本地部分若含非法字符或被占用，会清洗 / 加数字后缀，
   详见 `services/accounts.py:derive_username_from_email`。
4. **失败提示不区分「账号不存在」与「密码错误」**：统一「账号或密码错误，请核对账号与密码后重试，忘记密码可点击「忘记密码」重置」，避免
   把「某账号是否存在」免费告诉探测者。
"""
from typing import Annotated
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import (
    ERR_ACCOUNT_DISABLED,
    ERR_BAD_CREDENTIALS,
    ERR_EMAIL_CODE_INVALID,
    ERR_EMAIL_NOT_BOUND,
    ERR_PASSWORD_NOT_SET,
    ERR_PASSWORD_TOO_SHORT,
    ERR_USER_NOT_FOUND,
    BusinessError,
)
from app.core.security import create_login_token, hash_password, verify_password
from app.core.validators import (
    normalize_identifier,
    require_valid_account,
    require_valid_email,
)
from app.models.user import User
from app.schemas.user import (
    AuthResult,
    CodeLoginRequest,
    EmailCodeRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserBrief,
    UserOut,
)
from app.services import email_code as email_code_service
from app.services.accounts import (
    assert_identifier_free,
    derive_username_from_email,
    find_by_identifier,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# bcrypt 的上限：超过 72 字节会被静默截断，干脆提前拒绝
PASSWORD_MAX_LEN = 72


def _brief(user: User) -> UserBrief:
    """组装登录返回的用户信息（email 未绑定时回空串，前端好处理）。"""
    return UserBrief(
        id=user.id,
        name=user.nickname or "",
        username=user.username,
        avatar=user.avatar,
        email=user.email or "",
        is_admin=user.is_admin,
    )


def _check_password_length(password: str) -> None:
    if len(password) < 6:
        raise BusinessError(ERR_PASSWORD_TOO_SHORT, "密码至少 6 位", 400)
    if len(password.encode("utf-8")) > PASSWORD_MAX_LEN:
        raise BusinessError(ERR_PASSWORD_TOO_SHORT, "密码过长，请控制在 72 字节以内", 400)


async def _find_by_identifier(db: AsyncSession, value: str) -> User | None:
    """本模块内的薄封装，便于阅读时少一层跳转（实现见 services/accounts.py）。"""
    return await find_by_identifier(db, value)


def _require_bound_email(user: User) -> str:
    """取账号绑定的邮箱；没绑定就明确说清楚（而不是发一封永远不来的信）。"""
    if not user.email:
        raise BusinessError(
            ERR_EMAIL_NOT_BOUND,
            "该账号还没有绑定邮箱，无法通过邮件重置密码，请联系管理员",
            400,
        )
    return user.email


@router.post("/register", response_model=AuthResult)
async def register(
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: RegisterRequest,
):
    """注册：账号必填，邮箱选填（填了就必须带验证码）。

    校验顺序刻意是「账号格式 → 邮箱格式 → 密码 → 重复 → 验证码」：
    重复检查排在验证码之前，用户不必先等一封注定用不上的信。
    """
    username = require_valid_account(payload.username)
    _check_password_length(payload.password)

    email = require_valid_email(payload.email) if payload.email else ""

    # 账号名与邮箱共享命名空间，两个都要查
    await assert_identifier_free(db, username)
    if email:
        await assert_identifier_free(db, email)

    if email:
        if not payload.code:
            raise BusinessError(ERR_EMAIL_CODE_INVALID, "请先获取邮箱验证码", 400)
        await email_code_service.verify_code(
            email, email_code_service.SCENE_LOGIN, payload.code
        )

    user = User(
        username=username,
        # 空值统一存 NULL：空串会占用 uq_users_email 的唯一名额，
        # 导致第二个「不填邮箱」的用户注册失败
        email=email or None,
        password_hash=hash_password(payload.password),
        password_length=len(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return AuthResult(
        token=create_login_token(user.id, payload.remember),
        user=_brief(user),
    )


@router.post("/login", response_model=AuthResult)
async def login(
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: LoginRequest,
):
    """密码登录：account 传账号名或邮箱，两者都认。"""
    account = normalize_identifier(payload.account)
    user = await _find_by_identifier(db, account)

    if user is None:
        raise BusinessError(ERR_BAD_CREDENTIALS, "账号或密码错误，请核对账号与密码后重试，忘记密码可点击「忘记密码」重置", 401)
    if not user.password_hash:
        # 验证码登录自动创建的账号本来就没密码，直接点明该走哪条路，别让用户干猜
        raise BusinessError(
            ERR_PASSWORD_NOT_SET,
            "该账号还没有设置密码，请改用「邮箱验证码登录」；"
            "登录后可在用户中心设置密码",
            400,
        )
    if not verify_password(payload.password, user.password_hash):
        raise BusinessError(ERR_BAD_CREDENTIALS, "账号或密码错误，请核对账号与密码后重试，忘记密码可点击「忘记密码」重置", 401)
    if not user.is_active:
        raise BusinessError(ERR_ACCOUNT_DISABLED, "账号已被停用，请联系管理员", 401)

    # 登录成功：刷新「最近活跃」时间（管理端用户列表展示用）
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return AuthResult(
        token=create_login_token(user.id, payload.remember),
        user=_brief(user),
    )


@router.post("/email-code")
async def send_email_code(
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: EmailCodeRequest,
):
    """发送邮箱验证码（匿名可用）。

    - scene=login：登录 / 注册 / 用户中心绑定邮箱共用。`account` 必须是一个邮箱，
      该邮箱还没有账号也没关系——验证通过会自动建号。
    - scene=reset：重置密码用。`account` 可以是账号或邮箱：先定位账号，再把验证码
      发到**该账号绑定的邮箱**上，所以用账号名也能发起重置。账号没绑邮箱就直接告知，
      免得用户等一封永远不来的信。
      （这会暴露「某标识是否注册过」，但对自建的单租户工具来说，可用性更重要。）
    """
    raw = normalize_identifier(payload.account)

    if payload.scene == email_code_service.SCENE_RESET:
        user = await _find_by_identifier(db, raw)
        if user is None:
            raise BusinessError(ERR_USER_NOT_FOUND, "该账号或邮箱还没有注册，请先注册后再登录", 404)
        target = _require_bound_email(user)
    else:
        # 登录/绑定场景必须给邮箱：验证码就是发到这个地址来证明归属的
        target = require_valid_email(raw)

    await email_code_service.send_code(target, payload.scene)
    return {"ok": True}


@router.post("/login-by-code", response_model=AuthResult)
async def login_by_code(
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: CodeLoginRequest,
):
    """邮箱验证码登录。

    邮箱还没有账号时**自动创建**：账号名取邮箱本地部分（不含 `@`），并保证合法且不与
    其它账号名 / 邮箱撞车。自动建的账号没有密码，想用密码登录可以在用户中心补设，
    或者把账号名改成自己想要的。
    """
    email = require_valid_email(payload.email)
    await email_code_service.verify_code(
        email, email_code_service.SCENE_LOGIN, payload.code
    )

    user = await _find_by_identifier(db, email)
    if user is None:
        # 邮箱首次登录：自动建号。账号名取邮箱本地部分（不含 @），并清洗 / 去重，
        # 详见 derive_username_from_email（与注册 / 改账号走同一套命名空间口径）
        username = await derive_username_from_email(db, email)
        user = User(
            username=username,
            email=email,
            password_hash=None,
            password_length=None,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    if not user.is_active:
        raise BusinessError(ERR_ACCOUNT_DISABLED, "账号已被停用，请联系管理员", 401)

    # 登录成功：刷新「最近活跃」时间（管理端用户列表展示用）
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return AuthResult(
        token=create_login_token(user.id, payload.remember),
        user=_brief(user),
    )


@router.post("/reset-password", response_model=AuthResult)
async def reset_password(
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: ResetPasswordRequest,
):
    """用邮箱验证码重置密码；成功后直接登录，省掉一次重复输入。

    `account` 可以是账号或邮箱；验证码是发在该账号**绑定的邮箱**上的。
    """
    account = normalize_identifier(payload.account)
    user = await _find_by_identifier(db, account)
    if user is None:
        raise BusinessError(ERR_USER_NOT_FOUND, "该账号或邮箱还没有注册，请先注册后再登录", 404)

    email = _require_bound_email(user)
    await email_code_service.verify_code(
        email, email_code_service.SCENE_RESET, payload.code
    )

    if not user.is_active:
        raise BusinessError(ERR_ACCOUNT_DISABLED, "账号已被停用，请联系管理员", 401)

    user.password_hash = hash_password(payload.new_password)
    user.password_length = len(payload.new_password)
    await db.commit()
    await db.refresh(user)

    return AuthResult(
        token=create_login_token(user.id, False),
        user=_brief(user),
    )


@router.post("/refresh", response_model=AuthResult)
async def refresh_token(
    payload: RefreshRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """令牌续期：用当前**仍有效**的令牌换发一个新令牌，避免「即将过期」被迫重新登录。

    依赖 get_current_user —— 令牌必须还没过期才能通过；真正过期后这里会以 40102 拒绝，
    前端此时应走「到点强退」。所以续期只发生在「尚未过期、但前端已提前提醒」的窗口内。
    remember 由前端从本地偏好带过来，保持新令牌时长与原登录一致。
    """
    return AuthResult(
        token=create_login_token(current_user.id, payload.remember),
        user=_brief(current_user),
    )


@router.get("/me", response_model=UserOut)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """当前登录用户（请求头需带 Bearer 令牌）。"""
    return current_user
