"""竞品图标库服务：磁盘文件 + 数据库记录，按规范化域名命中。

解析优先级全局约定：图标库 → 官网抓取解析 → 首字母兜底。
接入点：
- POST /api/competitors（新增竞品时先查库，见 api/competitors.py）
- GET /api/competitors/favicon（前端兜底解析，先查库）
- 抓取首页时（services/analyzer.py，先查库再解析 HTML）

域名口径统一：normalize_host 复用 favicon.clean_host 的容错解析（支持
带/不带协议、带路径），再进一步去 www、小写——与前端 CompetitorLogo 的
host 计算、schemas 里 favicon 回退的 host 提取保持一致。
"""
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import IconLibrary
from app.services import favicon

settings = get_settings()

# 允许上传的图片格式 → 磁盘扩展名。SVG 一律拒收：可内嵌脚本，存在 XSS 面。
_EXT_BY_CONTENT_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def normalize_host(value: str | None) -> str:
    """取出官网地址的规范化主机名：小写、去 www（与前端口径一致）。"""
    host = favicon.clean_host(value)
    return host[4:] if host.startswith("www.") else host


def icons_dir() -> Path:
    """图标文件的落盘目录（确保存在）。"""
    path = Path(settings.storage_dir) / "icons"
    path.mkdir(parents=True, exist_ok=True)
    return path


def public_icon_url(file_name: str) -> str:
    """图标对外地址：相对路径，由 main.py 挂载的 /api/icons 静态路由托管。

    存相对路径而不是带 request.base_url 的绝对地址：dev 下由 vite 代理
    /api 命中，同源部署直接命中，不会因反代/多域名把地址写死。
    """
    return f"/api/icons/{file_name}"


def ext_for_content_type(content_type: str) -> str | None:
    """合法图片格式 → 磁盘扩展名；不在白名单内返回 None。"""
    return _EXT_BY_CONTENT_TYPE.get((content_type or "").strip().lower())


def new_file_name(content_type: str) -> str:
    """生成随机文件名（uuid + 白名单扩展名），避免覆盖与路径穿越。"""
    return uuid.uuid4().hex + _EXT_BY_CONTENT_TYPE[content_type]


async def find_by_domain(db: AsyncSession, domain: str) -> IconLibrary | None:
    """按规范化域名查图标库条目；查不到返回 None。"""
    host = normalize_host(domain)
    if not host:
        return None
    result = await db.execute(select(IconLibrary).where(IconLibrary.domain == host))
    return result.scalar_one_or_none()


async def apply_icon_for_competitor(db: AsyncSession, competitor) -> None:
    """按竞品官网域名查图标库，命中即更新其 logo_url；未命中不动。

    图标库是域名级事实源，这里不等 logo_url 为空——命中且不一致就覆盖，
    保证新增/恢复竞品时库里已收录的图标立即可用。
    """
    host = normalize_host(competitor.official_url)
    if not host:
        return
    row = await find_by_domain(db, host)
    if row is None:
        return
    url = public_icon_url(row.file_name)
    if competitor.logo_url != url:
        competitor.logo_url = url