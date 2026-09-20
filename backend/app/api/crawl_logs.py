"""抓取日志查询：把手动/定时抓取的成功、失败、告警统一回给前端。

权限口径与其它资源一致：只能看到自己竞品的日志（落库时已冗余 user_id）。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.crawl_log import CrawlLog
from app.models.user import User
from app.schemas.crawl_log import CrawlLogItem, CrawlLogPage

router = APIRouter(prefix="/api/crawl-logs", tags=["crawl-logs"])


@router.get("", response_model=CrawlLogPage)
async def list_crawl_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias='pageSize'),
    status: str | None = Query(default=None),
    trigger: str | None = Query(default=None),
    competitor_id: int | None = Query(default=None, alias='competitorId'),
):
    """按时间倒序分页返回当前用户的抓取日志，可按状态/触发方式/竞品过滤。"""
    conditions = [CrawlLog.user_id == current_user.id]
    if status:
        conditions.append(CrawlLog.status == status)
    if trigger:
        conditions.append(CrawlLog.trigger == trigger)
    if competitor_id is not None:
        conditions.append(CrawlLog.competitor_id == competitor_id)

    base = select(CrawlLog).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await db.execute(
            base.order_by(CrawlLog.created_at.desc(), CrawlLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return CrawlLogPage(
        items=[CrawlLogItem.model_validate(row) for row in rows],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.delete("", status_code=204)
async def clear_crawl_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """清空当前用户的全部抓取日志（日志页「清空」按钮）。"""
    await db.execute(delete(CrawlLog).where(CrawlLog.user_id == current_user.id))
    await db.commit()
