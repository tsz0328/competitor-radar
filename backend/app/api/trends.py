"""趋势分析接口。

注意路由顺序：`/overview` 必须声明在 `/{competitor_id}` 之前，
否则 "overview" 会被当成 competitor_id 去解析而报 422。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import ERR_COMPETITOR_NOT_FOUND, BusinessError
from app.models.competitor import Competitor
from app.models.trend import TrendInsight
from app.models.user import User
from app.schemas.trend import (
    CompetitorSeriesOut,
    DailyCountOut,
    TrendInsightOut,
    TrendPointOut,
)
from app.services import trend as trend_service

router = APIRouter(prefix="/api/trends", tags=["trends"])


def _to_insight_out(insight: TrendInsight, competitor_name: str) -> TrendInsightOut:
    return TrendInsightOut(
        competitor_id=insight.competitor_id,
        competitor_name=competitor_name,
        period_days=insight.period_days,
        direction=insight.direction,
        summary=insight.summary or "",
        highlights=list(insight.highlights or []),
        event_count=insight.event_count,
        high_impact_count=insight.high_impact_count,
        coverage_days=insight.coverage_days,
        created_at=insight.created_at,
    )


async def _get_owned_competitor(
    db: AsyncSession, competitor_id: int, current_user: User
) -> Competitor:
    competitor = (
        await db.execute(
            select(Competitor).where(
                Competitor.id == competitor_id,
                Competitor.user_id == current_user.id,
                Competitor.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if competitor is None:
        raise BusinessError(ERR_COMPETITOR_NOT_FOUND, "竞品不存在", 404)
    return competitor


@router.get("/overview", response_model=list[TrendPointOut])
async def trend_overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: int = Query(default=7, ge=7, le=90),
):
    """全部竞品汇总的变化趋势（Dashboard 的「竞品动态趋势」用）。"""
    return await trend_service.build_series(db, current_user.id, days)


@router.get("/daily", response_model=list[DailyCountOut])
async def trend_daily(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: int = Query(default=30, ge=7, le=90),
):
    """全部竞品汇总的每日变化总数（工作台趋势图用，点某天可钻取到情报中心）。"""
    return await trend_service.build_daily_totals(db, current_user.id, days)


@router.get("/compare", response_model=list[CompetitorSeriesOut])
async def trend_compare(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: int = Query(default=30, ge=7, le=90),
):
    """多竞品变化对比：每个竞品各自的每日变化总数序列（趋势分析「竞品对比」用）。"""
    return await trend_service.build_compare_series(db, current_user.id, days)


@router.get("/{competitor_id}/chart", response_model=list[TrendPointOut])
async def competitor_chart(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    competitor_id: int,
    days: int = Query(default=30, ge=7, le=90),
):
    """某个竞品的变化趋势序列。"""
    await _get_owned_competitor(db, competitor_id, current_user)
    return await trend_service.build_series(db, current_user.id, days, competitor_id)


@router.get("/{competitor_id}", response_model=TrendInsightOut)
async def competitor_trend(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    competitor_id: int,
    period_days: int = Query(default=30, ge=7, le=180, alias='periodDays'),
):
    """某竞品的趋势洞察；库里没有或已过期（>1 天）时自动生成一次。"""
    competitor = await _get_owned_competitor(db, competitor_id, current_user)

    insight, created = await trend_service.get_or_generate_insight(db, competitor, period_days)
    if created:
        await db.commit()
        await db.refresh(insight)  # created_at 由数据库默认值填充，需要回读
    return _to_insight_out(insight, competitor.name)
