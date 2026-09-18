"""历史快照回显：把抓取时落盘的原始 HTML 安全地返回给前端。

安全约定：
1. 只能看自己竞品名下的快照（按 user_id 校验）；
2. 目录穿越防护——解析后的路径必须仍在 STORAGE_DIR 之内；
3. 响应带 `Content-Security-Policy: sandbox` 且禁用脚本，
   前端再用 `<iframe sandbox>` 包一层，双重保证抓来的页面不会执行脚本。
"""
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import BusinessError
from app.models.competitor import Competitor
from app.models.snapshot import PageSnapshot
from app.models.user import User

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])

# 快照缺失统一用同一个业务码，避免暴露"存在但不属于你"这类信息
ERR_SNAPSHOT_MISSING = 40410

_SAFE_CSP = "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'"


@router.get("/{snapshot_id}/raw", response_class=HTMLResponse)
async def snapshot_raw(
    snapshot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回该快照抓取时的原始 HTML（供详情抽屉内嵌 iframe 查看）。"""
    row = (
        await db.execute(
            select(PageSnapshot, Competitor.user_id)
            .join(Competitor, Competitor.id == PageSnapshot.competitor_id)
            .where(PageSnapshot.id == snapshot_id)
        )
    ).first()
    if row is None:
        raise BusinessError(ERR_SNAPSHOT_MISSING, "快照不存在", 404)

    snapshot, owner_id = row
    if owner_id != current_user.id:
        raise BusinessError(ERR_SNAPSHOT_MISSING, "快照不存在", 404)
    if not snapshot.raw_html_path:
        raise BusinessError(ERR_SNAPSHOT_MISSING, "该快照没有留存原始页面", 404)

    # 库里存的是相对 backend 根目录的路径（如 storage/6/10_xxx.html），故基准取 storage 的上级
    storage_root = Path(get_settings().storage_dir).resolve()
    base = storage_root.parent
    target = (base / snapshot.raw_html_path).resolve()
    # 防目录穿越：必须仍落在 storage 目录内，且确实是文件
    if storage_root != target.parent and storage_root not in target.parents:
        raise BusinessError(ERR_SNAPSHOT_MISSING, "该快照没有留存原始页面", 404)
    if not target.is_file():
        raise BusinessError(ERR_SNAPSHOT_MISSING, "该快照没有留存原始页面", 404)

    html = target.read_text(encoding="utf-8", errors="replace")
    return HTMLResponse(content=html, headers={"Content-Security-Policy": _SAFE_CSP})
