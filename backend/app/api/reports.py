"""竞品周报接口。"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import (
    ERR_REPORT_NOT_FOUND,
    BusinessError,
)
from app.core.timeutil import app_timezone, to_utc
from app.models.user import User
from app.models.weekly_report import ReportType, WeeklyReport
from app.schemas.report import (
    ReportDetailOut,
    ReportFavoriteIn,
    ReportGenerateOut,
    ReportListItemOut,
    ReportListOut,
    ReportShareIn,
    ReportShareOut,
)
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
            .where(
                WeeklyReport.user_id == current_user.id,
                WeeklyReport.deleted_at.is_(None),
            )
        )
    ).scalar() or 0

    rows = (
        (
            await db.execute(
                select(WeeklyReport)
                .where(
                    WeeklyReport.user_id == current_user.id,
                    WeeklyReport.deleted_at.is_(None),
                )
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


@router.post("/generate", response_model=ReportGenerateOut)
async def generate_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_type: str = Query(default="weekly", alias="reportType"),
    weeks_ago: int = Query(default=0, ge=0, le=12, alias="weeksAgo"),
):
    """手动生成一份周报/月报。

    每次都直接生成一份新的报告，可重复生成、互不覆盖、不弹冲突。
    """
    rt = ReportType(report_type)
    report = await report_service.generate_report(
        db, current_user, report_type=rt, weeks_ago=weeks_ago
    )
    await db.commit()
    await db.refresh(report)
    return ReportGenerateOut(status="created", report=report_service.to_detail(report))


TRASH_RETENTION_DAYS = 30


async def _get_owned(db: AsyncSession, report_id: int, current_user: User) -> WeeklyReport:
    """取出**未删除**的报告并校验归属（回收站里的报告对常规操作不可见）。

    查不到时统一返回 404，避免泄露"该 ID 确实存在但属于别人/已删除"。
    """
    report = (
        await db.execute(
            select(WeeklyReport).where(
                WeeklyReport.id == report_id,
                WeeklyReport.user_id == current_user.id,
                WeeklyReport.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if report is None:
        raise BusinessError(ERR_REPORT_NOT_FOUND, "报告不存在", 404)
    return report


async def _get_any_owned(db: AsyncSession, report_id: int, current_user: User) -> WeeklyReport:
    """取出报告并校验归属，**不限删除状态**——回收站的恢复/彻底删除用这个。"""
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
    return report


async def _purge_expired(db: AsyncSession) -> None:
    """惰性清理：删除超过保留期的软删除报告（在回收站/列表接口入口调用）。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=TRASH_RETENTION_DAYS)
    rows = (
        await db.execute(
            select(WeeklyReport).where(
                WeeklyReport.deleted_at.isnot(None), WeeklyReport.deleted_at < cutoff
            )
        )
    ).scalars().all()
    for report in rows:
        await db.delete(report)
    if rows:
        await db.commit()


@router.get("/trash", response_model=list[ReportListItemOut])
async def list_trash(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """回收站：当前用户已软删除、尚在保留期内的周报/月报。"""
    await _purge_expired(db)
    rows = (
        await db.execute(
            select(WeeklyReport)
            .where(
                WeeklyReport.user_id == current_user.id,
                WeeklyReport.deleted_at.isnot(None),
            )
            .order_by(WeeklyReport.deleted_at.desc())
        )
    ).scalars().all()
    return [report_service.to_list_item(report) for report in rows]


@router.post("/trash/{report_id}", response_model=ReportListItemOut)
async def restore_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_id: int,
):
    """从回收站恢复：清除删除标记，报告重新回到列表。"""
    report = await _get_any_owned(db, report_id, current_user)
    if report.deleted_at is None:
        raise BusinessError(ERR_REPORT_NOT_FOUND, "该报告不在回收站中", 400)
    report.deleted_at = None
    await db.commit()
    await db.refresh(report)
    return report_service.to_list_item(report)


@router.delete("/trash/{report_id}", status_code=204)
async def purge_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_id: int,
):
    """从回收站彻底删除：连同分享信息一并清除，不可恢复。"""
    report = await _get_any_owned(db, report_id, current_user)
    if report.deleted_at is None:
        raise BusinessError(ERR_REPORT_NOT_FOUND, "该报告不在回收站中", 400)
    await db.delete(report)
    await db.commit()


@router.delete("/{report_id}")
async def delete_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_id: int,
):
    """删除一份周报/月报：软删除移入回收站（保留期内可恢复）。"""
    report = await _get_owned(db, report_id, current_user)
    report.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.patch("/{report_id}/favorite", response_model=ReportDetailOut)
async def set_report_favorite(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_id: int,
    payload: ReportFavoriteIn,
):
    """切换收藏：收藏状态存在账号下，不再是前端的本地状态。"""
    report = await _get_owned(db, report_id, current_user)
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
    report = await _get_owned(db, report_id, current_user)
    return report_service.to_detail(report)


@router.get("/{report_id}/export", response_class=HTMLResponse)
async def export_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_id: int,
    format: str = Query(default="pdf", pattern="^(pdf|html|md|docx)$"),
):
    """导出周报。

    - pdf：返回独立打印页，浏览器打印对话框可「另存为 PDF」（默认，保持原行为）
    - html：返回可下载的独立网页文件
    - md：返回可下载的 Markdown 文本
    - docx：返回可下载的 Word 文档
    """
    report = await _get_owned(db, report_id, current_user)

    # PDF 保持渲染打印页（不触发下载），由前端写入新窗口后调用打印
    if format == "pdf":
        return HTMLResponse(report_service.to_print_html(report))

    if format == "html":
        media_type = "text/html; charset=utf-8"
        content: str | bytes = report_service.to_print_html(report)
        ext = "html"
    elif format == "docx":
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        content = report_service.to_docx(report)
        ext = "docx"
    else:  # md
        media_type = "text/markdown; charset=utf-8"
        content = report_service.to_markdown(report)
        ext = "md"

    # 文件名用 ASCII 兜底（前端下载时会用中文名覆盖），避免部分浏览器解析非 ASCII 头失败
    filename = f"weekly-report-{report.id}.{ext}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{report_id}/share", response_model=ReportShareOut | None)
async def get_report_share(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_id: int,
):
    """读取该周报当前有效的分享信息；无分享或已过期则返回 null（前端据此决定展示/重新生成）。"""
    report = await _get_owned(db, report_id, current_user)
    if not report.share_token:
        return None

    # SQLite 不保存时区，取回的是 naive（实为 UTC），比较前统一归一化
    expires_at = to_utc(report.share_expires_at)
    if expires_at and expires_at < datetime.now(timezone.utc):
        return None  # 已过期 → 前台表现为"无有效分享"

    return ReportShareOut(
        token=report.share_token,
        expires_at=(report.share_expires_at.isoformat() if report.share_expires_at else ""),
    )


@router.post("/{report_id}/share", response_model=ReportShareOut)
async def create_report_share(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_id: int,
    payload: ReportShareIn,
):
    """生成/重置一份周报的免登录分享链接（可设有效期，expires_days 为空=永久）。"""
    report = await _get_owned(db, report_id, current_user)

    report.share_token = secrets.token_urlsafe(32)
    if payload.expires_days:
        report.share_expires_at = datetime.now(app_timezone()) + timedelta(
            days=payload.expires_days
        )
    else:
        report.share_expires_at = None
    await db.commit()
    await db.refresh(report)
    return ReportShareOut(
        token=report.share_token,
        expires_at=(
            report.share_expires_at.isoformat() if report.share_expires_at else ""
        ),
    )


@router.delete("/{report_id}/share")
async def revoke_report_share(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    report_id: int,
):
    """撤销该周报的免登录分享链接，此后原链接立即失效。"""
    report = await _get_owned(db, report_id, current_user)
    report.share_token = None
    report.share_expires_at = None
    await db.commit()
    return {"ok": True}
