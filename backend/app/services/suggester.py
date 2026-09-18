"""竞品智能预填：根据「竞品名称」猜官网地址与分类。

策略（按可靠性递减）：
1. LLM：能处理中文品牌名、名称与域名不一致的情况（如 豆包 → doubao.com），
   返回域名 + 分类；随后仍会**实际探活**确认域名可达。
2. 域名探测兜底：把名称转成候选域名（name.com / name.io / name.ai …）并发探活，
   并要求落地页与名称相关（域名含名称，或标题含名称），顺带过滤"域名出售"页。
无 Key 或 LLM 失败时自动走 2，保证功能不依赖 LLM 可用性。
"""
import asyncio
import html as html_lib
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.llm import get_llm_client
from app.services import crawler

settings = get_settings()
logger = logging.getLogger(__name__)

# 探测用 TLD，按"品牌官网常见度"排序（com/cn 优先，命中概率最高）
_TLDS = ("com", "cn", "io", "ai", "co", "app", "so", "dev", "org", "net")
# 只做 ASCII 名称的域名探测；中文等名称交给 LLM
_ASCII_NAME_RE = re.compile(r"^[a-z0-9\s\-_.]+$", re.I)
_NAME_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}$")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
# 停放/出售域名的典型文案，命中即排除
_PARKED_HINTS = ("for sale", "buy this domain", "domain is for sale", "待售", "出售", "域名出售")
_MAX_CONCURRENCY = 6


@dataclass
class SuggestResult:
    """预填结果；official_url / category 可能为 None（没识别出来）。"""

    official_url: str | None = None
    category: str | None = None
    source: str = "none"  # llm | probe | none
    message: str = ""


def _short_timeout() -> float:
    return min(settings.check_url_timeout_seconds, 8.0)


def _tokens(name: str) -> list[str]:
    """把名称转成可做域名的 token：'Open AI' → ['openai', 'open']，'Notion' → ['notion']。"""
    lowered = name.strip().lower()
    if not lowered or not _ASCII_NAME_RE.fullmatch(lowered):
        return []
    parts = [p for p in _NAME_SPLIT_RE.split(lowered) if p]
    if not parts:
        return []
    tokens = ["".join(parts)]  # open ai → openai
    if len(parts) > 1:
        tokens.append(parts[0])  # notion labs → notion
    return list(dict.fromkeys(tokens))


def _title(html: str) -> str:
    match = _TITLE_RE.search(html or "")
    return html_lib.unescape(" ".join(match.group(1).split())) if match else ""


def _related(name: str, token: str, final_url: str, html: str) -> bool:
    """落地页是否确实与该名称相关：域名含 token，或标题含名称。"""
    title = _title(html).lower()
    if any(hint in title for hint in _PARKED_HINTS):
        return False
    host = urlparse(final_url).netloc.lower().removeprefix("www.")
    if token and token in host:
        return True
    return name.strip().lower() in title


async def _probe(name: str) -> str | None:
    """并发探测候选域名，返回第一个"可达且相关"的最终地址。

    用 as_completed 实现"首个命中即返回并取消其余"，避免 gather 等所有候选都超时
    （无网络/慢网络下会累积到 最长超时 × 批次数，名称失焦预填因此卡十几秒）。
    """
    tokens = _tokens(name)
    if not tokens:
        return None

    # 按"品牌官网常见度"排序，命中概率高的先试（也利于首个完成即返回）
    candidates = [
        (token, f"https://{token}.{tld}") for token in tokens for tld in _TLDS
    ]
    probe_timeout = min(settings.check_url_timeout_seconds, 4.0)
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _check(item: tuple[str, str]):
        token, url = item
        async with sem:
            res = await crawler.fetch_html(url, timeout=probe_timeout)
        return item, res

    tasks = [asyncio.create_task(_check(c)) for c in candidates]
    try:
        for coro in asyncio.as_completed(tasks):
            _item, res = await coro
            token, _url = _item
            if res.ok and _related(name, token, res.url, res.html):
                return res.url
        return None
    finally:
        for t in tasks:
            t.cancel()


async def _verify_domain(domain: str) -> str | None:
    """把 LLM 给的域名规范化并实际探活，返回最终地址（跟随跳转）。

    优先采用 www 形式（很多官网规范地址带 www，如 deepseek.com → www.deepseek.com），
    www 不通再退回裸域名，保证常见品牌也能识别。
    """
    domain = (domain or "").strip().lower().removeprefix("www.")
    if not _DOMAIN_RE.fullmatch(domain):
        return None
    for cand in (f"www.{domain}", domain):
        res = await crawler.fetch_html(f"https://{cand}", timeout=_short_timeout())
        if res.ok:
            return res.url
    return None


async def suggest_competitor(
    name: str, categories: list[str], use_llm: bool = True
) -> SuggestResult:
    name = (name or "").strip()
    if not name:
        return SuggestResult(None, None, "none", "请输入竞品名称")

    category: str | None = None
    llm = get_llm_client()
    # 仅当显式允许且 LLM 可用时才调 AI；否则（用户自己填竞品的自动预填）直接走规则探测
    if use_llm and llm.enabled:
        profile = await llm.brand_profile(name, categories)
        if profile:
            category = profile.category or None
            if profile.domain:
                url = await _verify_domain(profile.domain)
                if url:
                    return SuggestResult(url, category, "llm", f"AI 推断官网：{url}")

    url = await _probe(name)
    if url:
        return SuggestResult(url, category, "probe", f"自动探测到官网：{url}")
    if category:
        return SuggestResult(None, category, "llm", "已推断分类，官网请手动填写")
    return SuggestResult(None, None, "none", "未能自动识别，请手动填写")
