"""密码登录失败限流回归测试。"""

import pytest_asyncio

from app.core.config import get_settings
from app.core.exceptions import ERR_BAD_CREDENTIALS, ERR_LOGIN_TOO_FREQUENT
from app.core.security import hash_password
from app.models.user import User

PASSWORD = "correct-password"
WRONG_PASSWORD = "wrong-password"


@pytest_asyncio.fixture(autouse=True)
async def _fresh_cache():
    """登录计数写进程内缓存，测试间必须新建单例避免跨用例串味。"""
    from app.core import cache as cache_module

    cache_module._cache = None
    yield
    cache_module._cache = None


async def _seed_password_user(session, username: str, email: str | None = None) -> User:
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(PASSWORD),
        password_length=len(PASSWORD),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _login(client, account: str, password: str, ip: str | None = None):
    headers = {"X-Forwarded-For": ip} if ip else None
    return await client.post(
        "/api/auth/login",
        json={"account": account, "password": password},
        headers=headers,
    )


async def test_wrong_password_triggers_account_lockout(
    client, session, monkeypatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    user = await _seed_password_user(session, "guarded", "guarded@example.com")
    assert user.id

    limit = settings.login_failure_limit
    for index in range(limit):
        response = await _login(
            client, user.username, WRONG_PASSWORD, f"198.51.100.{index + 1}"
        )
        assert response.status_code == 401, response.text
        assert response.json()["code"] == ERR_BAD_CREDENTIALS

    # 账号维度冷却：换 IP、换另一个登录标识也不能绕过。
    blocked = await _login(
        client, "guarded@example.com", WRONG_PASSWORD, "198.51.100.99"
    )
    assert blocked.status_code == 429
    assert blocked.json()["code"] == ERR_LOGIN_TOO_FREQUENT


async def test_blocked_account_rejects_correct_password_until_cooldown(
    client, session, monkeypatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    user = await _seed_password_user(session, "locked-user")

    for index in range(settings.login_failure_limit):
        response = await _login(
            client, user.username, WRONG_PASSWORD, f"203.0.113.{index + 1}"
        )
        assert response.status_code == 401

    correct = await _login(client, user.username, PASSWORD, "203.0.113.99")
    assert correct.status_code == 429
    assert correct.json()["code"] == ERR_LOGIN_TOO_FREQUENT

    # 清掉账号冷却后原密码应立即可用，验证之前不是密码本身也被修改。
    from app.core import cache as cache_module

    cache_module._cache = None
    restored = await _login(client, user.username, PASSWORD, "203.0.113.100")
    assert restored.status_code == 200, restored.text


async def test_successful_login_clears_account_failure_count(
    client, session, monkeypatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    user = await _seed_password_user(session, "reset-count")

    for index in range(settings.login_failure_limit - 1):
        response = await _login(
            client, user.username, WRONG_PASSWORD, f"192.0.2.{index + 1}"
        )
        assert response.status_code == 401

    success = await _login(client, user.username, PASSWORD, "192.0.2.99")
    assert success.status_code == 200, success.text

    # 成功后账号计数归零。若未清零，首轮留下的 4 次加上再一次失败就会 429。
    for index in range(settings.login_failure_limit):
        response = await _login(
            client, user.username, WRONG_PASSWORD, f"192.0.2.{100 + index}"
        )
        assert response.status_code == 401

    blocked = await _login(client, user.username, WRONG_PASSWORD, "192.0.2.200")
    assert blocked.status_code == 429
    assert blocked.json()["code"] == ERR_LOGIN_TOO_FREQUENT


async def test_client_ip_lockout_blocks_account_enumeration(client, session) -> None:
    settings = get_settings()
    limit = settings.login_failure_limit

    for index in range(limit):
        response = await _login(client, f"probe-{index}", WRONG_PASSWORD)
        assert response.status_code == 401, response.text

    # 同一客户端 IP 已经失败到阈值；即便新账号成功登录也不能继续撞库。
    response = await _login(client, "another-probe", WRONG_PASSWORD)
    assert response.status_code == 429
    assert response.json()["code"] == ERR_LOGIN_TOO_FREQUENT
