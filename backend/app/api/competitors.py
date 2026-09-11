import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import (
    ERR_COMPETITOR_NOT_FOUND,
    ERR_INVALID_SOURCE,
    ERR_NO_ENABLED_SOURCE,
    BusinessError,
)
from app.core.source_registry import SourceType, get_source_config
from app.models.competitor import Competitor
from app.models.source import MonitorSource
from app.models.user import User
from app.schemas.competitor import CompetitorCreate, CompetitorOut, CompetitorUpdate
from app.schemas.snapshot import CrawlResult, CrawlSourceResult
from app.schemas.source import MonitorSourceCreate
from app.services.analyzer import STATUS_FAILED, STATUS_SUCCESS, crawl_source

router = APIRouter(prefix="/api/competitors", tags=["competitors"])

logger = logging.getLogger(__name__)


async def _get_owned(db: AsyncSession, competitor_id: int, current_user: User) -> Competitor:
    """取出竞品并校验归属。

    查不到时统一返回 404（不区分"不存在"和"不是你的"），
    避免泄露"这个 ID 确实存在但属于别人"这种信息。
    """
    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.user_id == current_user.id,
        )
    )
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise BusinessError(ERR_COMPETITOR_NOT_FOUND, "竞品不存在", 404)
    return competitor


def _build_source(
    competitor_id: int,
    item: MonitorSourceCreate,
    fallback_url: str,
) -> MonitorSource:
    """把一条前端提交的监控源，按注册表补全成可直接落库的实体。"""
    cfg = get_source_config(item.source_type)
    url = item.url or fallback_url
    if not url:
        raise BusinessError(ERR_INVALID_SOURCE, "监控页面缺少可用的网址", 400)
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
            raise BusinessError(ERR_INVALID_SOURCE, "监控页面缺少可用的网址", 400)
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
        # 用户显式重新提交了这个页面 → 视为恢复监控：
        # 重新启用并清零失败计数，否则"连续失败自动停用"后永远无法复活。
        if not source.enabled:
            source.enabled = True
            source.fail_count = 0
            source.last_status = None
            source.last_error = None


@router.post("", response_model=CompetitorOut, status_code=status.HTTP_201_CREATED)
async def create_competitor(
    payload: CompetitorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新增竞品（连同要监控的页面），自动归属当前登录用户。

    未显式配置监控页面时，兜底为官网首页建一个源——保证"填完就能开始监控"。
    """
    competitor = Competitor(user_id=current_user.id, **payload.model_dump(exclude={"sources"}))
    db.add(competitor)
    await db.flush()  # 先拿到自增 id，监控源才能关联

    source_inputs = payload.sources or [MonitorSourceCreate(source_type=SourceType.HOMEPAGE)]
    for item in source_inputs:
        db.add(_build_source(competitor.id, item, competitor.official_url or ""))

    await db.commit()

    # 重新查一次：sources 是 selectin 预加载，这样响应里能直接带上监控源，
    # 也避免异步会话下访问未加载的关联关系触发惰性加载而报错。
    result = await db.execute(select(Competitor).where(Competitor.id == competitor.id))
    return result.scalar_one()


@router.get("", response_model=list[CompetitorOut])
async def list_competitors(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """只返回当前用户自己的竞品。"""
    result = await db.execute(
        select(Competitor).where(Competitor.user_id == current_user.id).order_by(Competitor.id)
    )
    return result.scalars().all()


@router.get("/{competitor_id}", response_model=CompetitorOut)
async def get_competitor(
    competitor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_owned(db, competitor_id, current_user)


@router.patch("/{competitor_id}", response_model=CompetitorOut)
async def update_competitor(
    competitor_id: int,
    payload: CompetitorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """局部更新：只改请求里实际传了的字段；sources 传了就整份对齐监控源。"""
    competitor = await _get_owned(db, competitor_id, current_user)

    # exclude_unset=True 是关键：没传的字段不出现在字典里，不会被覆盖成 None
    for key, value in payload.model_dump(exclude_unset=True, exclude={"sources"}).items():
        setattr(competitor, key, value)

    if payload.sources is not None:
        # 空数组等同于"至少盯住官网首页"，与新增时的兜底口径保持一致
        incoming = payload.sources or [MonitorSourceCreate(source_type=SourceType.HOMEPAGE)]
        _sync_sources(competitor, incoming)

    await db.commit()

    # 同 create：重查一次，确保返回的 sources 是同步后的最新状态
    result = await db.execute(select(Competitor).where(Competitor.id == competitor.id))
    return result.scalar_one()


@router.post("/{competitor_id}/crawl", response_model=CrawlResult)
async def crawl_competitor(
    competitor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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

    outcomes = []
    for source in sources:
        outcome = await crawl_source(db, competitor, source)
        outcomes.append(outcome)
        # 只记 URL / 类型 / 状态码 / 耗时 / 错误摘要，不记正文（见 data-source-design 第八节）
        logger.log(
            logging.WARNING if outcome.status == STATUS_FAILED else logging.INFO,
            "crawl competitor=%s source=%s type=%s status=%s http=%s changed=%s "
            "first_time=%s event_created=%s duration=%sms url=%s error=%s",
            competitor.id,
            source.id,
            source.source_type.value,
            outcome.status,
            outcome.http_status,
            outcome.changed,
            outcome.first_time,
            outcome.event_created,
            outcome.duration_ms,
            source.url,
            outcome.error,
        )
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
    competitor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competitor = await _get_owned(db, competitor_id, current_user)
    await db.delete(competitor)
    await db.commit()
    # 204：删除成功，没有响应体
