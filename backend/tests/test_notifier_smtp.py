"""SMTP 发信单元测试：覆盖 `_send_smtp` 的协议分支与配置缺失报错。

用 mock 掉 `smtplib.SMTP_SSL` / `smtplib.SMTP` 的方式验证——不需要真实 SMTP 账号，
钉住「465 走 SSL、其他端口走 SMTP+STARTTLS」两条分支，以及缺收件人/服务器/凭据时
抛出的中文报错（管理员在「发送测试邮件」里能看到的具体原因）。
"""

import asyncio

import pytest

from app.services import notifier


class _FakeSMTPClient:
    """记录一次 SMTP 会话被调用到的方法序列，供断言两条分支行为差异。"""

    created: list["_FakeSMTPClient"] = []

    def __init__(self, host: str, port: int, timeout: int = 15):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.startedtls = False
        self.credentials: tuple[str, str] | None = None
        self.sent = 0
        _FakeSMTPClient.created.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        self.startedtls = True

    def login(self, user: str, password: str):
        self.credentials = (user, password)

    def send_message(self, mail):
        self.sent += 1


@pytest.fixture(autouse=True)
def _reset_client_registry():
    """清掉跨测试累积的会话记录，保证每个用例只看到自己创建的那个客户端。"""
    _FakeSMTPClient.created.clear()
    yield


def _call(port: int) -> None:
    notifier._send_smtp(
        "标题",
        "正文",
        ["to@example.com"],
        "sender@example.com",
        "smtp.example.com",
        port,
        "user",
        "pass",
    )


def test_ssl_branch_on_465(monkeypatch) -> None:
    """465 端口必须走 SMTP_SSL，直接 login+send，绝不 STARTTLS。"""
    monkeypatch.setattr(notifier.smtplib, "SMTP_SSL", _FakeSMTPClient)
    _call(465)
    client = _FakeSMTPClient.created[-1]
    assert client.port == 465
    assert client.startedtls is False
    assert client.credentials == ("user", "pass")
    assert client.sent == 1


def test_starttls_branch_on_587(monkeypatch) -> None:
    """非 465（如 587）必须走 SMTP + STARTTLS 加密后再 login+send。"""
    monkeypatch.setattr(notifier.smtplib, "SMTP", _FakeSMTPClient)
    _call(587)
    client = _FakeSMTPClient.created[-1]
    assert client.port == 587
    assert client.startedtls is True
    assert client.credentials == ("user", "pass")
    assert client.sent == 1


def test_missing_recipients_raises() -> None:
    """没传收件人（且 NOTIFY_RECIPIENTS 也没配）时，明确报「未配置收件人」。"""
    with pytest.raises(RuntimeError, match="收件人"):
        notifier._send_smtp("t", "m", [], "s@example.com", "h", 465, "u", "p")


def test_missing_host_raises() -> None:
    """SMTP_HOST 为空时，明确报「未配置 SMTP 服务器」。"""
    with pytest.raises(RuntimeError, match="SMTP 服务器"):
        notifier._send_smtp("t", "m", ["to@example.com"], "s@example.com", "", 465, "u", "p")


def test_missing_credentials_raises() -> None:
    """用户名或授权码为空时，明确报「未配置 SMTP 用户名或授权码」。"""
    with pytest.raises(RuntimeError, match="用户名或授权码"):
        notifier._send_smtp("t", "m", ["to@example.com"], "s@example.com", "h", 465, "", "")


def test_email_switch_off_skips_send(monkeypatch) -> None:
    """用户关闭「接收邮件通知」开关（email_enabled=False）时，notify 直接返回 False，
    且不发起任何 SMTP 连接——即使全局 notify_enabled 开启、后端设为 smtp。

    钉住 2026-09-22 新增的开关链路末端：开关关闭是用户的主动选择，不是配置错误，
    不应尝试发信、也不应告警。
    """
    monkeypatch.setattr(notifier.settings, "notify_enabled", True)
    monkeypatch.setattr(notifier.settings, "notify_backend", "smtp")
    monkeypatch.setattr(notifier.smtplib, "SMTP_SSL", _FakeSMTPClient)
    monkeypatch.setattr(notifier.smtplib, "SMTP", _FakeSMTPClient)

    result = asyncio.run(
        notifier.notify("t", "m", to=["to@example.com"], email_enabled=False)
    )
    assert result is False
    assert _FakeSMTPClient.created == [], "开关关闭时不应建立任何 SMTP 会话"


def test_email_switch_on_still_sends(monkeypatch) -> None:
    """开关开启（默认 email_enabled=True）时，notify 正常走发送分支（log 后端返回 True）。"""
    monkeypatch.setattr(notifier.settings, "notify_enabled", True)
    monkeypatch.setattr(notifier.settings, "notify_backend", "log")

    result = asyncio.run(
        notifier.notify("t", "m", to=["to@example.com"], email_enabled=True)
    )
    assert result is True