"""解析竞品官网的"真实"图标地址。纯 IO，不碰数据库。

为什么需要它：
SPA 站点（如豆包 doubao.com）会把任意未知路径都返回成 200 的首页 HTML——
`/favicon.ico`、`/apple-touch-icon.png` 探测全部拿到 HTML，浏览器解码失败，
前端只能回退成首字母头像。真实图标往往挂在 CDN 上，只有读首页 HTML 里的
`<link rel="icon">` / `<link rel="apple-touch-icon">` 才能拿到。

设计要点：
- 不依赖任何第三方 logo 服务（Clearbit 之类不稳定且部分已弃用）；
- 结果（含"没找到"）按域名缓存，避免每次渲染都去打目标站；
- 所有失败都收敛成 None，不抛异常给接口层。
"""
import logging
import re
from urllib.parse import urljoin

import httpx

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.network import validate_remote_url

logger = logging.getLogger(__name__)
settings = get_settings()

# 图标缓存的 key 前缀与 TTL（24h：图标基本不变，失败也缓存，避免反复抓）
_CACHE_PREFIX = "favicon:"
_CACHE_TTL = 86400

_LINK_RE = re.compile(r"<link\b[^>]*>", re.I)
_REL_RE = re.compile(r"""rel\s*=\s*["']([^"']+)["']""", re.I)
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_SIZE_RE = re.compile(r"(\d+)\s*[xX]\s*(\d+)", re.I)

# 兜底路径：首页 HTML 里没解析到图标时，再按常规约定试一遍
_FALLBACK_PATHS = ("/favicon.ico", "/apple-touch-icon.png", "/favicon.png")


def clean_host(value: str | None) -> str:
    """从官网地址里取出主机名（容错：带/不带协议、带路径、带 www 都能处理）。

    `https://www.doubao.com/pricing` → `www.doubao.com`
    `doubao.com`                     → `doubao.com`
    """
    text = (value or "").strip()
    if not text:
        return ""
    if "://" in text:
        text = text.split("://", 1)[1]
    host = text.split("/")[0].split("?")[0].split("#")[0].strip().lower()
    return host


def _pick_icon_urls(html_text: str, base_url: str) -> list[str]:
    """按优先级挑出 HTML 里的图标地址（apple-touch-icon > 其他 icon，尺寸大的优先）。"""
    ranked: list[tuple[int, int, str]] = []  # (优先级, 尺寸, 绝对地址)

    for tag in _LINK_RE.findall(html_text):
        rel_match = _REL_RE.search(tag)
        href_match = _HREF_RE.search(tag)
        if not rel_match or not href_match:
            continue

        rel = rel_match.group(1).lower()
        if "icon" not in rel:  # 只看图标类 link
            continue
        # apple-touch-icon 通常是最清晰的一方图标，优先于普通 favicon
        priority = 3 if "apple-touch" in rel else (2 if "shortcut" in rel else 1)

        href = href_match.group(1).strip()
        if not href or href.startswith("data:"):
            continue

        url = urljoin(base_url, href)  # 兼容 //cdn... 、/path 、绝对地址
        if not url.lower().startswith(("http://", "https://")):
            continue

        size_match = _SIZE_RE.search(tag)
        size = int(size_match.group(1)) if size_match else 0
        ranked.append((priority, size, url))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)

    ordered: list[str] = []
    seen: set[str] = set()
    for _, _, url in ranked:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


async def _is_image(client: httpx.AsyncClient, url: str) -> bool:
    """确认地址真的返回图片——SPA 会把未知路径返回成 HTML，必须校验 content-type。"""
    if not (await validate_remote_url(url)).ok:
        return False
    try:
        response = await client.get(url, headers={"Accept": "image/*,*/*;q=0.8"})
    except httpx.HTTPError:
        return False
    if response.status_code >= 400:
        return False
    content_type = response.headers.get("content-type", "").lower()
    return content_type.startswith("image/")


async def _probe(host: str) -> str | None:
    """抓首页 HTML → 解析图标候选 → 逐个校验，返回第一个可用的图片地址。"""
    page_url = f"https://{host}/"
    if not (await validate_remote_url(page_url)).ok:
        return None
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.crawl_timeout_seconds,
            headers={
                "User-Agent": settings.crawl_user_agent,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        ) as client:
            candidates: list[str] = []
            try:
                response = await client.get(page_url)
                content_type = response.headers.get("content-type", "").lower()
                if response.status_code < 400 and "html" in content_type:
                    candidates.extend(_pick_icon_urls(response.text, str(response.url)))
            except httpx.HTTPError:
                pass  # 首页拿不到也不影响，下面还有常规路径兜底

            candidates.extend(
                urljoin(f"https://{host}/", path.lstrip("/")) for path in _FALLBACK_PATHS
            )

            for url in dict.fromkeys(candidates):  # 去重且保持顺序
                if await _is_image(client, url):
                    return url
    except httpx.HTTPError as exc:
        logger.warning("解析图标失败 host=%s err=%s", host, type(exc).__name__)
        return None
    return None


async def resolve_favicon(domain: str) -> str | None:
    """解析并缓存某域名的真实图标地址；解析不到返回 None。"""
    host = clean_host(domain)
    if not host or " " in host:
        return None

    cache = get_cache()
    key = f"{_CACHE_PREFIX}{host}"
    cached = await cache.get(key)
    if cached is not None:
        return cached or None  # 空串代表"解析过但没找到"，避免反复抓

    url = await _probe(host)
    await cache.set(key, url or "", _CACHE_TTL)
    logger.info("解析图标 host=%s ok=%s", host, bool(url))
    return url


# ---- 抓取流程专用：复用"已经在手"的首页 HTML，零额外请求 ----

def pick_icon_from_html(html_text: str, base_url: str) -> str | None:
    """从已经下载好的 HTML 里挑一个图标候选地址（纯解析，不发任何请求）。

    抓取官网首页时 HTML 本来就在手上，用这个函数拿候选不再多抓一次首页；
    候选是否真的返回图片由 validate_icon() 校验。
    """
    urls = _pick_icon_urls(html_text, base_url)
    return urls[0] if urls else None


async def validate_icon(url: str) -> bool:
    """确认候选地址真的返回图片（SPA 会把未知路径返回成 200 的 HTML）。"""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.crawl_timeout_seconds,
            headers={
                "User-Agent": settings.crawl_user_agent,
                "Accept": "image/*,*/*;q=0.8",
            },
        ) as client:
            return await _is_image(client, url)
    except httpx.HTTPError:
        return False


async def remember_favicon(domain: str, url: str | None) -> None:
    """把已解析（并已落库）的图标写进缓存。

    这样前端兜底调 /api/competitors/favicon 时直接命中，不必再抓一次首页。
    """
    host = clean_host(domain)
    if not host or " " in host:
        return
    await get_cache().set(f"{_CACHE_PREFIX}{host}", url or "", _CACHE_TTL)
