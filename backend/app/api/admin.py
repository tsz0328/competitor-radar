"""管理员接口：系统级全局设置（SMTP 发件配置）+ 用户管理。

只有 is_admin 的用户能访问；普通用户命中这些端点会收到 403。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import (
    ERR_COMPETITOR_NOT_FOUND,
    ERR_EMAIL_INVALID,
    ERR_FORBIDDEN,
    ERR_INVALID_ICON,
    ERR_PASSWORD_TOO_SHORT,
    ERR_USER_NOT_FOUND,
    BusinessError,
)
from app.core.security import hash_password
from app.core.validators import (
    is_valid_email,
    normalize_account,
    require_valid_account,
)
from app.models import (
    AppSetting,
    Competitor,
    CrawlLog,
    EventRead,
    IconLibrary,
    IntelligenceEvent,
    LlmProvider,
    MonitorSource,
    PageSnapshot,
    TrendInsight,
    User,
    WeeklyReport,
)
from app.api.competitors import _with_change_counts
from app.schemas.competitor import CompetitorOut
from app.services import icon_library
from app.services.accounts import assert_identifier_free
from app.services.system_settings import (
    get_effective_smtp_config,
    set_value,
)

settings = get_settings()

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
        if value and not is_valid_email(value):
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

    - username 是**登录账号名**（不再是邮箱，两者已解绑），改它只动 username 一列；
    - is_active=False 表示停用（无法登录）；
    - is_admin 可调整管理员权限；
    - new_password 非空表示重置该用户密码（至少 6 位）。

    注意：这里**不能改邮箱**。邮箱是第二登录标识 + 通知收件人 + 重置密码的收件人，
    换绑需要验证码证明新邮箱归属。管理员真要帮用户换，走「用户自己登录后在
    用户中心绑定」，或直接改库（邮箱本质是身份凭据，不该有免验证的旁路）。
    """

    # 长度下限交给 require_valid_account 按同一套口径判断（3–30 位）；
    # 这里放宽成 1，是为了不拦下**存量**的历史账号名（早期可能有超短的）
    username: str | None = Field(default=None, min_length=1, max_length=100)
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
    """修改用户：账号名 / 角色 / 启用状态 / 重置密码（均可选）。"""
    user = await db.get(User, user_id)
    if user is None:
        raise BusinessError(ERR_USER_NOT_FOUND, "用户不存在", 404)

    if payload.username is not None:
        new_name = normalize_account(payload.username)
        # 只有**真的改了**才做格式与唯一性校验：管理页保存时会把原值一起提交，
        # 而存量账号名可能是邮箱形态（自动建号的账号 username 就是邮箱，含 @），
        # 一律重校验会让「只想改个启用状态」直接失败。
        if new_name != user.username:
            require_valid_account(new_name)
            # 账号名与邮箱共享同一命名空间，改名前必须确认没撞别人的邮箱
            await assert_identifier_free(db, new_name, exclude_user_id=user.id)
            user.username = new_name

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


# ==================== 竞品图标管理（仅管理员） ====================


class AdminCompetitorOut(CompetitorOut):
    """管理员视角的竞品条目：在常规响应之上补充所有者信息。"""

    owner_username: str = ""
    owner_nickname: str = ""


class IconUploadOut(BaseModel):
    """图标上传结果：竞品新的图标地址（后端托管的 /api/icons/... 相对路径）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    logo_url: str


@router.get("/competitors", response_model=list[AdminCompetitorOut])
async def list_all_competitors(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
    keyword: str | None = None,
):
    """全部用户（未删除）的竞品列表，仅管理员；keyword 可选按名称/官网模糊匹配。"""
    stmt = select(Competitor).where(Competitor.deleted_at.is_(None)).order_by(Competitor.id)
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Competitor.name.ilike(like), Competitor.official_url.ilike(like)))
    rows = list((await db.execute(stmt)).scalars().all())

    user_ids = {c.user_id for c in rows}
    users: dict[int, User] = {}
    if user_ids:
        users = {
            u.id: u
            for u in (
                await db.execute(select(User).where(User.id.in_(user_ids)))
            ).scalars().all()
        }

    out: list[AdminCompetitorOut] = []
    for item in await _with_change_counts(db, rows):
        owner = users.get(item.user_id)
        out.append(
            AdminCompetitorOut(
                **item.model_dump(),
                owner_username=owner.username if owner else "",
                owner_nickname=owner.nickname if owner else "",
            )
        )
    return out


@router.post("/competitors/{competitor_id}/icon", response_model=IconUploadOut)
async def upload_competitor_icon(
    competitor_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    file: Annotated[UploadFile, File(description="图标图片（png/jpeg/webp/gif，≤2MB）")],
):
    """管理员上传/替换竞品图标：写磁盘 + 记图标库，同域名竞品一并换图。

    图标库按规范化域名（小写、去 www）做唯一 key：上传一次后，该域名下的
    所有竞品（含其他用户添加的）都改用后端托管的图标，与外部站点解耦。
    """
    competitor = await db.get(Competitor, competitor_id)
    if competitor is None or competitor.deleted_at is not None:
        raise BusinessError(ERR_COMPETITOR_NOT_FOUND, "竞品不存在", 404)

    # 只收白名单位图格式：svg 可内嵌脚本，有 XSS 面，一律拒收
    content_type = (file.content_type or "").strip().lower()
    ext = icon_library.ext_for_content_type(content_type)
    if ext is None:
        raise BusinessError(ERR_INVALID_ICON, "仅支持 PNG / JPG / WebP / GIF 格式的图片", 400)

    host = icon_library.normalize_host(competitor.official_url)
    if not host:
        raise BusinessError(ERR_INVALID_ICON, "该竞品缺少官网地址，无法确定图标域名", 400)

    data = await file.read()
    if not data:
        raise BusinessError(ERR_INVALID_ICON, "图标文件内容为空", 400)
    if len(data) > settings.icon_max_bytes:
        raise BusinessError(ERR_INVALID_ICON, "图标文件过大（上限 2MB）", 400)

    file_name = icon_library.new_file_name(content_type)
    (icon_library.icons_dir() / file_name).write_bytes(data)

    row = await icon_library.find_by_domain(db, host)
    if row is None:
        db.add(
            IconLibrary(
                domain=host,
                file_name=file_name,
                content_type=content_type,
                size=len(data),
                uploaded_by=admin.id,
            )
        )
    else:
        # 替换上传：清掉旧文件，更新元信息
        if row.file_name != file_name:
            (icon_library.icons_dir() / row.file_name).unlink(missing_ok=True)
        row.file_name = file_name
        row.content_type = content_type
        row.size = len(data)
        row.uploaded_by = admin.id

    # 图标库是域名级事实源：同域名的所有竞品（含其他用户的）一并换用新图标
    url = icon_library.public_icon_url(file_name)
    others = (
        await db.execute(select(Competitor).where(Competitor.deleted_at.is_(None)))
    ).scalars().all()
    for other in others:
        if icon_library.normalize_host(other.official_url) == host:
            other.logo_url = url

    await db.commit()

    # 清掉官网解析缓存（favicon.clean_host 保留 www，两个 key 都要清）
    cache = get_cache()
    await cache.delete(f"favicon:{host}")
    await cache.delete(f"favicon:www.{host}")

    return IconUploadOut(logo_url=url)
