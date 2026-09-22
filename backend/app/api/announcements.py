"""平台公告：用户端只读接口。

管理端的发布 / 下线操作在 api/admin.py（仅管理员）。这里只提供用户登录后
可见的 active 公告列表，供 AppLayout 顶部横幅展示。
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Announcement, User

router = APIRouter(prefix="/api/announcements", tags=["announcements"])


class AnnouncementOut(BaseModel):
    """公告回显（管理端与用户端共用）。"""

    id: int
    content: str
    is_active: bool
    created_at: datetime


@router.get("/active", response_model=list[AnnouncementOut])
async def list_active(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
):
    """用户端可读：当前生效的公告（最新的在前）。

    任何已登录用户（含管理员）都可读；横幅关闭记忆在前端 localStorage。
    """
    rows = (
        await db.execute(
            select(Announcement)
            .where(Announcement.is_active.is_(True))
            .order_by(Announcement.id.desc())
        )
    ).scalars().all()
    return [
        AnnouncementOut(id=a.id, content=a.content, is_active=a.is_active, created_at=a.created_at)
        for a in rows
    ]