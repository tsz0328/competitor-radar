"""管理员接口：系统级全局设置（SMTP 发件配置）+ 用户管理。

只有 is_admin 的用户能访问；普通用户命中这些端点会收到 403。
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import (
    ERR_ACCOUNT_EXISTS,
    ERR_EMAIL_INVALID,
    ERR_FORBIDDEN,
    ERR_PASSWORD_TOO_SHORT,
    ERR_USER_NOT_FOUND,
    BusinessError,
)
from app.core.security import hash_password
from app.models import (
    AppSetting,
    Competitor,
    CrawlLog,
    EventRead,
    IntelligenceEvent,
    LlmProvider,
    MonitorSource,
    PageSnapshot,
    TrendInsight,
    User,
    WeeklyReport,
)
from app.services.system_settings import (
    get_effective_smtp_config,
    set_value,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def get_current_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """管理员鉴权：非管理员直接 403。"""
    if not current_user.is_admin:
        raise BusinessError(ERR_FORBIDDEN, "需要管理员权限", 403)
    return current_user


class SystemSettingsOut(BaseModel):
    """系统设置回显。

    授权码（smtp_password）出于安全不回传明文，只回传 smtp_password_set 表示是否已配置；
    前端授权码栏永远显示空、靠"留空=不修改"。
    """

    smtp_host: str = ""
    smtp_port: int = 0
    smtp_username: str = ""
    smtp_sender: str = ""
    # 授权码是否已配置（不回传明文，仅给界面显示"已设置/未设置"）
    smtp_password_set: bool = False
    # 注意：smtp_password 不在此返回


def _settings_out(
    stored_host: str,
    stored_port: str,
    stored_user: str,
    stored_sender: str,
    password_set: bool,
) -> SystemSettingsOut:
    """组装回显（端口转 int；0 表示未覆盖）。"""
    return SystemSettingsOut(
        smtp_host=stored_host,
        smtp_port=int(stored_port) if stored_port else 0,
        smtp_username=stored_user,
        smtp_sender=stored_sender,
        smtp_password_set=password_set,
    )


class SystemSettingsUpdate(BaseModel):
    """系统设置更新入参：所有字段都可单独提交，未传的保持不变。

    - smtp_host / smtp_port / smtp_username / smtp_sender：传空串表示清掉覆盖、回退 .env；
    - smtp_password：传空串表示"不改动"（保留库里已有值）；只有传非空才更新。
    """

    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_sender: str | None = None
    smtp_password: str | None = None


@router.get("/system-settings", response_model=SystemSettingsOut)
async def get_system_settings(_: Annotated[User, Depends(get_current_admin)]):
    """读取系统设置（返回运行时生效值：库覆盖优先，否则回退 .env；授权码不回传）。"""
    cfg = await get_effective_smtp_config()
    return _settings_out(
        cfg["host"],
        str(cfg["port"]),
        cfg["username"],
        cfg["sender"],
        password_set=bool(cfg["password"]),
    )


@router.put("/system-settings", response_model=SystemSettingsOut)
async def update_system_settings(
    payload: SystemSettingsUpdate,
    _: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """保存系统设置：SMTP 五项（授权码留空=不改动）。"""
    # 发件邮箱格式校验（仅当本次提交了非空值时）
    if payload.smtp_sender is not None:
        value = payload.smtp_sender.strip()
        if value:
            if (
                "@" not in value
                or " " in value
                or value.startswith("@")
                or value.endswith("@")
            ):
                raise BusinessError(ERR_EMAIL_INVALID, "发件邮箱格式不正确", 400)
        await set_value(db, "smtp_sender", value)

    # 服务器 / 端口 / 用户名：提交即覆盖（空串=清掉，回退 .env）
    if payload.smtp_host is not None:
        await set_value(db, "smtp_host", payload.smtp_host.strip())
    if payload.smtp_port is not None:
        await set_value(db, "smtp_port", str(payload.smtp_port))
    if payload.smtp_username is not None:
        await set_value(db, "smtp_username", payload.smtp_username.strip())

    # 授权码：非空才更新；空串或 None 表示保留当前值
    if payload.smtp_password is not None and payload.smtp_password != "":
        await set_value(db, "smtp_password", payload.smtp_password)

    # 回显生效值（库覆盖优先，否则 .env）
    cfg = await get_effective_smtp_config()
    return _settings_out(
        cfg["host"],
        str(cfg["port"]),
        cfg["username"],
        cfg["sender"],
        password_set=bool(cfg["password"]),
    )


# ==================== 用户管理（仅管理员） ====================


class AdminUserOut(BaseModel):
    """用户管理列表项（不回传头像 data URL，避免列表响应过大）。"""

    id: int
    username: str
    email: str = ""
    is_admin: bool = False
    is_active: bool = True
    # 密码位数（仅长度，不暴露明文）；NULL 表示未知
    password_length: int | None = None


class AdminUserUpdate(BaseModel):
    """管理员修改用户：只传要改的字段。

    - is_active=False 表示停用（无法登录）；
    - is_admin 可调整管理员权限；
    - new_password 非空表示重置该用户密码（至少 6 位）。
    """

    username: str | None = Field(default=None, min_length=1, max_length=50)
    email: str | None = Field(default=None, max_length=100)
    is_admin: bool | None = None
    is_active: bool | None = None
    new_password: str | None = Field(default=None, max_length=72)


def _admin_user_out(user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        username=user.username,
        email=user.email or "",
        is_admin=user.is_admin,
        is_active=user.is_active,
        password_length=user.password_length,
    )


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
    keyword: str | None = None,
):
    """用户列表（按 id 升序）。keyword 可选，按账号或邮箱模糊匹配。"""
    stmt = select(User).order_by(User.id)
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.email.ilike(like)))
    rows = (await db.execute(stmt)).scalars().all()
    return [_admin_user_out(u) for u in rows]


@router.put("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
):
    """修改用户：账号 / 通知邮箱 / 角色 / 启用状态 / 重置密码（均可选）。"""
    user = await db.get(User, user_id)
    if user is None:
        raise BusinessError(ERR_USER_NOT_FOUND, "用户不存在", 404)

    if payload.username is not None:
        new_name = payload.username.strip()
        if not new_name:
            raise BusinessError(ERR_ACCOUNT_EXISTS, "账号不能为空", 400)
        if new_name != user.username:
            exists = await db.execute(
                select(User).where(User.username == new_name)
            )
            if exists.scalar_one_or_none() is not None:
                raise BusinessError(ERR_ACCOUNT_EXISTS, "账号已存在", 400)
            user.username = new_name

    if payload.email is not None:
        email = payload.email.strip()
        if email and (
            "@" not in email
            or " " in email
            or email.startswith("@")
            or email.endswith("@")
        ):
            raise BusinessError(ERR_EMAIL_INVALID, "邮箱格式不正确", 400)
        user.email = email or None

    if payload.is_admin is not None:
        if user.id == admin.id and payload.is_admin is False:
            raise BusinessError(ERR_FORBIDDEN, "不能取消自己的管理员权限", 400)
        user.is_admin = payload.is_admin

    if payload.is_active is not None:
        if user.id == admin.id and payload.is_active is False:
            raise BusinessError(ERR_FORBIDDEN, "不能停用当前登录账号", 400)
        user.is_active = payload.is_active

    if payload.new_password:
        if len(payload.new_password) < 6:
            raise BusinessError(ERR_PASSWORD_TOO_SHORT, "新密码至少 6 位", 400)
        user.password_hash = hash_password(payload.new_password)
        user.password_length = len(payload.new_password)

    await db.commit()
    await db.refresh(user)
    return _admin_user_out(user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
):
    """删除用户：连同其名下竞品、监控源、快照、情报、报告、日志等一并清理。

    不允许删除当前登录账号；删除后该用户令牌失效（下次请求 401）。
    """
    if user_id == admin.id:
        raise BusinessError(ERR_FORBIDDEN, "不能删除当前登录账号", 400)
    user = await db.get(User, user_id)
    if user is None:
        raise BusinessError(ERR_USER_NOT_FOUND, "用户不存在", 404)

    # 该用户名下竞品 → 由其派生出的源 / 事件 / 快照 / 趋势
    competitor_ids = select(Competitor.id).where(Competitor.user_id == user_id)
    event_ids = select(IntelligenceEvent.id).where(
        IntelligenceEvent.competitor_id.in_(competitor_ids)
    )

    # 顺序：先删引用方（已读/通知 → 事件 → 快照/趋势 → 源 → 竞品），再删用户自身数据
    await db.execute(delete(EventRead).where(EventRead.user_id == user_id))
    await db.execute(delete(EventRead).where(EventRead.event_id.in_(event_ids)))
    await db.execute(
        delete(IntelligenceEvent).where(
            IntelligenceEvent.competitor_id.in_(competitor_ids)
        )
    )
    await db.execute(
        delete(PageSnapshot).where(PageSnapshot.competitor_id.in_(competitor_ids))
    )
    await db.execute(
        delete(TrendInsight).where(TrendInsight.competitor_id.in_(competitor_ids))
    )
    await db.execute(
        delete(MonitorSource).where(MonitorSource.competitor_id.in_(competitor_ids))
    )
    await db.execute(delete(Competitor).where(Competitor.user_id == user_id))
    await db.execute(delete(WeeklyReport).where(WeeklyReport.user_id == user_id))
    await db.execute(delete(CrawlLog).where(CrawlLog.user_id == user_id))
    await db.execute(delete(LlmProvider).where(LlmProvider.user_id == user_id))
    await db.execute(delete(AppSetting).where(AppSetting.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    return {"ok": True}
