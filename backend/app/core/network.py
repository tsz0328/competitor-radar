"""对外抓取 URL 的校验：把常见的 SSRF 入口挡在请求真正发出之前。

覆盖两类请求：
- 用户提交的 `check-url` / `discover-sources` / `suggest` 地址；
- 数据库中已被篡改或被历史数据带入的监控地址。

这里会同时校验初始 URL 与请求完成后的最终 URL。解析层校验是防御性的，
重定向和 DNS 解析仍有正常业务语义，保持不变。

地址分两类处理：
- 回环 / 链路本地（127/8、::1、169.254/16、fe80::/10、云元数据）始终拦截——
  它们指向本机或内网基础设施，即使放开私网也不该被服务端主动访问；
- 私网（RFC1918、fc00::/7）由 `allow_private_network_urls` 控制：
  开=放行（风险自负），关=拦截。
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

from app.core.config import get_settings

settings = get_settings()

_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_PORTS = {80, 443}

# 私网地址：是否放行由 allow_private_network_urls 决定
_PRIVATE_BLOCK = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)
# 回环 / 链路本地 / 云元数据：无论私网开关是否打开都拦截
_ALWAYS_BLOCK = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
)


@dataclass(frozen=True)
class URLValidation:
    ok: bool
    message: str = ""


def _parsed_url(url: str) -> tuple[SplitResult, str]:
    text = (url or "").strip()
    parsed = urlsplit(text)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return parsed, "仅允许访问 http:// 或 https:// 地址"
    if parsed.username or parsed.password:
        return parsed, "网址中不能携带用户名或密码"
    hostname = parsed.hostname
    if not hostname:
        return parsed, "网址缺少有效主机名"
    port = parsed.port
    if port is not None and port not in _ALLOWED_PORTS:
        return parsed, "仅允许访问标准 80/443 端口"
    return parsed, ""


def _unsafe_hostname(hostname: str) -> bool:
    if hostname in {"localhost", "localhost.localdomain"}:
        return True
    lowered = hostname.lower()
    if lowered.endswith((".local", ".internal", ".localhost")):
        return True
    return ".metadata.google.internal" in f".{lowered}"


def _unsafe_ip(value: str, *, allow_private: bool) -> bool:
    """该地址是否应被拦截。

    - 回环 / 链路本地永远拦截；
    - 私网是否拦截由 allow_private 决定。
    """
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if any(address in network for network in _ALWAYS_BLOCK):
        return True
    if allow_private:
        return False
    return any(address in network for network in _PRIVATE_BLOCK)


def _validation(message: str) -> URLValidation:
    return URLValidation(False, f"网址不符合访问安全要求：{message}")


async def validate_remote_url(url: str) -> URLValidation:
    """校验一个目标地址；通过则返回 `ok=True`，否则给出一句可展示的原因。"""
    parsed, error = _parsed_url(url)
    if error:
        return _validation(error)
    hostname = parsed.hostname or ""
    if _unsafe_hostname(hostname):
        return _validation("本地保留域名不允许访问")

    allow_private = settings.allow_private_network_urls

    # 主机名本身就是 IP 字面量：直接按 IP 规则校验（含 allow_private 开关）
    if _unsafe_ip(hostname, allow_private=allow_private):
        return _validation("内网、回环或链路本地地址不允许访问")

    # 主机名是域名：解析后逐个地址再校验一遍，防止 DNS rebinding 绕过
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
    except socket.gaierror:
        return URLValidation(True)  # 后续 HTTP 层会给出真正的解析失败原因
    for info in infos:
        address = info[4][0]
        if _unsafe_ip(address, allow_private=allow_private):
            return _validation("域名解析到内网、回环或链路本地地址，不允许访问")
    return URLValidation(True)
