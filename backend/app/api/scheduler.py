"""调度器状态查询（里程碑 10）。

只提供观测，不提供手动触发——抓取的入口是 `POST /api/competitors/{id}/crawl`，
周报的入口是 `POST /api/reports/generate`，避免出现两套触发语义。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.scheduler import SchedulerStatusOut
from app.services import scheduler as scheduler_service

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("", response_model=SchedulerStatusOut)
async def scheduler_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """调度器是否在跑、各任务下次执行时间、当前有多少个监控源到期待抓。"""
    return SchedulerStatusOut(
        **scheduler_service.get_scheduler_status(),
        pending_sources=await scheduler_service.count_due_sources(db),
    )
