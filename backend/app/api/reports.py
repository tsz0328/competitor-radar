"""竞品周报接口。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
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
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
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
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    weeks_ago: int = Query(default=0, ge=0, le=12, alias='weeksAgo'),
):
    """手动生成一份周报（调试用；定时生成留到里程碑 10）。"""
    start, _end = report_service.window_for(weeks_ago)
    existing = await report_service.get_report_for_window(
        db, current_user.id, start
    )
    if existing is not None:
        await db.refresh(existing)
        return report_service.to_detail(existing)
    report = await report_service.generate_weekly_report(
        db, current_user, weeks_ago=weeks_ago
    )
    await db.commit()
    await db.refresh(report)
    return report_service.to_detail(report)


@router.patch("/{report_id}/favorite", response_model=ReportDetailOut)
async def set_report_favorite(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_id: int,
    payload: ReportFavoriteIn,
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
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_id: int,
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


@router.get("/{report_id}/export", response_class=HTMLResponse)
async def export_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_id: int,
):
    """返回独立打印页；浏览器打印对话框可保存为 PDF。"""
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
    return HTMLResponse(report_service.to_print_html(report))
