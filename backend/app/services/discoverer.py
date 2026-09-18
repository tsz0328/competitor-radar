"""监控页自动发现：从官网首页（+ sitemap）里找出「定价页/更新日志/博客/文档/状态页/RSS」
最可能的地址，再逐个校验可达，交给前端一键回填。

设计要点：
- 纯 IO，不碰数据库；不依赖 LLM，规则可解释、无 Key 也能用。
- 匹配线索来自多处，优先级递减：首页里的站内链接（含子域，如 platform./api-docs.）
  > sitemap > 常见路径兜底（主域 + 同站子域）。
- 只有「链接/站点地图」来源的候选直接信任（站点自己链了它）；常见路径来源必须
  真的抓到有效正文才算数，避免把软 404（返回 200 的空壳页）误判为找到了。
- 单个候选失败不影响其它类型：6 类并行探测，每类沿"可信优先"顺序取首个通过者。
"""
import asyncio
import difflib
import logging
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from app.core.config import get_settings
from app.core.source_registry import RenderMode, SourceType, get_source_config
from app.services import browser, crawler

settings = get_settings()
logger = logging.getLogger(__name__)

# 只从官网自动发现这些类型：首页就是官网本身；应用商店页不在官网内，排除。
DISCOVERABLE_TYPES: tuple[SourceType, ...] = (
    SourceType.PRICING,
    SourceType.CHANGELOG,
    SourceType.BLOG,
    SourceType.DOCS,
    SourceType.STATUS,
    SourceType.RSS,
)

# 每类的路径/文本线索（命中路径权重更高）
_KEYWORDS: dict[SourceType, tuple[str, ...]] = {
    SourceType.PRICING: (
        "pricing", "price", "plans", "plan", "billing", "定价", "价格", "套餐", "计费",
    ),
    SourceType.CHANGELOG: (
        "changelog", "change-log", "releases", "release-notes", "release",
        "whats-new", "updates", "更新日志", "更新记录", "版本",
    ),
    SourceType.BLOG: ("blog", "news", "articles", "article", "posts", "博客", "新闻"),
    SourceType.DOCS: (
        "docs", "documentation", "help", "support", "guide", "manual", "faq", "文档", "帮助",
    ),
    SourceType.STATUS: ("status", "uptime", "health", "服务状态", "状态页"),
    SourceType.RSS: ("feed", "rss", "atom", "订阅"),
}

# 首页没链到时直接探的常见路径
_COMMON_PATHS: dict[SourceType, tuple[str, ...]] = {
    SourceType.PRICING: ("/pricing", "/prices", "/plans", "/price", "/pricing.html"),
    SourceType.CHANGELOG: (
        "/changelog", "/change-log", "/releases", "/release-notes", "/updates", "/whats-new",
    ),
    SourceType.BLOG: ("/blog", "/news", "/articles"),
    SourceType.DOCS: ("/docs", "/documentation", "/help", "/support", "/guide", "/faq"),
    SourceType.STATUS: ("/status", "/uptime", "/health"),
    SourceType.RSS: ("/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml", "/index.xml"),
}

# 每类最多校验的候选数 / 全局并发上限（既控耗时也控对目标站点的请求量）
# _MAX_RENDER：浏览器渲染很重（起内核 + 逐页渲染），单独再限一道流
_MAX_PER_TYPE = 4
_MAX_CONCURRENCY = 6
_MAX_RENDER = 2

# 候选来源的可信度排序：首页真实链接 > sitemap > 猜测的常见路径
_ORIGIN_RANK = {"link": 0, "sitemap": 1, "common": 2}

_SITEMAP_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)


@dataclass
class DiscoveredSource:
    """某个类型的发现结果；url 为 None 表示没找到。"""

    source_type: SourceType
    label: str
    url: str | None
    found: bool
    origin: str = ""  # link | sitemap | common
    http_status: int | None = None


class _LinkParser(HTMLParser):
    """收集页面里的 <a> 链接与声明的订阅源（<link rel=alternate type=rss/atom>）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.feeds: list[str] = []
        self._href: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        data = dict(attrs)
        if tag == "a":
            href = data.get("href")
            if href:
                self._href = href
                self._buf = []
        elif tag == "link":
            rel = (data.get("rel") or "").lower()
            typ = (data.get("type") or "").lower()
            href = data.get("href")
            if href and "alternate" in rel and any(k in typ for k in ("rss", "atom", "xml")):
                self.feeds.append(href)

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            text = " ".join("".join(self._buf).split())
            self.links.append((self._href, text))
            self._href = None
            self._buf = []


def _normalize(raw: str) -> str:
    value = (raw or "").strip().rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value


def _base_domain(host: str) -> str:
    host = (host or "").lower().split(":")[0].removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _same_site(host: str, base_host: str) -> bool:
    return _base_domain(host) == _base_domain(base_host)


def _absolutize(base: str, href: str) -> str | None:
    href = (href or "").strip()
    if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
        return None
    url = urljoin(base + "/", href).split("#", 1)[0]
    if urlparse(url).scheme not in ("http", "https"):
        return None
    return url.rstrip("/") or url


def _score(url: str, text: str, stype: SourceType) -> int:
    """候选与某类型的匹配分：路径命中权重高于锚文本命中，层级越深越扣分。"""
    path = urlparse(url).path.lower().strip("/")
    text_l = (text or "").lower()
    score = 0
    for kw in _KEYWORDS[stype]:
        if kw in path:
            score += 10
        elif kw in text_l:
            score += 3
    if score:
        score -= path.count("/") * 3  # 深层页面（如 /docs/a/b/c）不如栏目入口
    return score


def _score_sitemap(url: str, stype: SourceType) -> int:
    """站点地图候选：只认"路径整段等于关键词"的栏目入口。

    站点地图里多是深层文章页，若按子串匹配，`.../2026-01-29-time-in-status` 会误命中
    status、`.../custom-feeds-in-pulse` 会误命中 feeds，故要求整段相等。
    """
    segments = [seg for seg in urlparse(url).path.lower().split("/") if seg]
    if len(segments) != 1:
        return 0
    return 12 if segments[0] in _KEYWORDS[stype] else 0


def _path_depth(url: str) -> int:
    return len([seg for seg in urlparse(url).path.split("/") if seg])


async def _sitemap_urls(base: str) -> list[str]:
    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        res = await crawler.fetch_html(base + path, timeout=settings.check_url_timeout_seconds)
        if res.ok and "<" in res.html:
            locs = _SITEMAP_LOC_RE.findall(res.html)
            if locs:
                return locs[:200]
    return []


def _content_ok(text: str, extractor: str) -> bool:
    return bool(text.strip()) if extractor == "rss" else len(text) >= settings.crawl_min_text_length


class _ShellGuard:
    """识别"任意路径都返回同一页面"的站点（软 404 / SPA / 文档站默认页）。

    - 渲染场景：对每个 host 渲染一个**必然不存在**的路径作为基准；候选渲染结果与它高度雷同 → 拒绝。
    - httpx 场景：对每个 host 取一个不存在的路径作基准；候选正文与它雷同 → 拒绝。
      例如 api-docs.deepseek.com 对任意路径都返回同一个默认文档页，靠这个挡住误报。
    基准按 host 分别缓存：状态页/文档站常挂在子域，必须用「它自己」的基准比对才准。
    """

    def __init__(self, base: str, sem: asyncio.Semaphore) -> None:
        self.base = base
        self.scheme = urlparse(base).scheme
        self.sem = sem
        self._render_canary: dict[str, str] = {}
        self._http_canary: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def _rendered_canary_text(self, host: str) -> str:
        if host not in self._render_canary:
            async with self._lock:
                if host not in self._render_canary:
                    url = f"{self.scheme}://{host}/__cr_nonexistent__{uuid.uuid4().hex[:8]}"
                    async with self.sem:
                        rendered = await browser.fetch_rendered(url)
                    cfg = get_source_config(SourceType.HOMEPAGE)
                    self._render_canary[host] = (
                        crawler.extract_text(rendered.html, cfg) if rendered.ok else ""
                    )
        return self._render_canary[host]

    async def _http_canary_text(self, host: str) -> str:
        if host not in self._http_canary:
            async with self._lock:
                if host not in self._http_canary:
                    url = f"{self.scheme}://{host}/__cr_nonexistent__{uuid.uuid4().hex[:8]}"
                    res = await crawler.fetch_html(
                        url, timeout=settings.check_url_timeout_seconds
                    )
                    cfg = get_source_config(SourceType.HOMEPAGE)
                    self._http_canary[host] = (
                        crawler.extract_text(res.html, cfg) if res.ok else ""
                    )
        return self._http_canary[host]

    @staticmethod
    def _similar(a: str, b: str) -> bool:
        return bool(a) and difflib.SequenceMatcher(None, a, b).ratio() >= 0.95

    async def is_shell_rendered(self, host: str, text: str) -> bool:
        return self._similar(await self._rendered_canary_text(host), text)

    async def is_shell_http(self, host: str, text: str) -> bool:
        return self._similar(await self._http_canary_text(host), text)


async def _verify(
    url: str,
    stype: SourceType,
    origin: str,
    allow_render: bool,
    guard: _ShellGuard,
) -> tuple[int | None, bool]:
    """校验候选是否可用。

    - 链接/站点地图来源：HTTP 可达即可（站点自己链了它，可信）。
    - 常见路径来源：要求真能提取到正文、且**不是**"任意路径同一页"的默认页；
      browser 类型若 httpx 取不到正文，再用真浏览器渲染兜底（SPA 页面只有渲染后才有内容）。
    """
    cfg = get_source_config(stype)
    res = await crawler.fetch_html(url, timeout=settings.check_url_timeout_seconds)
    if res.ok:
        if origin in ("link", "sitemap"):
            return res.http_status, True
        text = crawler.extract_text(res.html, cfg)
        if _content_ok(text, cfg.extractor) and not await guard.is_shell_http(
            urlparse(url).netloc, text
        ):
            return res.http_status, True
    # httpx 拿不到（连接被拒 / 无正文）时，browser 类型仍要用真浏览器渲染兜底：
    # 不少站点（如带 Cloudflare 防护的状态页）对 httpx 直接拒连，只有浏览器能打开。
    if allow_render and cfg.render == RenderMode.BROWSER and not browser.availability_note():
        async with guard.sem:
            rendered = await browser.fetch_rendered(url)
        if rendered.ok:
            rtext = crawler.extract_text(rendered.html, cfg)
            # 链接/站点地图来源是站点自己指过来的地址，直接采信（不做空壳判定）——
            # 例如 status.deepseek.com 这类状态站对任意路径都渲染同一页，但它就是对的。
            trusted = origin in ("link", "sitemap")
            if _content_ok(rtext, cfg.extractor) and (
                trusted
                or not await guard.is_shell_rendered(urlparse(url).netloc, rtext)
            ):
                return rendered.http_status, True
    return res.http_status, False


def _empty(stype: SourceType) -> DiscoveredSource:
    return DiscoveredSource(
        source_type=stype, label=get_source_config(stype).label, url=None, found=False
    )


async def discover_sources(
    official_url: str,
    skip_types: Iterable[SourceType] | None = None,
) -> tuple[bool, list[DiscoveredSource]]:
    """返回 (官网首页是否可达, 每个可发现类型的结果)。

    skip_types 里的类型会被整体跳过（例如前端已检测通过、不想再找的页面），
    既不在探测范围内，也省掉对应的请求与浏览器渲染。
    """
    base = _normalize(official_url)
    if not base:
        return False, [_empty(t) for t in DISCOVERABLE_TYPES]
    skip = set(skip_types or ())
    scan = tuple(t for t in DISCOVERABLE_TYPES if t not in skip)
    if not scan:
        return True, [_empty(t) for t in DISCOVERABLE_TYPES]

    home = await crawler.fetch_html(base, timeout=settings.check_url_timeout_seconds)
    base_host = urlparse(base).netloc

    pool: dict[SourceType, list[tuple[int, str, str]]] = {t: [] for t in scan}
    extra_hosts: set[str] = set()  # 首页里出现过的同站子域（platform. / api-docs. 等）

    if home.ok:
        parser = _LinkParser()
        try:
            parser.feed(home.html)
        except Exception:  # noqa: BLE001 - 畸形 HTML 不该拖垮整个发现流程
            logger.debug("解析首页链接失败：%s", base)

        for href, text in parser.links:
            url = _absolutize(base, href)
            if not url:
                continue
            host = urlparse(url).netloc
            if not _same_site(host, base_host):
                continue
            if host != base_host:
                extra_hosts.add(host)
            for stype in scan:
                score = _score(url, text, stype)
                if score:
                    pool[stype].append((score, url, "link"))

        # <link rel=alternate> 声明的订阅源是 RSS 最可靠的来源
        for href in parser.feeds:
            url = _absolutize(base, href)
            if url and SourceType.RSS in scan:
                pool[SourceType.RSS].append((30, url, "link"))

        for url in await _sitemap_urls(base):
            if not _same_site(urlparse(url).netloc, base_host):
                continue
            for stype in scan:
                score = _score_sitemap(url, stype)  # 只认"整段等于关键词"的栏目入口
                if score:
                    pool[stype].append((score + 1, url, "sitemap"))

    # 常见路径兜底：主域 + 首页出现过的同站子域（很多竞品把定价/文档挂在子域而非主域）
    scheme = urlparse(base).scheme
    for stype in scan:
        for path in _COMMON_PATHS[stype]:
            url = base + path
            pool[stype].append((_score(url, "", stype) + 2, url, "common"))
        for host in sorted(extra_hosts)[:3]:
            root = f"{scheme}://{host}"
            for path in _COMMON_PATHS[stype]:
                url = root + path
                pool[stype].append((_score(url, "", stype), url, "common"))

    # 每类去重取前 N，按「可信来源优先、同来源分数高优先」排序：
    # 首页真实链接（含子域）务必优先于猜测的常见路径，否则会被猜的路径挤掉名额。
    # 每类仅对「排第一者」允许浏览器渲染兜底，避免渲染次数失控。
    candidates: list[tuple[SourceType, int, str, str, bool]] = []
    for stype in scan:
        seen: set[str] = set()
        ranked = sorted(pool[stype], key=lambda c: (_ORIGIN_RANK.get(c[2], 3), -c[0]))
        for score, url, origin in ranked:
            if url in seen:
                continue
            seen.add(url)
            candidates.append((stype, score, url, origin, len(seen) == 1))
            if len(seen) >= _MAX_PER_TYPE:
                break

    sem = asyncio.Semaphore(_MAX_CONCURRENCY)
    guard = _ShellGuard(base, asyncio.Semaphore(_MAX_RENDER))

    async def _check(item: tuple[SourceType, int, str, str, bool]):
        stype, score, url, origin, allow_render = item
        async with sem:
            status, ok = await _verify(url, stype, origin, allow_render, guard)
        return stype, score, url, origin, status, ok

    checked = await asyncio.gather(*(_check(c) for c in candidates)) if candidates else []

    best: dict[SourceType, DiscoveredSource] = {}
    # 通过的候选里优先更短的栏目路径（/changelog 优于 /changelog/xxx 单篇），
    # 同层级再按来源可信度、分数取优。
    for stype, _, url, origin, status, ok in sorted(
        checked, key=lambda r: (_path_depth(r[2]), _ORIGIN_RANK.get(r[3], 3), -r[1])
    ):
        if ok and stype not in best:
            best[stype] = DiscoveredSource(
                source_type=stype,
                label=get_source_config(stype).label,
                url=url,
                found=True,
                origin=origin,
                http_status=status,
            )

    return home.ok, [best.get(t) or _empty(t) for t in DISCOVERABLE_TYPES]
