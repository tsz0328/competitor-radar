"""竞品周报接口。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import ERR_REPORT_NOT_FOUND, BusinessError
from app.models.user import User
from app.models.weekly_report import WeeklyReport
from app.schemas.report import ReportDetailOut, ReportFavoriteIn, ReportListOut
from app.services import report as report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("", response_model=ReportListOut)
async def list_reports(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """周报列表（按覆盖周期倒序）。"""
    total = (
        await db.execute(
            select(func.count())
            .select_from(WeeklyReport)
            .where(WeeklyReport.user_id == current_user.id)
        )
    ).scalar() or 0

    rows = (
        (
            await db.execute(
                select(WeeklyReport)
                .where(WeeklyReport.user_id == current_user.id)
                .order_by(WeeklyReport.range_end.desc(), WeeklyReport.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return ReportListOut(
        total=total, reports=[report_service.to_list_item(report) for report in rows]
    )


@router.post("/generate", response_model=ReportDetailOut)
async def generate_report(
    weeks_ago: int = Query(default=0, ge=0, le=12, alias="weeksAgo"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动生成一份周报（调试用；定时生成留到里程碑 10）。"""
    report = await report_service.generate_weekly_report(
        db, current_user, weeks_ago=weeks_ago
    )
    await db.commit()
    await db.refresh(report)
    return report_service.to_detail(report)


@router.patch("/{report_id}/favorite", response_model=ReportDetailOut)
async def set_report_favorite(
    report_id: int,
    payload: ReportFavoriteIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """切换收藏：收藏状态存在账号下，不再是前端的本地状态。"""
    report = (
        await db.execute(
            select(WeeklyReport).where(
                WeeklyReport.id == report_id,
                WeeklyReport.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if report is None:
        raise BusinessError(ERR_REPORT_NOT_FOUND, "报告不存在", 404)
    report.favorite = payload.favorite
    await db.commit()
    await db.refresh(report)
    return report_service.to_detail(report)


@router.get("/{report_id}", response_model=ReportDetailOut)
async def get_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """周报详情（AI 叙述 + 冻结的结构化报表内容）。"""
    report = (
        await db.execute(
            select(WeeklyReport).where(
                WeeklyReport.id == report_id,
                WeeklyReport.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if report is None:
        raise BusinessError(ERR_REPORT_NOT_FOUND, "报告不存在", 404)
    return report_service.to_detail(report)
