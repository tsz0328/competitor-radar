import logging
import re
import shutil
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import (
    ERR_COMPETITOR_NOT_FOUND,
    ERR_INVALID_SOURCE,
    ERR_NO_ENABLED_SOURCE,
    BusinessError,
)
from app.core.http_errors import explain_http_status
from app.core.source_registry import SourceType, get_source_config
from app.core.timeutil import app_timezone, local_day_start_utc
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.notification import EventRead
from app.models.snapshot import PageSnapshot
from app.models.source import MonitorSource
from app.models.trend import TrendInsight
from app.models.user import User
from app.schemas.competitor import (
    CompetitorCreate,
    CompetitorOut,
    CompetitorUpdate,
    FaviconOut,
    SuggestRequest,
    SuggestResult,
)
from app.schemas.snapshot import CrawlResult, CrawlSourceResult, CrawlStatusOut
from app.schemas.source import (
    DiscoveredSourceOut,
    DiscoverRequest,
    DiscoverResult,
    MonitorSourceCreate,
    UrlCheckRequest,
    UrlCheckResult,
)
from app.services import settings as settings_service
from app.services.analyzer import (
    STATUS_FAILED,
    STATUS_SUCCESS,
    active_crawl_ids,
    run_competitor_crawl,
)
from app.services.crawler import fetch_html
from app.services.discoverer import discover_sources
from app.services.favicon import resolve_favicon
from app.services import icon_library
from app.services.suggester import suggest_competitor

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/competitors", tags=["competitors"])

# 回收站保留天数：超过此期限的软删除竞品会被惰性清理（连事件/快照一并清掉）
TRASH_RETENTION_DAYS = 30


def _remove_storage_folder(folder: Path) -> None:
    root = Path(settings.storage_dir).resolve()
    target = folder.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        logger.warning("拒绝删除存储目录外的路径：%s", target)
        return
    if target.exists():
        try:
            shutil.rmtree(target, ignore_errors=False)
        except OSError:
            logger.exception("删除竞品存储目录失败：%s", target)


async def _with_change_counts(
    db: AsyncSession, competitors: list[Competitor]
) -> list[CompetitorOut]:
    ids = [competitor.id for competitor in competitors]
    if not ids:
        return [CompetitorOut.model_validate(competitor) for competitor in competitors]

    total_stmt = (
        select(IntelligenceEvent.competitor_id, func.count())
        .where(IntelligenceEvent.competitor_id.in_(ids))
        .group_by(IntelligenceEvent.competitor_id)
    )
    today_start = local_day_start_utc(datetime.now(app_timezone()).date())
    today_stmt = (
        select(IntelligenceEvent.competitor_id, func.count())
        .where(
            IntelligenceEvent.competitor_id.in_(ids),
            IntelligenceEvent.created_at >= today_start,
        )
        .group_by(IntelligenceEvent.competitor_id)
    )
    totals = dict((await db.execute(total_stmt)).all())
    todays = dict((await db.execute(today_stmt)).all())

    return [
        CompetitorOut.model_validate(competitor).model_copy(
            update={
                "changes": totals.get(competitor.id, 0),
                "today_changes": todays.get(competitor.id, 0),
            }
        )
        for competitor in competitors
    ]


@router.post("/check-url", response_model=UrlCheckResult)
async def check_source_url(
    _: Annotated[User, Depends(get_current_user)],
    payload: UrlCheckRequest,
) -> UrlCheckResult:
    """保存竞品前，先悄悄探一下某个监控网址是否可达。

    仅发一次轻量 GET（短超时），不落库、不渲染；目的是从源头拦住"路径填错"
    这类低级错误——返回给人看的 message，前端直接弹提示。
    """
    url = (payload.url or "").strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return UrlCheckResult(
            url=url,
            ok=False,
            http_status=None,
            message="网址格式不正确，需以 http:// 或 https:// 开头",
        )

    result = await fetch_html(url, timeout=settings.check_url_timeout_seconds, retry_count=0)
    if result.ok:
        return UrlCheckResult(
            url=url,
            ok=True,
            http_status=result.http_status,
            message=f"可正常访问（HTTP {result.http_status}）",
        )
    # 网络错误走 result.error；4xx/5xx 已由 explain_http_status 翻成中文
    message = result.error or explain_http_status(result.http_status or 0)
    return UrlCheckResult(
        url=url,
        ok=False,
        http_status=result.http_status,
        message=message,
    )


@router.post("/discover-sources", response_model=DiscoverResult)
async def discover_source_urls(
    _: Annotated[User, Depends(get_current_user)],
    payload: DiscoverRequest,
) -> DiscoverResult:
    """按官网首页里的链接，自动寻找定价页/更新日志/博客/文档/状态页/RSS 的地址。

    只读探测（不落库）：拉首页 → 解析链接/sitemap → 关键词匹配 → 短超时校验可达。
    用户在前端点「自动寻找页面」时调用，拿到结果后由前端勾选并回填地址。
    """
    url = (payload.official_url or "").strip()
    if url and not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    if not url:
        return DiscoverResult(official_url="", homepage_reachable=False, sources=[])

    reachable, found = await discover_sources(url, skip_types=payload.skip_types)
    return DiscoverResult(
        official_url=url,
        homepage_reachable=reachable,
        sources=[DiscoveredSourceOut(**asdict(s)) for s in found],
    )


@router.post("/suggest", response_model=SuggestResult)
async def suggest_competitor_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: SuggestRequest,
) -> SuggestResult:
    """根据竞品名称，智能预填「官网地址」与「分类」。

    只读探测（不落库）：use_llm=True 时优先让 LLM 推断域名/分类并探活（「智能检测填充」按钮）；
    use_llm=False 时只用规则域名探测、不调 AI（用户自己填竞品时的自动预填）。
    无 Key 时两种分支都会退回常见域名探测；AI 能力用**当前账号自己**的配置。
    """
    llm_cfg = await settings_service.get_user_llm_config(db, current_user.id)
    result = await suggest_competitor(
        llm_cfg, payload.name, payload.categories, use_llm=payload.use_llm
    )
    return SuggestResult(
        official_url=result.official_url,
        category=result.category,
        source=result.source,
        message=result.message,
    )


async def _get_owned(db: AsyncSession, competitor_id: int, current_user: User) -> Competitor:
    """取出**未删除**的竞品并校验归属（软删除的竞品对常规操作不可见）。

    查不到时统一返回 404（不区分"不存在"、"已删除"和"不是你的"），
    避免泄露"这个 ID 确实存在但属于别人"这种信息。
    """
    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.user_id == current_user.id,
            Competitor.deleted_at.is_(None),
        )
    )
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise BusinessError(ERR_COMPETITOR_NOT_FOUND, "竞品不存在或已被删除，请刷新列表后重试", 404)
    return competitor


async def _get_any_owned(db: AsyncSession, competitor_id: int, current_user: User) -> Competitor:
    """取出竞品并校验归属，**不限删除状态**——回收站的恢复/彻底删除用这个。"""
    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.user_id == current_user.id,
        )
    )
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise BusinessError(ERR_COMPETITOR_NOT_FOUND, "竞品不存在或已被删除，请刷新列表后重试", 404)
    return competitor


async def _hard_delete_competitor(db: AsyncSession, competitor: Competitor) -> None:
    """彻底删除一个竞品：级联删监控源，按其归属删事件/快照/趋势/已读标记，并清存储目录。

    抓取日志（crawl_logs）不含外键、属"历史现场"，按设计保留，不在此清理。
    """
    storage_folder = Path(settings.storage_dir) / str(competitor.id)
    # 已读标记依赖事件，先清标记再清事件本身（SQLite 默认不开外键级联，需显式删）
    await db.execute(
        delete(EventRead).where(
            EventRead.event_id.in_(
                select(IntelligenceEvent.id).where(
                    IntelligenceEvent.competitor_id == competitor.id
                )
            )
        )
    )
    # 趋势分析按竞品维度聚合，无外键级联，硬删时须显式清除，避免指向已删竞品的孤儿记录
    await db.execute(
        delete(TrendInsight).where(TrendInsight.competitor_id == competitor.id)
    )
    await db.execute(
        delete(IntelligenceEvent).where(IntelligenceEvent.competitor_id == competitor.id)
    )
    await db.execute(
        delete(PageSnapshot).where(PageSnapshot.competitor_id == competitor.id)
    )
    # monitor_sources 随 relationship 的 cascade="all, delete-orphan" 级联删
    await db.delete(competitor)
    await db.commit()
    _remove_storage_folder(storage_folder)


async def _purge_expired(db: AsyncSession) -> None:
    """惰性清理：删除超过保留期的软删除竞品（含其事件/快照/存储）。

    没有独立调度进程——在列表/回收站接口入口调用即可，查询成本低。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=TRASH_RETENTION_DAYS)
    rows = (
        await db.execute(
            select(Competitor).where(
                Competitor.deleted_at.isnot(None), Competitor.deleted_at < cutoff
            )
        )
    ).scalars().all()
    for competitor in rows:
        await _hard_delete_competitor(db, competitor)


def _build_source(
    competitor_id: int,
    item: MonitorSourceCreate,
    fallback_url: str,
) -> MonitorSource:
    """把一条前端提交的监控源，按注册表补全成可直接落库的实体。"""
    cfg = get_source_config(item.source_type)
    url = item.url or fallback_url
    if not url:
        raise BusinessError(ERR_INVALID_SOURCE, "监控页面缺少可用的网址，请为要监控的页面填写地址", 400)
    return MonitorSource(
        competitor_id=competitor_id,
        source_type=item.source_type,
        name=item.name or cfg.label,
        url=url,
        render_mode=cfg.render,
        interval_minutes=item.interval_minutes or cfg.default_interval_minutes,
    )


def _sync_sources(competitor: Competitor, incoming: list[MonitorSourceCreate]) -> None:
    """把竞品的监控源对齐到 incoming 集合（同类型视为同一个源）。

    只改内存中的关系集合，随调用方那次 commit 一起落库：
    - 不在 incoming 里的类型 → 移除（delete-orphan 级联删除）
    - 已有的类型               → 就地更新 url / 频率 / 渲染方式
    - 新增的类型               → 追加一个源
    """
    want = {item.source_type: item for item in incoming}
    existing = {source.source_type: source for source in competitor.sources}

    for source_type, source in existing.items():
        if source_type not in want:
            competitor.sources.remove(source)

    for source_type, item in want.items():
        cfg = get_source_config(source_type)
        url = item.url or competitor.official_url or ""
        if not url:
            raise BusinessError(ERR_INVALID_SOURCE, "监控页面缺少可用的网址，请为要监控的页面填写地址", 400)
        source = existing.get(source_type)
        if source is None:
            competitor.sources.append(
                _build_source(competitor.id, item, competitor.official_url or "")
            )
            continue
        source.name = item.name or cfg.label
        source.url = url
        source.render_mode = cfg.render
        source.interval_minutes = item.interval_minutes or cfg.default_interval_minutes
        # 用户显式重新提交了这个页面 → 视为已确认配置并恢复监控：
        # 清空上次抓取失败记录（用户重新编辑并验证过地址），重新启用并清零失败计数。
        # 否则"URL 已可达但上次抓取失败"的源在保存后仍残留旧错误，编辑弹窗会继续显示不通过。
        source.enabled = True
        source.fail_count = 0
        source.last_status = None
        source.last_error = None


@router.post("", response_model=CompetitorOut, status_code=status.HTTP_201_CREATED)
async def create_competitor(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: CompetitorCreate,
):
    """新增竞品（连同要监控的页面），自动归属当前登录用户。

    未显式配置监控页面时，兜底为官网首页建一个源——保证"填完就能开始监控"。

    重加同竞品：若当前用户的回收站里已有**同官网**的竞品，直接恢复它
    （清除删除标记、按提交的页面对齐监控源），其历史快照/事件/抓取记录
    因 competitor_id 未变而自动连回，无需任何额外迁移。
    """
    # official_url 已在 CompetitorCreate 里归一化，可直接用于精确匹配
    trashed = (
        await db.execute(
            select(Competitor).where(
                Competitor.user_id == current_user.id,
                Competitor.official_url == payload.official_url,
                Competitor.deleted_at.isnot(None),
            )
        )
    ).scalar_one_or_none()
    if trashed is not None:
        trashed.deleted_at = None
        trashed.name = payload.name
        if payload.category is not None:
            trashed.category = payload.category
        source_inputs = payload.sources or [MonitorSourceCreate(source_type=SourceType.HOMEPAGE)]
        _sync_sources(trashed, source_inputs)
        # 图标库优先：恢复的竞品若命中图标库，直接用后端托管图标
        await icon_library.apply_icon_for_competitor(db, trashed)
        await db.commit()
        result = await db.execute(select(Competitor).where(Competitor.id == trashed.id))
        restored = result.scalar_one()
        out = CompetitorOut.model_validate(restored)
        out.restored = True
        return out

    competitor = Competitor(user_id=current_user.id, **payload.model_dump(exclude={"sources"}))
    db.add(competitor)
    await db.flush()  # 先拿到自增 id，监控源才能关联

    source_inputs = payload.sources or [MonitorSourceCreate(source_type=SourceType.HOMEPAGE)]
    for item in source_inputs:
        db.add(_build_source(competitor.id, item, competitor.official_url or ""))

    # 图标库优先：库里已有该域名图标就直接用（否则等首次抓取时解析官网）
    await icon_library.apply_icon_for_competitor(db, competitor)

    await db.commit()

    # 重新查一次：sources 是 selectin 预加载，这样响应里能直接带上监控源，
    # 也避免异步会话下访问未加载的关联关系触发惰性加载而报错。
    result = await db.execute(select(Competitor).where(Competitor.id == competitor.id))
    return result.scalar_one()


@router.get("", response_model=list[CompetitorOut])
async def list_competitors(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """只返回当前用户自己的**未删除**竞品。"""
    await _purge_expired(db)  # 入口顺手清掉过期的回收站项
    result = await db.execute(
        select(Competitor)
        .where(Competitor.user_id == current_user.id, Competitor.deleted_at.is_(None))
        .order_by(Competitor.id)
    )
    competitors = list(result.scalars().all())
    return await _with_change_counts(db, competitors)


@router.get("/trash", response_model=list[CompetitorOut])
async def list_trash(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """回收站：当前用户已软删除、尚在保留期内的竞品（含其变化数）。"""
    await _purge_expired(db)
    result = await db.execute(
        select(Competitor)
        .where(Competitor.user_id == current_user.id, Competitor.deleted_at.isnot(None))
        .order_by(Competitor.deleted_at.desc())
    )
    competitors = list(result.scalars().all())
    return await _with_change_counts(db, competitors)


@router.post("/trash/{competitor_id}", response_model=CompetitorOut)
async def restore_competitor(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    competitor_id: int,
):
    """从回收站恢复：清除删除标记，竞品与其全部历史数据重新可用。"""
    competitor = await _get_any_owned(db, competitor_id, current_user)
    if competitor.deleted_at is None:
        raise BusinessError(ERR_COMPETITOR_NOT_FOUND, "该竞品不在回收站中，请刷新后重试", 400)
    competitor.deleted_at = None
    await db.commit()
    result = await db.execute(select(Competitor).where(Competitor.id == competitor.id))
    return result.scalar_one()


@router.delete("/trash", status_code=status.HTTP_204_NO_CONTENT)
async def purge_all_trash(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """清空回收站：彻底删除当前用户回收站中的全部竞品（事件/快照/监控源一并清除）。

    抓取日志按设计保留（历史现场），不受此影响。
    """
    await _purge_expired(db)
    result = await db.execute(
        select(Competitor).where(
            Competitor.user_id == current_user.id, Competitor.deleted_at.isnot(None)
        )
    )
    for competitor in result.scalars().all():
        await _hard_delete_competitor(db, competitor)


@router.delete("/trash/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_competitor(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    competitor_id: int,
):
    """从回收站彻底删除：连竞品的事件与快照一并清除，不可恢复。

    抓取日志按设计保留（历史现场），不受此影响。
    """
    competitor = await _get_any_owned(db, competitor_id, current_user)
    if competitor.deleted_at is None:
        raise BusinessError(ERR_COMPETITOR_NOT_FOUND, "该竞品不在回收站中，请刷新后重试", 400)
    await _hard_delete_competitor(db, competitor)


@router.get("/favicon", response_model=FaviconOut)
async def competitor_favicon(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    domain: str,
):
    """解析竞品官网的图标地址：图标库优先，否则读首页 HTML 的 <link rel="icon">。

    图标库里已有该域名条目时直接返回后端托管的图标；没有才按域名缓存地
    抓官网解析。前端在直连 favicon.ico / apple-touch-icon.png 都失败时调用，
    用于兜底那些把真实图标挂在 CDN 上的 SPA 站点（如豆包）。必须声明在
    `/{competitor_id}` 之前，否则 "favicon" 会被当成路径参数去匹配。
    """
    row = await icon_library.find_by_domain(db, domain)
    if row is not None:
        return FaviconOut(logo_url=icon_library.public_icon_url(row.file_name))
    return FaviconOut(logo_url=await resolve_favicon(domain))


@router.get("/crawl-status", response_model=CrawlStatusOut)
async def crawl_status(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """当前用户正在抓取中的竞品 id 列表。

    抓取状态在后端进程内实时登记（手动/定时共用），前端刷新页面后据此
    恢复「抓取中」按钮，避免刷新后误以为任务已结束而重复触发。
    """
    return CrawlStatusOut(competitor_ids=active_crawl_ids(current_user.id))


@router.get("/{competitor_id}", response_model=CompetitorOut)
async def get_competitor(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    competitor_id: int,
):
    return await _get_owned(db, competitor_id, current_user)


@router.patch("/{competitor_id}", response_model=CompetitorOut)
async def update_competitor(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    competitor_id: int,
    payload: CompetitorUpdate,
):
    """局部更新：只改请求里实际传了的字段；sources 传了就整份对齐监控源。"""
    competitor = await _get_owned(db, competitor_id, current_user)

    # 记录原始官网地址，用于判断是否发生了变更（决定是否让旧图标失效）
    original_url = competitor.official_url

    # exclude_unset=True 是关键：没传的字段不出现在字典里，不会被覆盖成 None
    for key, value in payload.model_dump(exclude_unset=True, exclude={"sources"}).items():
        setattr(competitor, key, value)

    # 官网地址变更：旧图标来自旧域名，若不失效会一直显示上一个网站的图标
    # （analyzer 抓取时有 `if competitor.logo_url: return` 守卫，旧值会卡死不再重解析）。
    # 改完立即用新域名去共享图标库复用：命中即填上；未命中则留空，等下次抓取或手动「重新获取」。
    if payload.official_url is not None and payload.official_url != original_url:
        competitor.logo_url = ""
        await icon_library.apply_icon_for_competitor(db, competitor)

    if payload.sources is not None:
        # 空数组等同于"至少盯住官网首页"，与新增时的兜底口径保持一致
        incoming = payload.sources or [MonitorSourceCreate(source_type=SourceType.HOMEPAGE)]
        _sync_sources(competitor, incoming)

    await db.commit()

    # 同 create：重查一次，确保返回的 sources 是同步后的最新状态
    result = await db.execute(select(Competitor).where(Competitor.id == competitor.id))
    return result.scalar_one()


@router.post("/{competitor_id}/revive-sources", response_model=CompetitorOut)
async def revive_sources(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    competitor_id: int,
):
    """重新启用被「连续失败自动停用」的监控源，并清零失败计数。

    只复活 auto_disabled 的源（enabled=False 且 fail_count 达阈值），
    不影响仍正常或手动暂停的源；没有可复活的源时直接返回当前状态。
    """
    competitor = await _get_owned(db, competitor_id, current_user)
    revived = 0
    for source in competitor.sources:
        if (
            not source.enabled
            and (source.fail_count or 0) >= settings.crawl_max_fail_count
        ):
            source.enabled = True
            source.fail_count = 0
            source.last_status = None
            source.last_error = None
            revived += 1
    if revived == 0:
        result = await db.execute(
            select(Competitor).where(Competitor.id == competitor.id)
        )
        return result.scalar_one()
    await db.commit()
    result = await db.execute(
        select(Competitor).where(Competitor.id == competitor.id)
    )
    return result.scalar_one()


@router.post("/{competitor_id}/crawl", response_model=CrawlResult)
async def crawl_competitor(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    competitor_id: int,
):
    """立即抓取该竞品下所有启用的监控页面（里程碑 6 的手动触发入口）。

    逐源顺序执行；单源失败只记录健康度与失败快照，不影响同批次其他源。
    """
    competitor = await _get_owned(db, competitor_id, current_user)

    sources = [source for source in competitor.sources if source.enabled]
    if not sources:
        raise BusinessError(
            ERR_NO_ENABLED_SOURCE, "该竞品没有启用的监控页面，请先启用至少一个", 400
        )

    outcomes = await run_competitor_crawl(db, competitor, sources)
    await db.commit()

    return CrawlResult(
        competitor_id=competitor.id,
        total=len(outcomes),
        succeeded=sum(1 for o in outcomes if o.status == STATUS_SUCCESS),
        failed=sum(1 for o in outcomes if o.status == STATUS_FAILED),
        changed=sum(1 for o in outcomes if o.changed),
        results=[CrawlSourceResult(**asdict(o)) for o in outcomes],
    )


@router.delete("/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_competitor(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    competitor_id: int,
):
    """删除竞品：软删除（移入回收站）。

    只置 deleted_at 标记，竞品行、监控源、历史快照、情报事件、抓取记录全部保留；
    标记后全局查询都会把它过滤掉，体验等同删除。30 天内可在「回收站」恢复；
    彻底删除（含事件/快照）只能在回收站里触发。
    """
    competitor = await _get_owned(db, competitor_id, current_user)
    competitor.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    # 204：删除成功，没有响应体
