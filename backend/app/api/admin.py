"""管理员接口：系统级全局设置（SMTP 发件配置）+ 用户管理。

只有 is_admin 的用户能访问；普通用户命中这些端点会收到 403。
"""
import smtplib
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.announcements import AnnouncementOut
from app.api.deps import get_current_user
from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import (
    ERR_ANNOUNCEMENT_INVALID,
    ERR_COMPETITOR_NOT_FOUND,
    ERR_EMAIL_INVALID,
    ERR_FORBIDDEN,
    ERR_INVALID_ICON,
    ERR_PASSWORD_TOO_SHORT,
    ERR_USER_NOT_FOUND,
    BusinessError,
)
from app.core.security import hash_password
from app.core.timeutil import format_time
from app.core.validators import (
    is_valid_email,
    normalize_account,
    require_valid_account,
)
from app.models import (
    AdminAuditLog,
    Announcement,
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
from app.api.competitors import _self_heal_logos, _with_change_counts
from app.core.event_types import EVENT_TYPE_LABELS
from app.schemas.competitor import CompetitorOut
from app.services import admin_stats, favicon, icon_library, notifier
from app.services.accounts import assert_identifier_free
from app.services.system_settings import (
    encrypt_smtp_password,
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
        raise BusinessError(ERR_FORBIDDEN, "需要管理员权限，请使用管理员账号登录后操作", 403)
    return current_user


def _write_audit(
    db: AsyncSession,
    admin: User,
    action: str,
    target_type: str,
    target_id: int | None,
    detail: str,
) -> None:
    """追加一条审计日志（不 commit：与业务变更同事务提交，成功必有日志）。"""
    db.add(
        AdminAuditLog(
            admin_id=admin.id,
            admin_username=admin.username,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
    )


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
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """保存系统设置：SMTP 五项（授权码留空=不改动）。"""
    changes: list[str] = []
    # 发件邮箱格式校验（仅当本次提交了非空值时）
    if payload.smtp_sender is not None:
        value = payload.smtp_sender.strip()
        if value and not is_valid_email(value):
            raise BusinessError(ERR_EMAIL_INVALID, "发件邮箱格式不正确，请检查后重新填写", 400)
        await set_value(db, "smtp_sender", value)
        changes.append(f"smtp_sender={value or '(清空)'}")

    # 服务器 / 端口 / 用户名：提交即覆盖（空串=清掉，回退 .env）
    if payload.smtp_host is not None:
        await set_value(db, "smtp_host", payload.smtp_host.strip())
        changes.append(f"smtp_host={payload.smtp_host.strip() or '(清空)'}")
    if payload.smtp_port is not None:
        await set_value(db, "smtp_port", str(payload.smtp_port))
        changes.append(f"smtp_port={payload.smtp_port}")
    if payload.smtp_username is not None:
        await set_value(db, "smtp_username", payload.smtp_username.strip())
        changes.append(f"smtp_username={payload.smtp_username.strip() or '(清空)'}")

    # 授权码：非空才更新；空串或 None 表示保留当前值（落库前加密，不写审计明细）
    if payload.smtp_password is not None and payload.smtp_password != "":
        await set_value(db, "smtp_password", encrypt_smtp_password(payload.smtp_password))
        changes.append("smtp_password=***")

    if changes:
        _write_audit(
            db,
            admin,
            "update_system_settings",
            "system_settings",
            None,
            "；".join(changes),
        )
        await db.commit()

    # 回显生效值（库覆盖优先，否则 .env）
    cfg = await get_effective_smtp_config()
    return _settings_out(
        cfg["host"],
        str(cfg["port"]),
        cfg["username"],
        cfg["sender"],
        password_set=bool(cfg["password"]),
    )


class TestEmailRequest(BaseModel):
    """测试邮件收件人（默认由前端带当前管理员的绑定邮箱）。"""

    to: str


class TestEmailResult(BaseModel):
    """测试发信结果：成功与否都返回 200，失败原因放 error 里展示给管理员。"""

    ok: bool
    message: str


def _friendly_smtp_error(exc: Exception) -> str:
    """把 SMTP 发信异常翻译成可照着排查的中文提示（管理员测试发信时展示）。"""
    detail = str(exc)[:120] or type(exc).__name__
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        hint = "SMTP 认证失败：请检查发件账号和密码/授权码（第三方邮箱通常要用授权码而非登录密码）"
    elif isinstance(exc, smtplib.SMTPRecipientsRefused):
        hint = "收件人被拒：请确认收件邮箱存在且未停用"
    elif isinstance(exc, smtplib.SMTPServerDisconnected):
        hint = "SMTP 服务器断开连接：请检查端口与加密方式是否匹配（465 用 SSL，587 用 STARTTLS）"
    elif isinstance(exc, TimeoutError):
        hint = "连接 SMTP 服务器超时：请检查网络与服务器地址、端口"
    elif isinstance(exc, smtplib.SMTPException) or isinstance(exc, OSError):
        hint = "无法连接 SMTP 服务器：请检查服务器地址与端口（465 用 SSL，587 用 STARTTLS）"
    else:
        hint = "发送失败，请检查 SMTP 配置后重试"
    return f"{hint}（详情：{detail}）"


@router.post("/system-settings/test-email", response_model=TestEmailResult)
async def test_email(
    payload: TestEmailRequest,
    _: Annotated[User, Depends(get_current_admin)],
):
    """用当前生效的 SMTP 配置给指定收件人发一封测试邮件（同步等待结果）。"""
    to = payload.to.strip()
    if not is_valid_email(to):
        raise BusinessError(ERR_EMAIL_INVALID, "收件邮箱格式不正确，请检查后重新填写", 400)

    cfg = await get_effective_smtp_config()
    try:
        await notifier.send_test_email(cfg, to)
    except Exception as exc:  # noqa: BLE001 - 把失败原因带给前端，供管理员排查配置
        return TestEmailResult(ok=False, message=_friendly_smtp_error(exc))
    return TestEmailResult(ok=True, message=f"测试邮件已发送至 {to}，请查收。")


# ==================== 平台总览（仅管理员） ====================


class AdminOverviewTotals(BaseModel):
    """平台全局总量（竞品/周报只计未删除的；事件/抓取日志是全量历史）。"""

    users: int = 0
    active_users: int = 0
    admin_users: int = 0
    competitors: int = 0
    sources: int = 0
    events: int = 0
    reports: int = 0
    crawl_logs: int = 0


class AdminDailyPoint(BaseModel):
    """单日计数点：date 用于 x 轴展示（如 9/15），date_iso 用于对齐与钻取。"""

    date: str
    date_iso: str
    count: int = 0


class AdminOverviewOut(BaseModel):
    """平台总览：总量卡片 + 情报/抓取两条近 30 天趋势线。"""

    totals: AdminOverviewTotals
    event_trend: list[AdminDailyPoint]
    crawl_trend: list[AdminDailyPoint]


@router.get("/overview", response_model=AdminOverviewOut)
async def get_overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
):
    """平台总览统计：全局总量 + 近 30 天情报事件/抓取趋势（跨全部用户）。

    总量走 5 分钟 TTL 的内存缓存（跨用户聚合较贵），趋势线实时查询。
    """
    days = admin_stats.OVERVIEW_TREND_DAYS
    return AdminOverviewOut(
        totals=AdminOverviewTotals(**await admin_stats.overview_totals_cached(db)),
        event_trend=await admin_stats.build_global_daily_series(
            db, days, IntelligenceEvent.created_at
        ),
        crawl_trend=await admin_stats.build_global_daily_series(
            db, days, CrawlLog.created_at
        ),
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
    # 注册时间 / 最近活跃（本地时区格式化；last_login_at 为空 = 从未登录）
    created_at: str = ""
    last_login_at: str = ""
    # 该用户名下数据统计（竞品/周报只计未删除，事件/抓取日志为全量）
    competitor_count: int = 0
    event_count: int = 0
    report_count: int = 0
    crawl_log_count: int = 0


class AdminUserPage(BaseModel):
    """用户列表分页响应。"""

    items: list[AdminUserOut]
    total: int


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


def _admin_user_out(user: User, stats: dict[str, int] | None = None) -> AdminUserOut:
    stats = stats or {}
    return AdminUserOut(
        id=user.id,
        username=user.username,
        email=user.email or "",
        is_admin=user.is_admin,
        is_active=user.is_active,
        password_length=user.password_length,
        created_at=format_time(user.created_at),
        last_login_at=format_time(user.last_login_at),
        competitor_count=stats.get("competitor_count", 0),
        event_count=stats.get("event_count", 0),
        report_count=stats.get("report_count", 0),
        crawl_log_count=stats.get("crawl_log_count", 0),
    )


@router.get("/users", response_model=AdminUserPage)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """用户列表（按 id 升序），每行带该用户名下数据统计。

    keyword 可选，按账号或邮箱模糊匹配；page/page_size 分页（page_size 上限 100）。
    统计用「子查询 + outerjoin + coalesce」隔离计数，避免多表一对多 join
    同时 count 导致计数翻倍。
    """
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    competitor_sub, event_sub, report_sub, crawl_sub = (
        admin_stats.user_stat_subqueries()
    )
    base = (
        select(
            User,
            func.coalesce(competitor_sub.c.cnt, 0).label("competitor_count"),
            func.coalesce(event_sub.c.cnt, 0).label("event_count"),
            func.coalesce(report_sub.c.cnt, 0).label("report_count"),
            func.coalesce(crawl_sub.c.cnt, 0).label("crawl_log_count"),
        )
        .outerjoin(competitor_sub, competitor_sub.c.user_id == User.id)
        .outerjoin(event_sub, event_sub.c.user_id == User.id)
        .outerjoin(report_sub, report_sub.c.user_id == User.id)
        .outerjoin(crawl_sub, crawl_sub.c.user_id == User.id)
    )
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        base = base.where(or_(User.username.ilike(like), User.email.ilike(like)))

    total = int(
        (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = (
        await db.execute(
            base.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()

    return AdminUserPage(
        items=[
            _admin_user_out(
                row.User,
                {
                    "competitor_count": row.competitor_count,
                    "event_count": row.event_count,
                    "report_count": row.report_count,
                    "crawl_log_count": row.crawl_log_count,
                },
            )
            for row in rows
        ],
        total=total,
    )


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
        raise BusinessError(ERR_USER_NOT_FOUND, "用户不存在或已被删除，请刷新后重试", 404)

    changes: list[str] = []
    if payload.username is not None:
        new_name = normalize_account(payload.username)
        # 只有**真的改了**才做格式与唯一性校验：管理页保存时会把原值一起提交，
        # 而存量账号名可能是邮箱形态（自动建号的账号 username 就是邮箱，含 @），
        # 一律重校验会让「只想改个启用状态」直接失败。
        if new_name != user.username:
            require_valid_account(new_name)
            # 账号名与邮箱共享同一命名空间，改名前必须确认没撞别人的邮箱
            await assert_identifier_free(db, new_name, exclude_user_id=user.id)
            changes.append(f"账号: {user.username}→{new_name}")
            user.username = new_name

    if payload.is_admin is not None:
        if user.id == admin.id and payload.is_admin is False:
            raise BusinessError(ERR_FORBIDDEN, "不能取消自己的管理员权限", 400)
        if payload.is_admin != user.is_admin:
            changes.append(
                f"角色: {'普通用户' if user.is_admin else '管理员'}"
                f"→{'管理员' if payload.is_admin else '普通用户'}"
            )
        user.is_admin = payload.is_admin

    if payload.is_active is not None:
        if user.id == admin.id and payload.is_active is False:
            raise BusinessError(ERR_FORBIDDEN, "不能停用当前登录账号", 400)
        if payload.is_active != user.is_active:
            changes.append(f"状态: {'停用' if user.is_active else '启用'}→{'启用' if payload.is_active else '停用'}")
        user.is_active = payload.is_active

    if payload.new_password:
        if len(payload.new_password) < 6:
            raise BusinessError(ERR_PASSWORD_TOO_SHORT, "新密码至少 6 位", 400)
        user.password_hash = hash_password(payload.new_password)
        user.password_length = len(payload.new_password)
        changes.append("重置密码")

    if changes:
        _write_audit(db, admin, "update_user", "user", user.id, "；".join(changes))
    else:
        # 什么都没改：直接回显原样（也避免 commit 触发不必要的缓存失效）
        return _admin_user_out(user)

    await db.commit()
    await db.refresh(user)
    admin_stats.invalidate_overview_cache()
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
        raise BusinessError(ERR_USER_NOT_FOUND, "用户不存在或已被删除，请刷新后重试", 404)

    deleted_name = user.username
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
    # 审计与删除同事务提交；用户行已删，把账号名留在 detail 里备查
    _write_audit(db, admin, "delete_user", "user", user_id, f"删除用户 {deleted_name} 及其名下数据")
    await db.commit()
    admin_stats.invalidate_overview_cache()
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


class BackfillIconsOut(BaseModel):
    """全量回填竞品图标的结果。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    changed: int


class AdminCompetitorPage(BaseModel):
    """全部竞品分页响应。"""

    items: list[AdminCompetitorOut]
    total: int


@router.get("/competitors", response_model=AdminCompetitorPage)
async def list_all_competitors(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """全部用户（未删除）的竞品列表，仅管理员；keyword 可选按名称/官网模糊匹配。

    page/page_size 分页（page_size 上限 100）。
    """
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    base = select(Competitor).where(Competitor.deleted_at.is_(None))
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        base = base.where(or_(Competitor.name.ilike(like), Competitor.official_url.ilike(like)))

    total = int(
        (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = list(
        (
            await db.execute(base.order_by(Competitor.id).offset((page - 1) * page_size).limit(page_size))
        ).scalars().all()
    )

    user_ids = {c.user_id for c in rows}
    users: dict[int, User] = {}
    if user_ids:
        users = {
            u.id: u
            for u in (
                await db.execute(select(User).where(User.id.in_(user_ids)))
            ).scalars().all()
        }

    items = await _with_change_counts(db, rows)
    # 读取时把 logo_url 对齐到图标库当前值（与用户端列表/详情一致的自愈逻辑），
    # 避免管理端平台列表展示陈旧/外链的图标（如「重新获取」抓到 SVG 退化成的外链）。
    await _self_heal_logos(db, rows, items)

    out: list[AdminCompetitorOut] = []
    for item in items:
        owner = users.get(item.user_id)
        out.append(
            AdminCompetitorOut(
                **item.model_dump(),
                owner_username=owner.username if owner else "",
                owner_nickname=owner.nickname if owner else "",
            )
        )
    return AdminCompetitorPage(items=out, total=total)


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
        raise BusinessError(ERR_COMPETITOR_NOT_FOUND, "竞品不存在或已被删除，请刷新列表后重试", 404)

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

    _write_audit(
        db,
        admin,
        "upload_competitor_icon",
        "competitor",
        competitor_id,
        f"上传/替换图标 {competitor.name}（{host}）",
    )
    await db.commit()

    # 清掉官网解析缓存（favicon.clean_host 保留 www，两个 key 都要清）
    cache = get_cache()
    await cache.delete(f"favicon:{host}")
    await cache.delete(f"favicon:www.{host}")

    return IconUploadOut(logo_url=url)


@router.post("/competitors/{competitor_id}/refresh-icon", response_model=IconUploadOut)
async def refresh_competitor_icon(
    competitor_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
):
    """管理员重新获取竞品图标：按官网地址用修复后的逻辑重新解析并沉淀进共享图标库。

    与「上传图标」不同，这里不要求人工提供图片，而是自动去官网抓 favicon。
    复用 favicon._probe 的修复逻辑：官网域名若跨域跳转（被收购/停放）会放弃解析并返回提示，
    避免把别的站点的图标当成该竞品的。解析到的图标按域名沉淀进共享库，同域名竞品一并换图。
    """
    competitor = await db.get(Competitor, competitor_id)
    if competitor is None or competitor.deleted_at is not None:
        raise BusinessError(ERR_COMPETITOR_NOT_FOUND, "竞品不存在或已被删除，请刷新列表后重试", 404)

    host = icon_library.normalize_host(competitor.official_url)
    if not host:
        raise BusinessError(ERR_INVALID_ICON, "该竞品缺少官网地址，无法重新获取图标，请先补全官网", 400)

    candidate = await favicon._probe(host)
    if not candidate:
        raise BusinessError(
            ERR_INVALID_ICON,
            "无法从该竞品官网解析到图标（官网可能跨域跳转、无可用 favicon 或已下线），建议改用「上传图标」手动提供",
            400,
        )

    # 沉淀进跨用户共享图标库；不支持入库的格式（如 SVG）退化为外链，仅本竞品使用
    logo_url = await icon_library.save_from_url(db, competitor.official_url, candidate)
    if not logo_url and await favicon.validate_icon(candidate):
        logo_url = candidate

    # 同可注册域名的竞品（含其他用户的）一并换用新图标
    domain = favicon._registrable_domain(host)
    others = (
        await db.execute(select(Competitor).where(Competitor.deleted_at.is_(None)))
    ).scalars().all()
    for other in others:
        if favicon._registrable_domain(icon_library.normalize_host(other.official_url)) == domain:
            other.logo_url = logo_url

    _write_audit(
        db,
        admin,
        "refresh_competitor_icon",
        "competitor",
        competitor_id,
        f"重新获取图标 {competitor.name}（{host}）",
    )
    await db.commit()

    cache = get_cache()
    await cache.delete(f"favicon:{host}")
    await cache.delete(f"favicon:www.{host}")

    return IconUploadOut(logo_url=logo_url)


@router.post("/icons/backfill", response_model=BackfillIconsOut)
async def backfill_competitor_icons(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
):
    """全量回填竞品图标：把所有未删除竞品的 logo_url 重新对齐到图标库当前值。

    与「上传/重新获取图标」不同，本接口不发起任何网络请求，只把图标库已有域名图标
    重新推送到各竞品记录——用于消除「竞品创建/编辑早于图标库收录该域名」的存量不一致
    （同一站点因创建时机不同而显示不同图标）。返回被改动的记录数，便于确认影响面。
    """
    changed = await icon_library.backfill_all_icons(db)
    _write_audit(
        db,
        admin,
        "backfill_competitor_icons",
        "icon_library",
        0,
        f"全量回填竞品图标，改动 {changed} 条",
    )
    return BackfillIconsOut(changed=changed)


# ==================== 审计日志（仅管理员） ====================

# 审计日志每页上限（防一次拉全表）
AUDIT_PAGE_SIZE_MAX = 100


class AuditLogOut(BaseModel):
    """审计日志回显。"""

    id: int
    admin_username: str
    action: str
    target_type: str
    target_id: int | None
    detail: str
    # 本地时区格式化时间
    created_at: str


class AuditLogPage(BaseModel):
    """审计日志分页响应。"""

    items: list[AuditLogOut]
    total: int


@router.get("/audit-logs", response_model=AuditLogPage)
async def list_audit_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
    page: int = 1,
    page_size: int = 20,
    action: str | None = None,
    keyword: str | None = None,
):
    """审计日志列表（新→旧）。action 精确匹配；keyword 模糊匹配操作人/目标。"""
    page = max(page, 1)
    page_size = min(max(page_size, 1), AUDIT_PAGE_SIZE_MAX)

    base = select(AdminAuditLog)
    if action and action.strip():
        base = base.where(AdminAuditLog.action == action.strip())
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        base = base.where(
            or_(AdminAuditLog.admin_username.ilike(like), AdminAuditLog.detail.ilike(like))
        )

    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
    rows = (
        await db.execute(
            base.order_by(AdminAuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return AuditLogPage(
        items=[
            AuditLogOut(
                id=r.id,
                admin_username=r.admin_username,
                action=r.action,
                target_type=r.target_type,
                target_id=r.target_id,
                detail=r.detail,
                created_at=format_time(r.created_at),
            )
            for r in rows
        ],
        total=total,
    )


# ==================== 用户详情（仅管理员） ====================


class AdminUserOverviewOut(BaseModel):
    """用户详情抽屉：基本资料 + 数据摘要。"""

    id: int
    username: str
    email: str = ""
    nickname: str = ""
    is_admin: bool = False
    is_active: bool = True
    created_at: str = ""
    last_login_at: str = ""
    # 数据总量
    competitor_count: int = 0
    event_count: int = 0
    report_count: int = 0
    crawl_log_count: int = 0
    # 摘要明细：竞品名 / 报告标题各取最新 5 条
    competitor_names: list[str] = []
    report_titles: list[str] = []
    # 近 30 天情报趋势
    event_trend: list[dict] = []
    # 抓取日志按 state 的成败分布
    crawl_success_count: int = 0
    crawl_fail_count: int = 0


@router.get("/users/{user_id}/overview", response_model=AdminUserOverviewOut)
async def get_user_overview(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
):
    """单个用户的聚合概况（用户管理抽屉用）。"""
    user = await db.get(User, user_id)
    if user is None:
        raise BusinessError(ERR_USER_NOT_FOUND, "用户不存在或已被删除，请刷新后重试", 404)

    competitor_names = list(
        (
            await db.execute(
                select(Competitor.name)
                .where(Competitor.user_id == user_id, Competitor.deleted_at.is_(None))
                .order_by(Competitor.id.desc())
                .limit(5)
            )
        ).scalars().all()
    )
    report_rows = (
        await db.execute(
            select(WeeklyReport.title)
            .where(WeeklyReport.user_id == user_id, WeeklyReport.deleted_at.is_(None))
            .order_by(WeeklyReport.id.desc())
            .limit(5)
        )
    ).scalars().all()

    competitor_ids = select(Competitor.id).where(Competitor.user_id == user_id)
    counts = await admin_stats.overview_totals_for_user(db, user_id, competitor_ids)

    return AdminUserOverviewOut(
        id=user.id,
        username=user.username,
        email=user.email or "",
        nickname=user.nickname or "",
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=format_time(user.created_at),
        last_login_at=format_time(user.last_login_at),
        competitor_count=counts["competitors"],
        event_count=counts["events"],
        report_count=counts["reports"],
        crawl_log_count=counts["crawl_logs"],
        competitor_names=competitor_names,
        report_titles=list(report_rows),
        event_trend=await admin_stats.build_user_daily_series(
            db, admin_stats.OVERVIEW_TREND_DAYS, IntelligenceEvent.created_at, user_id
        ),
        crawl_success_count=counts["crawl_success"],
        crawl_fail_count=counts["crawl_fail"],
    )


# ==================== 平台数据（仅管理员，「平台数据」页三 tab） ====================

DATA_PAGE_SIZE_MAX = 100


def _clamp_page(page: int, page_size: int) -> tuple[int, int]:
    """分页参数夹逼：page ≥ 1，page_size ∈ [1, 100] 防一次拉全表。"""
    return max(page, 1), min(max(page_size, 1), DATA_PAGE_SIZE_MAX)


class AdminEventOut(BaseModel):
    """跨用户情报事件条目（平台数据·情报事件 tab）。"""

    id: int
    title: str
    event_type: str
    event_type_label: str = ""
    priority: str = ""
    competitor_name: str = ""
    owner_username: str = ""
    created_at: str = ""


class AdminEventPage(BaseModel):
    items: list[AdminEventOut]
    total: int


@router.get("/events", response_model=AdminEventPage)
async def list_all_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
):
    """全部用户的情报事件，按时间倒序分页。keyword 按标题模糊匹配。"""
    page, page_size = _clamp_page(page, page_size)

    cond = []
    if keyword and keyword.strip():
        cond.append(IntelligenceEvent.title.ilike(f"%{keyword.strip()}%"))

    base = (
        select(
            IntelligenceEvent,
            Competitor.name.label("competitor_name"),
            User.username.label("owner_username"),
        )
        .outerjoin(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .outerjoin(User, User.id == Competitor.user_id)
        .where(*cond)
    )
    total = int(
        (
            await db.execute(
                select(func.count()).select_from(IntelligenceEvent).where(*cond)
            )
        ).scalar_one()
    )
    rows = (
        await db.execute(
            base.order_by(IntelligenceEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return AdminEventPage(
        items=[
            AdminEventOut(
                id=ev.id,
                title=ev.title,
                event_type=ev.event_type.value,
                event_type_label=EVENT_TYPE_LABELS.get(ev.event_type, ev.event_type.value),
                priority=ev.priority,
                competitor_name=competitor_name or "（未知竞品）",
                owner_username=owner_username or "",
                created_at=format_time(ev.created_at),
            )
            for ev, competitor_name, owner_username in rows
        ],
        total=total,
    )


class AdminReportOut(BaseModel):
    """跨用户报告条目（平台数据·周度报告 tab）。deleted 标记软删状态。"""

    id: int
    title: str
    report_type: str
    range_start: str = ""
    range_end: str = ""
    competitor_count: int = 0
    event_count: int = 0
    owner_username: str = ""
    created_at: str = ""
    deleted: bool = False


class AdminReportPage(BaseModel):
    items: list[AdminReportOut]
    total: int


@router.get("/reports", response_model=AdminReportPage)
async def list_all_reports(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    include_deleted: bool = False,
):
    """全部用户的报告，按生成时间倒序分页。keyword 按标题模糊匹配。

    默认只返回未删除（有效）报告；include_deleted=True 时一并返回软删报告，
    并用 deleted 字段标记软删状态（对应回收站里的周报）。
    """
    page, page_size = _clamp_page(page, page_size)

    cond = []
    if not include_deleted:
        cond.append(WeeklyReport.deleted_at.is_(None))
    if keyword and keyword.strip():
        cond.append(WeeklyReport.title.ilike(f"%{keyword.strip()}%"))

    base = (
        select(WeeklyReport, User.username.label("owner_username"))
        .outerjoin(User, User.id == WeeklyReport.user_id)
        .where(*cond)
    )
    total = int(
        (
            await db.execute(
                select(func.count()).select_from(WeeklyReport).where(*cond)
            )
        ).scalar_one()
    )
    rows = (
        await db.execute(
            base.order_by(WeeklyReport.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return AdminReportPage(
        items=[
            AdminReportOut(
                id=r.id,
                title=r.title,
                report_type=r.report_type.value,
                range_start=str(r.range_start),
                range_end=str(r.range_end),
                competitor_count=r.competitor_count,
                event_count=r.event_count,
                owner_username=owner_username or "",
                created_at=format_time(r.created_at),
                deleted=r.deleted_at is not None,
            )
            for r, owner_username in rows
        ],
        total=total,
    )


class AdminCrawlLogOut(BaseModel):
    """跨用户抓取日志条目（平台数据·抓取日志 tab）。"""

    id: int
    competitor_name: str
    source_name: str
    status: str
    trigger: str
    changed: bool = False
    event_created: bool = False
    duration_ms: int = 0
    owner_username: str = ""
    created_at: str = ""


class AdminCrawlLogPage(BaseModel):
    items: list[AdminCrawlLogOut]
    total: int


@router.get("/crawl-logs", response_model=AdminCrawlLogPage)
async def list_all_crawl_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
):
    """全部用户的抓取日志，按时间倒序分页。keyword 按竞品名/监控源模糊匹配。"""
    page, page_size = _clamp_page(page, page_size)

    cond = []
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        cond.append(
            or_(CrawlLog.competitor_name.ilike(like), CrawlLog.source_name.ilike(like))
        )

    base = (
        select(CrawlLog, User.username.label("owner_username"))
        .outerjoin(User, User.id == CrawlLog.user_id)
        .where(*cond)
    )
    total = int(
        (
            await db.execute(
                select(func.count()).select_from(CrawlLog).where(*cond)
            )
        ).scalar_one()
    )
    rows = (
        await db.execute(
            base.order_by(CrawlLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return AdminCrawlLogPage(
        items=[
            AdminCrawlLogOut(
                id=log.id,
                competitor_name=log.competitor_name,
                source_name=log.source_name,
                status=log.status,
                trigger=log.trigger,
                changed=log.changed,
                event_created=log.event_created,
                duration_ms=log.duration_ms,
                owner_username=owner_username or "",
                created_at=format_time(log.created_at),
            )
            for log, owner_username in rows
        ],
        total=total,
    )


# ==================== 平台公告（仅管理员） ====================


class AnnouncementCreate(BaseModel):
    """发布公告：仅正文。"""

    content: str


class AnnouncementUpdate(BaseModel):
    """修改公告：正文 / 上下线均可选。"""

    content: str | None = None
    is_active: bool | None = None


@router.get("/announcements", response_model=list[AnnouncementOut])
async def list_announcements(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin)],
):
    """管理端公告全量列表（含已下线），新→旧。"""
    rows = (
        await db.execute(select(Announcement).order_by(Announcement.id.desc()))
    ).scalars().all()
    return [
        AnnouncementOut(
            id=a.id, content=a.content, is_active=a.is_active, created_at=a.created_at
        )
        for a in rows
    ]


@router.post("/announcements", response_model=AnnouncementOut)
async def create_announcement(
    payload: AnnouncementCreate,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """发布公告（默认上线）。"""
    content = payload.content.strip()
    if not content:
        raise BusinessError(ERR_ANNOUNCEMENT_INVALID, "公告内容不能为空", 400)
    row = Announcement(content=content, created_by=admin.id, is_active=True)
    db.add(row)
    # 先 flush 拿到自增 id，审计里就能带上目标 id（与业务同事务提交）
    await db.flush()
    _write_audit(
        db, admin, "create_announcement", "announcement", row.id, f"发布公告：{content[:80]}"
    )
    await db.commit()
    await db.refresh(row)
    return AnnouncementOut(id=row.id, content=row.content, is_active=row.is_active, created_at=row.created_at)


@router.patch("/announcements/{announcement_id}", response_model=AnnouncementOut)
async def update_announcement(
    announcement_id: int,
    payload: AnnouncementUpdate,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """修改公告：改正文 / 上线 / 下线。"""
    row = await db.get(Announcement, announcement_id)
    if row is None:
        raise BusinessError(ERR_USER_NOT_FOUND, "公告不存在或已被删除，请刷新后重试", 404)

    changes: list[str] = []
    if payload.content is not None:
        content = payload.content.strip()
        if not content:
            raise BusinessError(ERR_ANNOUNCEMENT_INVALID, "公告内容不能为空", 400)
        if content != row.content:
            changes.append("修改正文")
        row.content = content
    if payload.is_active is not None and payload.is_active != row.is_active:
        changes.append("上线" if payload.is_active else "下线")
        row.is_active = payload.is_active

    if changes:
        _write_audit(db, admin, "update_announcement", "announcement", row.id, "；".join(changes))
        await db.commit()
        await db.refresh(row)
    return AnnouncementOut(id=row.id, content=row.content, is_active=row.is_active, created_at=row.created_at)
