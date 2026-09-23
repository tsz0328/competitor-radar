"""密码登录失败限流。

按账号和客户端 IP 两个维度记录失败次数。账号维度的作用是防止攻击者枚举同一个
账号并绕过「换 IP 就清零」的策略；IP 维度则挡住同源批量探测。两个维度都使用
固定时间窗口：连续失败达到阈值后整窗冷却，成功后只清账号计数，不清 IP 计数。

账号输入会先做摘要再进缓存 key，避免把登录邮箱原样写进 Redis / 内存缓存。
"""

import hashlib
import json
import time

from fastapi import Request

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.exceptions import ERR_LOGIN_TOO_FREQUENT, BusinessError


def _now() -> float:
    return time.time()


def _cache_key(namespace: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"login:fail:{namespace}:{digest}"


def _account_key(value: str | int) -> str:
    return _cache_key("account", str(value))


def _ip_key(value: str) -> str:
    return _cache_key("ip", value)


def client_ip(request: Request) -> str:
    """读取真实客户端 IP；只有显式配置可信代理后才采纳 X-Forwarded-For。"""
    trusted = get_settings().trusted_proxy_count
    if trusted <= 0:  # noqa: SIM103
        return request.client.host if request.client and request.client.host else "unknown"

    forwarded = request.headers.get("x-forwarded-for", "")
    chain = [part.strip() for part in forwarded.split(",") if part.strip()]
    if not chain:
        return request.client.host if request.client and request.client.host else "unknown"

    # 从最右端按可信代理数量往外取。例如一个可信反代时，最右项是它添加的
    # 「请求来源 IP」；直接采用 HTTP 头最左项会把头部交给任意客户端伪造。
    candidate = chain[-trusted]
    return candidate or "unknown"


def _read_window(raw: str | None) -> tuple[float, int] | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
        started, count = float(value[0]), int(value[1])
    except (TypeError, ValueError, IndexError, json.JSONDecodeError):
        return None
    return started, count


def _window_value(count: int) -> str:
    return json.dumps([_now(), count], separators=(",", ":"))


async def _raise_if_blocked(keys: list[str]) -> None:
    settings = get_settings()
    for key in keys:
        state = _read_window(await get_cache().get(key))
        if state is None:
            continue
        started, count = state
        remaining = settings.login_failure_window_seconds - (_now() - started)
        if count >= settings.login_failure_limit and remaining > 0:
            minutes = max(1, int(remaining // 60) + (1 if remaining % 60 else 0))
            raise BusinessError(
                ERR_LOGIN_TOO_FREQUENT,
                f"登录失败次数过多，请 {minutes} 分钟后再试",
                429,
            )
        if remaining <= 0:
            await get_cache().delete(key)


async def _record(key: str) -> None:
    settings = get_settings()
    state = _read_window(await get_cache().get(key))
    if state is None:
        count = 1
    else:
        started, current = state
        count = current + 1 if _now() - started < settings.login_failure_window_seconds else 1
    await get_cache().set(
        key,
        _window_value(count),
        settings.login_failure_window_seconds,
    )


async def ensure_allowed(request: Request, account: str) -> None:
    """在查询账号前检查：输入标识与客户端 IP 任一项冷却中就拒绝。"""
    await _raise_if_blocked([_account_key(account), _ip_key(client_ip(request))])


async def ensure_user_allowed(user_id: int) -> None:
    """账号可通过用户名或邮箱登录，按稳定 user_id 再检查一次冷却状态。"""
    await _raise_if_blocked([_account_key(user_id)])


async def record_failure(request: Request, identity: str | int) -> None:
    """记录一次凭据失败；未知账号记输入标识，已知账号记 user_id。"""
    await _record(_account_key(identity))
    await _record(_ip_key(client_ip(request)))


async def clear_account_failures(account: str, user_id: int) -> None:
    """登录成功后清掉本次输入标识和稳定 user_id 的失败计数。"""
    cache = get_cache()
    await cache.delete(_account_key(account))
    await cache.delete(_account_key(user_id))
