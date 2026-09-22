"""竞品图标的"解析一次、落库、全站复用"链路。

覆盖三件不依赖网络、却最容易出错的事：
1. 从抓取时已下载的首页 HTML 里挑图标（优先级 + 相对地址解析）；
2. 事件响应里优先用落库图标，没有才回退官网 favicon；
3. 竞品响应的同一套回退规则。
"""
from datetime import datetime, timezone

from unittest.mock import AsyncMock, MagicMock, patch

from app.core.source_registry import SourceType
from app.schemas.competitor import CompetitorOut
from app.schemas.event import EventRecordOut
from app.services.favicon import (
    _probe,
    _registrable_domain,
    _same_domain,
    pick_icon_from_html,
)


class TestPickIconFromHtml:
    def test_prefers_apple_touch_icon_over_favicon(self) -> None:
        html = (
            '<head><link rel="icon" href="/favicon.ico">'
            '<link rel="apple-touch-icon" sizes="180x180" href="//cdn.example.com/icon.png">'
            "</head>"
        )
        # apple-touch-icon 最清晰，优先；//cdn 这种协议相对地址要补成 https
        assert (
            pick_icon_from_html(html, "https://www.example.com/")
            == "https://cdn.example.com/icon.png"
        )

    def test_resolves_relative_href(self) -> None:
        html = '<link rel="shortcut icon" href="/static/logo.svg">'
        assert (
            pick_icon_from_html(html, "https://example.com/pricing")
            == "https://example.com/static/logo.svg"
        )

    def test_ignores_data_url_and_non_icon_links(self) -> None:
        html = (
            '<link rel="icon" href="data:image/png;base64,AAAA">'
            '<link rel="stylesheet" href="/a.css">'
        )
        assert pick_icon_from_html(html, "https://example.com/") is None

    def test_returns_none_when_page_has_no_icon(self) -> None:
        assert pick_icon_from_html("<html><body>hi</body></html>", "https://a.com/") is None


def _event(**overrides) -> EventRecordOut:
    base = dict(
        id=1,
        competitor_id=7,
        competitor_name="豆包",
        competitor_domain="https://www.doubao.com",
        source_name="官网首页",
        event_type="new_feature",
        title="新增功能",
        summary="摘要",
        created_at=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    )
    return EventRecordOut(**{**base, **overrides})


class TestEventLogoFallback:
    def test_uses_stored_logo_when_present(self) -> None:
        record = _event(competitor_logo_url="https://cdn.example.com/icon.png")
        assert record.logo_url == "https://cdn.example.com/icon.png"

    def test_falls_back_to_official_favicon(self) -> None:
        # 回退地址会去掉 www（与 clean_host 口径一致）
        assert _event().logo_url == "https://doubao.com/favicon.ico"

    def test_no_domain_means_no_logo(self) -> None:
        assert _event(competitor_domain="").logo_url is None

    def test_stored_logo_is_not_exposed_as_extra_field(self) -> None:
        """它是内部输入字段，不该多出一个同义字段给前端。"""
        dumped = _event(competitor_logo_url="https://cdn.example.com/icon.png").model_dump(
            by_alias=True
        )
        assert "competitorLogoUrl" not in dumped
        assert dumped["logoUrl"] == "https://cdn.example.com/icon.png"


class TestCompetitorLogoFallback:
    def _out(self, **overrides) -> CompetitorOut:
        base = dict(
            id=1,
            user_id=1,
            name="豆包",
            official_url="https://www.doubao.com",
            category="AI产品",
            status="active",
            created_at=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
            sources=[],
        )
        return CompetitorOut(**{**base, **overrides})

    def test_uses_stored_logo_when_present(self) -> None:
        out = self._out(logo_url="https://cdn.example.com/icon.png")
        assert out.logo_url == "https://cdn.example.com/icon.png"

    def test_falls_back_to_official_favicon(self) -> None:
        # 老数据（还没抓过首页）落库值是空串 → 回退官网 favicon（同样去掉 www）
        assert self._out(logo_url="").logo_url == "https://doubao.com/favicon.ico"

    def test_no_official_url_keeps_empty(self) -> None:
        assert self._out(official_url=None, logo_url="").logo_url == ""


def test_source_type_constant_used_by_logo_capture() -> None:
    """图标只在抓官网首页时记录，这里钉住那个判断用的常量。"""
    assert SourceType.HOMEPAGE == "homepage"


class TestSameDomain:
    def test_same_registrable_domain_ignores_subdomain_and_www(self) -> None:
        assert _same_domain("example.com", "www.example.com")
        assert _same_domain("www.example.com", "a.b.example.com")
        assert _same_domain("http://example.com/", "https://www.example.com/pricing")

    def test_different_registrable_domain_detected(self) -> None:
        # linear.com 已被 Analog Devices 收购，跳转到 analog.com —— 视为不同域
        assert not _same_domain("linear.com", "www.analog.com")
        assert not _same_domain("doubao.com", "analog.com")

    def test_registrable_domain_extraction(self) -> None:
        assert _registrable_domain("www.example.com") == "example.com"
        assert _registrable_domain("a.b.example.com") == "example.com"
        assert _registrable_domain("example.com") == "example.com"


class TestProbeRejectsCrossDomainRedirect:
    @patch("app.services.favicon.httpx.AsyncClient")
    async def test_returns_none_on_cross_domain_redirect(self, client_cls: MagicMock) -> None:
        # linear.com 跳转到 analog.com（域名被收购）→ 应放弃解析，不返回对方图标
        redirect = MagicMock()
        redirect.status_code = 200
        redirect.headers = {"content-type": "text/html; charset=utf-8"}
        redirect.text = '<link rel="icon" href="/media/favicon/adi-icon.png">'
        redirect.url = "https://www.analog.com/"

        instance = client_cls.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=redirect)

        with patch(
            "app.services.favicon.validate_remote_url",
            new=AsyncMock(return_value=MagicMock(ok=True)),
        ):
            result = await _probe("linear.com")
        assert result is None

    @patch("app.services.favicon.httpx.AsyncClient")
    async def test_follows_same_domain_www_redirect(self, client_cls: MagicMock) -> None:
        # example.com → www.example.com 是同源跳转，应继续解析并拿到图标
        page = MagicMock()
        page.status_code = 200
        page.headers = {"content-type": "text/html; charset=utf-8"}
        page.text = '<link rel="apple-touch-icon" href="/touch.png">'
        page.url = "https://www.example.com/"

        image = MagicMock()
        image.status_code = 200
        image.headers = {"content-type": "image/png"}

        instance = client_cls.return_value.__aenter__.return_value

        async def _fake_get(url: str, **_kwargs):
            if url == "https://example.com/":
                return page
            return image

        instance.get = AsyncMock(side_effect=_fake_get)

        with patch(
            "app.services.favicon.validate_remote_url",
            new=AsyncMock(return_value=MagicMock(ok=True)),
        ):
            result = await _probe("example.com")
        assert result == "https://www.example.com/touch.png"
