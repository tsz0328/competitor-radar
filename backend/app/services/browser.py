"""浏览器渲染层：给需要 JS 执行的页面兜底（里程碑 6 留下的最后一块）。

三条硬约束（对应 docs/architecture.md 的性能要点）：

1. **复用单例 browser context**——Playwright 单次抓取约 1-3 秒、内存占用高，
   每次抓取新建浏览器是明确的反模式；这里进程内只 launch 一次。
2. **懒启动**——绝大多数页面走 httpx 毫秒级就能拿到，应用启动不拉浏览器，
   第一次真正需要渲染时才初始化；关闭时随 lifespan 释放。
3. **失败收敛**——Chromium 没装、页面加载失败等都返回 ok=False 的结果，
   绝不抛穿抓取主流程；`availability_note()` 给上层拼提示用。

本模块不导入 crawler（crawler 会导入本模块），避免循环依赖。
"""
import asyncio
import logging
import time
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.http_errors import explain_http_status
from app.core.network import validate_remote_url

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class RenderResult:
    """一次浏览器渲染的结果（crawler 会转成统一的 FetchResult）。"""

    ok: bool
    url: str = ""
    html: str = ""
    http_status: int | None = None
    error: str = ""
    elapsed_ms: int = 0


_lock = asyncio.Lock()
_playwright = None
_context = None
# None = 还没探测过；False = 确认不可用（没装内核/启动失败），之后不再重试
_available: bool | None = None
# 启动失败的真实原因（诊断用）；availability_note() 直接引用它
_unavailable_reason: str = ""


def _clean_error(message: str, limit: int = 300) -> str:
    import re

    return re.sub(r"\s+", " ", (message or "").strip())[:limit]


def _error_chain(exc: BaseException) -> list[BaseException]:
    """展开异常的 cause/context 链——Playwright 会把底层错误包一层再抛。"""
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _diagnose(exc: BaseException) -> str:
    """把启动失败的异常翻译成一句"能照着做"的提示。

    注意：**不是所有失败都是缺内核**——Windows 下 `uvicorn --reload` 会让
    uvicorn>=0.36 回退到 SelectorEventLoop，而该事件循环不支持创建子进程，
    Playwright 的驱动进程就起不来（表现为 NotImplementedError）。
    这种情况装多少次 chromium 都没用，必须换回 ProactorEventLoop。
    """
    text = _clean_error(str(exc), 200)
    kinds = {type(item).__name__ for item in _error_chain(exc)}

    if "Executable doesn't exist" in text or "playwright install" in text:
        return "内核缺失，在 backend 目录执行 playwright install chromium 后重启后端"
    if "NotImplementedError" in kinds:
        return (
            "当前事件循环不支持创建子进程（Windows 下 uvicorn --reload 会启用 "
            "SelectorEventLoop）：请用 `python run_dev.py` 启动，或去掉 --reload、"
            "或加 `--loop asyncio:ProactorEventLoop`"
        )
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def availability_note() -> str:
    """浏览器不可用时的说明文案；可用返回空串（给失败原因拼一句话）。"""
    if _available is False:
        return f"（浏览器渲染不可用：{_unavailable_reason or '原因未知，见后端日志'}）"
    return ""


async def _ensure_context():
    """懒启动并复用浏览器上下文；不可用时返回 None 并记住结论。"""
    global _playwright, _context, _available, _unavailable_reason
    if _context is not None:
        return _context
    if _available is False or not settings.browser_render_enabled:
        return None

    async with _lock:  # 并发首抓时只初始化一次
        if _context is not None:
            return _context
        start = time.perf_counter()
        try:
            from playwright.async_api import async_playwright

            _playwright = await async_playwright().start()
            browser = await _playwright.chromium.launch(headless=True)
            _context = await browser.new_context(
                user_agent=settings.crawl_user_agent,
                locale="zh-CN",
                viewport={"width": 1440, "height": 900},
            )
            if settings.browser_block_assets:
                await _block_assets(_context)
            _available = True
            logger.info(
                "浏览器渲染就绪（chromium，启动耗时 %dms）",
                int((time.perf_counter() - start) * 1000),
            )
            return _context
        except Exception as exc:  # noqa: BLE001 - 内核缺失/启动失败都要优雅降级
            _available = False
            _unavailable_reason = _diagnose(exc)
            logger.warning("浏览器渲染不可用，已降级为仅 httpx：%s", _unavailable_reason)
            logger.debug("浏览器启动失败详情", exc_info=True)
            return None


async def _block_assets(context) -> None:
    """屏蔽图片/字体/媒体：正文提取用不到，省带宽也显著加快渲染。"""
    blocked = {"image", "media", "font"}

    async def _handler(route):
        if route.request.resource_type in blocked:
            await route.abort()
        else:
            await route.continue_()

    await context.route("**/*", _handler)


async def fetch_rendered(url: str) -> RenderResult:
    """用真实浏览器渲染一个页面，返回执行完 JS 之后的 HTML。"""
    start = time.perf_counter()
    validation = await validate_remote_url(url)
    if not validation.ok:
        return RenderResult(
            ok=False, url=url, error=validation.message, elapsed_ms=_elapsed_ms(start)
        )
    context = await _ensure_context()
    if context is None:
        return RenderResult(
            ok=False,
            url=url,
            error="浏览器渲染不可用" + availability_note(),
            elapsed_ms=_elapsed_ms(start),
        )

    page = await context.new_page()
    try:
        # domcontentloaded 先确保主文档到达；SPA 的数据再由 networkidle 尽力等
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=settings.browser_timeout_seconds * 1000,
        )
        try:
            await page.wait_for_load_state(
                "networkidle", timeout=settings.browser_network_idle_seconds * 1000
            )
        except Exception:  # noqa: BLE001 - 长轮询站点永不空闲，等到上限就继续
            pass

        html = await page.content()
        final_validation = await validate_remote_url(page.url)
        if not final_validation.ok:
            return RenderResult(
                ok=False,
                url=page.url,
                error=final_validation.message,
                elapsed_ms=_elapsed_ms(start),
            )
        status = response.status if response else None
        if status is not None and status >= 400:
            return RenderResult(
                ok=False,
                url=url,
                http_status=status,
                error=explain_http_status(status),
                elapsed_ms=_elapsed_ms(start),
            )
        return RenderResult(
            ok=True, url=url, http_status=status, html=html, elapsed_ms=_elapsed_ms(start)
        )
    except Exception as exc:  # noqa: BLE001 - 渲染失败不让主流程炸掉
        return RenderResult(
            ok=False,
            url=url,
            error=_clean_error(f"渲染失败：{type(exc).__name__}: {exc}"),
            elapsed_ms=_elapsed_ms(start),
        )
    finally:
        await page.close()  # 只关页签，浏览器与 context 复用


async def close_browser() -> None:
    """随应用关闭释放浏览器资源。"""
    global _playwright, _context
    if _context is None and _playwright is None:
        return
    try:
        if _context is not None:
            await _context.close()
        if _playwright is not None:
            await _playwright.stop()
        logger.info("浏览器渲染资源已释放")
    except Exception as exc:  # noqa: BLE001 - 关闭阶段别让清理异常打断退出
        logger.warning("释放浏览器资源时出错：%s", _clean_error(str(exc), 200))
    finally:
        _context = None
        _playwright = None


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
