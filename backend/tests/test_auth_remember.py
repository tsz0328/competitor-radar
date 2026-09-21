"""登录「记住我」：勾选签长期令牌，不勾签会话令牌。

前端按勾选把 token 存 localStorage（关浏览器仍登录）或 sessionStorage（关即失效），
后端令牌时长必须跟着变，否则这个勾选框等于没有作用。
"""
from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.security import decode_access_token, hash_password
from app.models.user import User

settings = get_settings()
PASSWORD = "pass-123456"


async def _make_user(session: object, username: str = "alice") -> User:
    # 账号名与邮箱已解绑：这里给一个自定义账号名 + 一个绑定邮箱
    u = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password(PASSWORD),
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _expire_seconds(token: str) -> int:
    """从令牌里读出「有效期还剩多久」（exp - iat），单位秒。"""
    payload = decode_access_token(token)
    assert payload is not None
    return int(payload["exp"] - payload["iat"])


async def test_remember_controls_token_lifetime(client: object, session: object) -> None:
    await _make_user(session)

    # 不传 remember（老前端/注册页）：按会话令牌处理
    plain = await client.post(
        "/api/auth/login", json={"account": "alice", "password": PASSWORD}
    )
    remembered = await client.post(
        "/api/auth/login",
        json={"account": "alice@example.com", "password": PASSWORD, "remember": True},
    )

    assert plain.status_code == 200, plain.text
    assert remembered.status_code == 200, remembered.text

    assert (
        _expire_seconds(plain.json()["token"])
        == settings.session_token_expire_minutes * 60
    )
    assert (
        _expire_seconds(remembered.json()["token"])
        == settings.remember_token_expire_minutes * 60
    )
    # 长期令牌必须明显更长，否则「记住我」失去了意义
    assert (
        settings.remember_token_expire_minutes
        > settings.session_token_expire_minutes
    )


async def test_register_token_is_session_scoped(client: object, monkeypatch) -> None:
    """注册页没有「记住我」勾选框 → 默认不记住，只发会话令牌。

    这里刻意带上邮箱（邮箱同时是通知收件人，填了就必须验码），顺便覆盖注册的
    「验码 → 建号 → 签发会话令牌」整条链路；通知后端临时设成 log，不发真邮件
    但 notify() 返回 True。
    """
    monkeypatch.setattr(settings, "notify_enabled", True)
    monkeypatch.setattr(settings, "notify_backend", "log")

    email = "bob@example.com"
    sent = await client.post(
        "/api/auth/email-code", json={"account": email, "scene": "login"}
    )
    assert sent.status_code == 200, sent.text
    code = await get_cache().get(f"email_code:code:login:{email}")
    assert code, "验证码没有写进缓存"

    r = await client.post(
        "/api/auth/register",
        json={"username": "bob", "email": email, "password": PASSWORD, "code": code},
    )
    assert r.status_code == 200, r.text
    assert (
        _expire_seconds(r.json()["token"])
        == settings.session_token_expire_minutes * 60
    )
