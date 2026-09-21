"""免登录周报分享：持有 /api/share/{token} 链接即可浏览该份周报的独立页面。

该路由刻意**不依赖登录**（get_current_user），只凭 share_token 查库。
token 由用户端生成分享链接时产生，撤销或过期后即失效。
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ERR_SHARE_EXPIRED, ERR_SHARE_NOT_FOUND, BusinessError
from app.core.timeutil import to_utc
from app.models.weekly_report import WeeklyReport
from app.services import report as report_service

router = APIRouter(prefix="/api/share", tags=["share"])


def _render_share_page(report: WeeklyReport) -> HTMLResponse:
    """把周报渲染成免登录可浏览的独立 HTML 页面。"""
    return HTMLResponse(report_service.to_print_html(report))


@router.get("/{token}", response_class=HTMLResponse)
async def shared_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str,
):
    """按分享 token 渲染周报；token 不存在/已撤销 → 404，已过期 → 410。"""
    report = (
        await db.execute(select(WeeklyReport).where(WeeklyReport.share_token == token))
    ).scalar_one_or_none()
    if report is None:
        raise BusinessError(ERR_SHARE_NOT_FOUND, "分享链接不存在或已被撤销", 404)

    # SQLite 不保存时区，取回的 expires_at 是 naive（实为 UTC），比较前统一归一化，
    # 否则 naive < aware 会抛 TypeError → 500
    expires_at = to_utc(report.share_expires_at)
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise BusinessError(ERR_SHARE_EXPIRED, "分享链接已过期，请向分享者获取新链接", 410)

    return _render_share_page(report)