"""抓取层：把页面拿回来并提取正文。纯 IO，不碰数据库。

设计要点：
- 正文提取优先用 trafilatura（装了就用，正文更干净、Diff 噪声更少）；
  没装则退回内置解析——保证零额外依赖也能跑通整条链路。
- 所有失败都收敛成 FetchResult.ok=False，不抛异常给上层。
- 日志只记 URL / 类型 / 耗时 / 状态码 / 错误摘要，不记正文。
"""
import asyncio
import hashlib
import html as html_lib
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import BACKEND_DIR, get_settings
from app.core.http_errors import explain_http_status
from app.core.network import validate_remote_url
from app.core.source_registry import RenderMode, SourceTypeConfig
from app.services import browser

settings = get_settings()

# 可选增强：装了就用（正文更干净、Diff 噪声更少），没装则退回内置解析
try:  # pragma: no cover - 取决于运行环境
    import trafilatura
except ImportError:  # pragma: no cover
    trafilatura = None

try:  # pragma: no cover
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None


@dataclass
class FetchResult:
    """一次 HTTP 抓取的结果。"""

    ok: bool
    url: str = ""
    http_status: int | None = None
    html: str = ""
    error: str = ""
    elapsed_ms: int = 0
    attempts: int = 1


# ---- 内置的轻量正文提取（无第三方依赖）----
_DROP_BLOCK_RE = re.compile(
    r"<(script|style|noscript|template|svg|iframe)\b[^>]*>.*?</\1>", re.I | re.S
)
_BLOCK_END_RE = re.compile(
    r"</(p|div|li|tr|h[1-6]|section|article|header|footer|br)\s*>", re.I
)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# RSS/Atom：按"条目集合"提取，和注册表里 differ=item_set 的策略对应
_ITEM_RE = re.compile(r"<(item|entry)\b[^>]*>(.*?)</\1>", re.I | re.S)
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _clean_error(message: str, limit: int = 300) -> str:
    """错误摘要截断，避免把整段堆栈写进库。"""
    message = re.sub(r"\s+", " ", (message or "").strip())
    return message[:limit]
def _retry_wait_seconds(
    attempt: int,
    response: httpx.Response | None = None,
    base_seconds: float | None = None,
    max_wait_seconds: float | None = None,
) -> float:
    """计算下一次重试前等待的时间，优先尊重 Retry-After。"""
    base = settings.crawl_retry_base_seconds if base_seconds is None else base_seconds
    max_wait = (
        settings.crawl_retry_max_wait_seconds
        if max_wait_seconds is None
        else max_wait_seconds
    )
    if response is not None:
        value = (response.headers.get("Retry-After") or "").strip()
        if value.isdigit():
            delay = float(value)
        else:
            delay = base * (2**attempt)
    else:
        delay = base * (2**attempt)
    return min(max(0.1, delay), max_wait)


async def fetch_html(
    url: str,
    timeout: float | None = None,
    retry_count: int | None = None,
    retry_backoff_seconds: float | None = None,
    retry_max_wait_seconds: float | None = None,
) -> FetchResult:
    """GET 一个页面，并对 429/5xx 与瞬时网络错误做有限重试。

    timeout 可覆盖默认抓取超时（例如「校验网址」场景想用更短的等待）。
    """
    start = time.perf_counter()
    validation = await validate_remote_url(url)
    if not validation.ok:
        return FetchResult(
            ok=False, url=url, error=validation.message, elapsed_ms=_ms(start)
        )
    max_retries = max(0, settings.crawl_retry_count if retry_count is None else retry_count)
    retry_base = (
        settings.crawl_retry_base_seconds
        if retry_backoff_seconds is None
        else retry_backoff_seconds
    )
    retry_max = (
        settings.crawl_retry_max_wait_seconds
        if retry_max_wait_seconds is None
        else retry_max_wait_seconds
    )
    last_error = ""
    last_status: int | None = None

    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=timeout if timeout is not None else settings.crawl_timeout_seconds,
                headers={
                    "User-Agent": settings.crawl_user_agent,
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            ) as client:
                response = await client.get(url)
                final_validation = await validate_remote_url(str(response.url))
                if not final_validation.ok:
                    return FetchResult(
                        ok=False,
                        url=str(response.url),
                        error=final_validation.message,
                        elapsed_ms=_ms(start),
                        attempts=attempt + 1,
                    )
        except httpx.HTTPError as exc:
            last_error = _clean_error(f"请求失败：{type(exc).__name__}: {exc}")
            if attempt < max_retries:
                await asyncio.sleep(
                    _retry_wait_seconds(
                        attempt,
                        base_seconds=retry_base,
                        max_wait_seconds=retry_max,
                    )
                )
                continue
            return FetchResult(
                ok=False,
                url=url,
                error=last_error,
                elapsed_ms=_ms(start),
                attempts=attempt + 1,
            )

        elapsed = _ms(start)
        if response.status_code < 400:
            return FetchResult(
                ok=True,
                url=str(response.url),
                http_status=response.status_code,
                html=response.text,
                elapsed_ms=elapsed,
                attempts=attempt + 1,
            )

        last_status = response.status_code
        last_error = explain_http_status(response.status_code)
        if response.status_code in _RETRYABLE_STATUS_CODES and attempt < max_retries:
            await asyncio.sleep(
                _retry_wait_seconds(
                    attempt, response, retry_base, retry_max
                )
            )
            continue

        return FetchResult(
            ok=False,
            url=url,
            http_status=response.status_code,
            error=last_error,
            elapsed_ms=elapsed,
            attempts=attempt + 1,
        )

    return FetchResult(
        ok=False,
        url=url,
        http_status=last_status,
        error=last_error or "抓取失败",
        elapsed_ms=_ms(start),
        attempts=max_retries + 1,
    )


async def fetch_auto(url: str, cfg: SourceTypeConfig) -> FetchResult:
    """按注册表的 render 策略抓取，必要时用真浏览器兜底。

    - render=http：只走 httpx（RSS / 状态页这类，毫秒级）
    - render=browser：**先 httpx 试探**——很多"标了 browser"的页面其实是静态的，
      毫秒级就能拿到；只有拿不到有效正文时才动真浏览器，避免无差别上
      Playwright（单次 1-3 秒、内存占用高）。
    """
    first = await fetch_html(url)
    if (
        cfg.render != RenderMode.BROWSER
        or not settings.browser_render_enabled
        or browser.availability_note()
    ):
        return first
    if first.ok and len(extract_text(first.html, cfg)) >= settings.crawl_min_text_length:
        return first

    rendered = await browser.fetch_rendered(url)
    if not rendered.ok:
        # 保留 httpx 那次的结果：它的失败原因更贴近"到底发生了什么"
        return first
    return FetchResult(
        ok=True,
        url=rendered.url,
        http_status=rendered.http_status,
        html=rendered.html,
        elapsed_ms=rendered.elapsed_ms,
    )


def normalize_text(text: str) -> str:
    """空白归一化：去掉多余空格与空行，让 Diff 只反映真实内容变化。"""
    text = unicodedata.normalize("NFKC", text or "")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t\u00a0\u3000]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


# ---- 噪声行识别：这些往往是页面每次渲染都会变、但不携带"竞品情报"的内容 ----
# 命中即整行丢弃，避免"Footer 时间 / 相对时间 / 浏览量"等把 hash 与 diff 污染成假变化。
# 设计取舍：只打"明显动态"的行，避免误伤正文——例如"发布于/更新于 2026-09-18"（发布日期，
# 对更新日志是有意义内容）与"营业时间 09:00-18:00"（时间区间）都**不**在此列。
_NOISE_LINE_RES = (
    # 相对时间（中文）：3 分钟前 / 2 小时前 / 刚刚
    re.compile(r"\d+\s*(?:秒|分钟|分|小时|天|日|周|月|年)\s*前"),
    re.compile(r"刚刚"),
    # 相对时间（英文）：3 minutes ago / just now
    re.compile(r"\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\s*ago", re.I),
    re.compile(r"just now", re.I),
    # 动态元数据行（页面"何时刷新/生成"，并非内容本身）：当前时间 / 更新时间 / 最后更新 /
    # 最后修改 / 刷新时间（不含"发布于/更新于"，后者多为有含义的发布日期）
    re.compile(r"^(?:当前时间|更新时间|最后更新|最后修改|刷新时间)\b", re.I),
    # 整行仅为一个时刻（如 footer 的 09:30）；用"整行仅此"避免误伤"营业时间 09:00-18:00"区间
    re.compile(r"^\d{1,2}[:：]\d{2}(?:\s*[AP]M)?$"),
    # 浏览/阅读/播放计数：123 次阅读 / 1.2k views / 播放 456 次
    re.compile(
        r"\d[\d,.]*\s*(?:次阅读|次浏览|次播放|次观看|次查看|阅读|views?|plays?|visits?)",
        re.I,
    ),
    re.compile(r"(?:阅读|浏览|播放|观看|查看)\s*\d[\d,.]*\s*次?"),
)


def strip_noise(text: str) -> str:
    """丢弃"每轮渲染都会变却没有情报价值"的行（相对时间、动态元数据、浏览计数）。

    放在正文提取与空白归一化之后、计算 content_hash 之前：
    - 噪声行消失 → 相同实质内容两次抓取 hash 不变 → 不再产生假情报事件；
    - 同时让留存下来的 diff 只反映"真正有意义"的变化。
    只整行丢弃、不部分改写，避免误伤正文里偶尔出现的时间/数字。
    """
    lines = [
        line
        for line in (text or "").splitlines()
        if not any(rx.search(line) for rx in _NOISE_LINE_RES)
    ]
    return "\n".join(lines)


def _html_to_text(raw_html: str) -> str:
    """内置解析兜底：去脚本样式 → 块级标签转换行 → 剥标签 → 反转义。"""
    text = _DROP_BLOCK_RE.sub(" ", raw_html)
    text = _BLOCK_END_RE.sub("\n", text)
    text = _ANY_TAG_RE.sub(" ", text)
    return html_lib.unescape(text)

def _extract_article_text(raw_html: str) -> str:
    """用 trafilatura（可用时）提取正文，否则退回内置 HTML 转文本。"""
    if trafilatura is not None:
        text = trafilatura.extract(
            raw_html, include_comments=False, include_tables=True
        )
        if text:
            return text
    return _html_to_text(raw_html)

def _focused_lines(lines: list[str], pattern: "re.Pattern[str]", radius: int = 2) -> list[str]:
    """只保留命中行与其邻近行，避免把整个页面都留给 LLM。"""
    keep: set[int] = set()
    for index, line in enumerate(lines):
        if pattern.search(line):
            low = max(0, index - radius)
            high = min(len(lines), index + radius + 1)
            keep.update(range(low, high))
    return [line for index, line in enumerate(lines) if index in keep]

_FOCUS_PATTERNS: dict[str, "re.Pattern[str]"] = {
    "price_table": re.compile(
        (
            r"[￥¥$€£]\s?\d|\d+\s?/\s?(?:月|年|季)|每\s?百万|per\s+1m|"
            r"input|output|价格|定价|计费|套餐|订阅"
        ),
        re.I,
    ),
    "release_block": re.compile(r"新增|上线|发布|推出|支持|调整|修复|版本|v?\d+\.\d+", re.I),
    "store_block": re.compile(r"版本|version|v?\d+\.\d+|评分|rating|更新|what's new", re.I),
}


def _extract_rss_items(raw_html: str) -> str:
    """RSS/Atom 只取条目标题集合——这是最稳定的"变了什么"信号。"""
    if feedparser is not None:
        try:
            parsed = feedparser.parse(raw_html)
            titles = [(entry.get("title") or "").strip() for entry in parsed.entries]
            titles = [title for title in titles if title]
            if titles:
                return "\n".join(titles)
        except Exception:  # noqa: BLE001 - 解析失败就退回下面的正则
            pass

    items = _ITEM_RE.findall(raw_html)
    titles: list[str] = []
    for _, body in items:
        matched = _TITLE_RE.search(body)
        if not matched:
            continue
        title = _CDATA_RE.sub(r"\1", matched.group(1))
        titles.append(_ANY_TAG_RE.sub(" ", title).strip())
    return "\n".join(t for t in titles if t)


def extract_text(raw_html: str, cfg: SourceTypeConfig) -> str:
    """按注册表的 extractor 策略提取正文，并做空白归一化与噪声剥离。"""
    if cfg.extractor == "rss":
        text = _extract_rss_items(raw_html)
        if not text.strip() and cfg.rss_fallback_to_html:
            text = _extract_article_text(raw_html)
    else:
        text = _extract_article_text(raw_html)
        focus = _FOCUS_PATTERNS.get(cfg.extractor)
        if focus is not None:
            lines = normalize_text(text).splitlines()
            focused = _focused_lines(lines, focus)
            # 聚焦后若只剩零星内容，宁可保留全文，避免把有效正文误判为空
            if sum(len(line) for line in focused) >= settings.crawl_min_text_length:
                text = "\n".join(focused)
    # 先归一化再剥离噪声：噪声行（相对时间/浏览量等）整行丢弃，
    # 保证进入 hash 与 diff 的都是"有意义的文本"。
    return strip_noise(normalize_text(text))


def compute_hash(text: str) -> str:
    """内容指纹：先用它粗筛是否变化，避免无谓的全文 Diff。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def persist_raw_html(competitor_id: int, source_id: int, raw_html: str) -> str | None:
    """原始 HTML 落盘，返回相对 backend 的路径；关掉落盘开关则返回 None。"""
    if not settings.save_raw_html or not raw_html:
        return None
    folder = Path(settings.storage_dir) / str(competitor_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{source_id}_{int(time.time())}.html"
    path.write_text(raw_html, encoding="utf-8")
    try:
        return str(path.relative_to(BACKEND_DIR)).replace("\\", "/")
    except ValueError:  # 存储目录被配置到 backend 之外
        return str(path).replace("\\", "/")
