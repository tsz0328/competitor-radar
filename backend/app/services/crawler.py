"""抓取层：把页面拿回来并提取正文。纯 IO，不碰数据库。

设计要点：
- 正文提取优先用 trafilatura（装了就用，正文更干净、Diff 噪声更少）；
  没装则退回内置解析——保证零额外依赖也能跑通整条链路。
- 所有失败都收敛成 FetchResult.ok=False，不抛异常给上层。
- 日志只记 URL / 类型 / 耗时 / 状态码 / 错误摘要，不记正文。
"""
import hashlib
import html as html_lib
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import BACKEND_DIR, get_settings
from app.core.source_registry import SourceTypeConfig

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


# ---- 内置的轻量正文提取（无第三方依赖）----
_DROP_BLOCK_RE = re.compile(
    r"<(script|style|noscript|template|svg|iframe)\b[^>]*>.*?</\1>", re.I | re.S
)
_BLOCK_END_RE = re.compile(
    r"</(p|div|li|tr|h[1-6]|section|article|header|footer|br)\s*>", re.I
)
_ANY_TAG_RE = re.compile(r"<[^>]+>")

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


async def fetch_html(url: str) -> FetchResult:
    """GET 一个页面。网络错误与 4xx/5xx 都返回 ok=False。"""
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.crawl_timeout_seconds,
            headers={
                "User-Agent": settings.crawl_user_agent,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        return FetchResult(
            ok=False,
            url=url,
            error=_clean_error(f"请求失败：{type(exc).__name__}: {exc}"),
            elapsed_ms=_ms(start),
        )

    elapsed = _ms(start)
    if response.status_code >= 400:
        return FetchResult(
            ok=False,
            url=url,
            http_status=response.status_code,
            error=f"HTTP {response.status_code}",
            elapsed_ms=elapsed,
        )
    return FetchResult(
        ok=True,
        url=str(response.url),
        http_status=response.status_code,
        html=response.text,
        elapsed_ms=elapsed,
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


def _html_to_text(raw_html: str) -> str:
    """内置解析兜底：去脚本样式 → 块级标签转换行 → 剥标签 → 反转义。"""
    text = _DROP_BLOCK_RE.sub(" ", raw_html)
    text = _BLOCK_END_RE.sub("\n", text)
    text = _ANY_TAG_RE.sub(" ", text)
    return html_lib.unescape(text)


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
    """按注册表的 extractor 策略提取正文，并做空白归一化。"""
    if cfg.extractor == "rss":
        text = _extract_rss_items(raw_html)
    elif trafilatura is not None:
        text = trafilatura.extract(
            raw_html, include_comments=False, include_tables=True
        ) or _html_to_text(raw_html)
    else:
        text = _html_to_text(raw_html)
    return normalize_text(text)


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
