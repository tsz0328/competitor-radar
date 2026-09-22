"""智能预填的"相关性把关"：LLM 猜出的域名即使可达，也要与竞品名称相关才接受。

之前 `_verify_domain` 只查 HTTP 可达性，LLM（brand_profile）仅凭记忆、不联网，
可能吐出"可达但不相关"的域名被误当官网；现在复用 `_related` 把关，
与规则探测路径（_probe）保持同一套判定口径。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.suggester import _related, _tokens, _verify_domain


def _mk_res(ok=True, url="https://example.com/", html="", status=200):
    return SimpleNamespace(
        ok=ok, url=url, http_status=status, html=html, error="", elapsed_ms=1, attempts=1
    )


class TestVerifyDomainRelevance:
    @patch("app.services.suggester.crawler.fetch_html", new_callable=AsyncMock)
    async def test_accepts_related_llm_domain(self, fetch) -> None:
        # 通义千问 → tongyi.cn，落地页标题含中文名 → 接受
        fetch.return_value = _mk_res(
            url="https://www.tongyi.cn/",
            html="<title>通义千问 - 阿里云</title>",
        )
        assert await _verify_domain("tongyi.cn", "通义千问") == "https://www.tongyi.cn/"

    @patch("app.services.suggester.crawler.fetch_html", new_callable=AsyncMock)
    async def test_accepts_ascii_token_in_host(self, fetch) -> None:
        # Linear → linear.app，域名含名称 token（不依赖标题） → 接受
        fetch.return_value = _mk_res(
            url="https://linear.app/",
            html="<title>Linear</title>",
        )
        assert await _verify_domain("linear.app", "Linear") == "https://linear.app/"

    @patch("app.services.suggester.crawler.fetch_html", new_callable=AsyncMock)
    async def test_rejects_unrelated_reachable_domain(self, fetch) -> None:
        # 把品牌名拼音拼成一个"可达但不相关"的站点（linear.com 跳 analog.com 的同类情况）
        fetch.return_value = _mk_res(
            url="https://analog.com/",
            html="<title>Analog Devices | Semiconductor</title>",
        )
        # 名称 token 不在 host、名称不在标题 → 拒绝
        assert await _verify_domain("analog.com", "Linear") is None

    @patch("app.services.suggester.crawler.fetch_html", new_callable=AsyncMock)
    async def test_rejects_parked_domain(self, fetch) -> None:
        fetch.return_value = _mk_res(
            url="https://placeholder.io/",
            html="<title>Buy this domain - for sale</title>",
        )
        assert await _verify_domain("placeholder.io", "Whatever") is None

    @patch("app.services.suggester.crawler.fetch_html", new_callable=AsyncMock)
    async def test_rejects_unreachable_domain(self, fetch) -> None:
        fetch.return_value = _mk_res(ok=False, url="https://nope.invalid/", html="")
        assert await _verify_domain("nope.invalid", "X") is None

    @patch("app.services.suggester.crawler.fetch_html", new_callable=AsyncMock)
    async def test_rejects_malformed_domain(self, fetch) -> None:
        # 没法形成合法域名的内容（含空格/路径）直接返回 None，且不发起网络请求
        assert await _verify_domain("not a domain", "X") is None
        fetch.assert_not_called()

    def test_related_tokens(self) -> None:
        # 中文名无法转 token（交给 LLM 路径），_tokens 返回空
        assert _tokens("通义千问") == []
        # ASCII 名转成可拼域名的 token
        assert _tokens("Open AI") == ["openai", "open"]
        assert _tokens("Notion") == ["notion"]

    def test_related_judgement(self) -> None:
        # 标题含名称 → 相关
        assert _related("通义千问", "", "https://www.tongyi.cn/", "<title>通义千问 - 阿里云</title>")
        # host 含 token → 相关
        assert _related("Linear", "linear", "https://linear.app/", "<title>Linear</title>")
        # 停放页 → 不相关
        assert not _related("X", "", "https://p.io/", "<title>Buy this domain - for sale</title>")
        # 既不含 token 也不含名称 → 不相关
        assert not _related("Linear", "linear", "https://analog.com/", "<title>Analog</title>")
