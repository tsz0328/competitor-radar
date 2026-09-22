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
import httpx
import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.network import validate_remote_url
from app.models import IconLibrary
from app.services import favicon

settings = get_settings()
logger = logging.getLogger(__name__)

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
    """合法图片格式 → 磁盘扩展名；不在白名单内返回 None。

    容错处理 `image/png; charset=...` 这类带参数的 content-type（部分 CDN 会带）。
    """
    base = (content_type or "").split(";")[0].strip().lower()
    return _EXT_BY_CONTENT_TYPE.get(base)


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


async def _download_image(url: str) -> tuple[str, bytes] | None:
    """下载图标字节；非图片或失败返回 None。

    用于抓取流程把"顺手解析到的官网 favicon"沉淀进共享图标库——这样首个
    抓到该域标的用户写入一次，之后其他用户（含再次添加）直接命中，不必重复抓。
    """
    if not (await validate_remote_url(url)).ok:
        return None
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.crawl_timeout_seconds,
            headers={
                "User-Agent": settings.crawl_user_agent,
                "Accept": "image/*,*/*;q=0.8",
            },
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        return None
    if response.status_code >= 400:
        return None
    content_type = response.headers.get("content-type", "").lower()
    if not content_type.startswith("image/"):
        return None
    return content_type, response.content


async def save_from_url(db: AsyncSession, domain: str, image_url: str) -> str | None:
    """把某个官网域名的图标（抓取解析到的外链）沉淀进跨用户共享图标库。

    返回后端托管的图标地址（`/api/icons/...`）；无法入库时返回 None：
    - 域名无效 / 下载失败 / 非图片
    - 格式不在白名单（SVG 等，因可内嵌脚本已被图标库整体拒收）
    - 文件超过上限

    入库策略：
    - 该域名在库里已有记录（管理员上传或他人已沉淀）→ 以既有为准，不覆盖；
    - 否则落盘 + 插库（`uploaded_by` 留空，表示自动沉淀而非人工上传）；
    - 并发插入冲突时回退到既有记录（不报错、不重复写盘）。
    """
    host = normalize_host(domain)
    if not host:
        return None
    try:
        downloaded = await _download_image(image_url)
    except Exception:  # noqa: BLE001 - 图标只是锦上添花，绝不能影响抓取主流程
        logger.warning("下载图标失败 domain=%s url=%s", host, image_url)
        return None
    if downloaded is None:
        return None
    content_type, data = downloaded
    ext = ext_for_content_type(content_type)
    if ext is None:
        return None
    if len(data) > settings.icon_max_bytes:
        return None

    file_name = new_file_name(content_type)
    (icons_dir() / file_name).write_bytes(data)

    row = await find_by_domain(db, host)
    if row is not None:
        # 已存在：以既有图标为准，清理刚写的临时文件
        (icons_dir() / file_name).unlink(missing_ok=True)
        return public_icon_url(row.file_name)

    db.add(
        IconLibrary(
            domain=host,
            file_name=file_name,
            content_type=content_type,
            size=len(data),
            uploaded_by=None,
        )
    )
    try:
        await db.flush()
    except IntegrityError:
        # 并发：另一请求已抢先插入同域名记录
        await db.rollback()
        row = await find_by_domain(db, host)
        if row is not None:
            (icons_dir() / file_name).unlink(missing_ok=True)
            return public_icon_url(row.file_name)
        raise
    return public_icon_url(file_name)