"""用户中心（账号资料 / 邮箱绑定 / 改密 / 无密码账号）的集成测试。

体系已改为「账号 + 选填邮箱」双标识，本文件对应四块：
1. `/api/users/me` 可改**账号名**与昵称/头像，但**不含邮箱**——换绑必须验码，走
   `PUT /api/users/me/email`；这里两边都断言，防止有人把邮箱又塞回普通资料更新里。
2. 改账号名要过格式（禁 @）与「跨列唯一」（不能撞别人绑定的邮箱）。
3. **没有密码的账号**（邮箱验证码登录自动创建）可以直接设置密码，无需原密码。
4. 解绑邮箱前必须已有密码，否则账号会彻底登不进来。

重点之一（保持原样）：**原密码错误必须是 400xx，不能是 401xx**。
前端 request.ts 把任何 401xx 都当成"登录失效"→ 清 token 跳登录页，
所以改密失败若返回 401xx，用户会被直接踢出去。
"""
import pytest_asyncio

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.user import User

PASSWORD = "old-pass-123"
USERNAME = "alice"
EMAIL = "alice@example.com"


@pytest_asyncio.fixture(autouse=True)
async def _fresh_cache():
    """绑定邮箱要发验证码，缓存单例必须每例重建（与 test_email_auth 同处置）。"""
    from app.core import cache as cache_module

    cache_module._cache = None
    yield
    cache_module._cache = None


@pytest_asyncio.fixture(autouse=True)
def _enable_log_notify(monkeypatch):
    """发信走 log 后端：不连真 SMTP，但 notify() 返回 True，验证码照常入缓存。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "notify_enabled", True)
    monkeypatch.setattr(settings, "notify_backend", "log")


async def _make_user(
    session: object,
    username: str = USERNAME,
    email: str | None = EMAIL,
    password: str | None = PASSWORD,
) -> User:
    """password=None 表示「该账号还没设置密码」（验证码登录自动建号的形态）；
    email=None 表示「还没绑定邮箱」。"""
    u = User(
        username=username,
        email=email,
        password_hash=hash_password(password) if password else None,
        password_length=len(password) if password else None,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def test_profile_defaults_and_update(client: object, session: object) -> None:
    user = await _make_user(session)

    initial = (await client.get("/api/users/me", headers=_auth(user))).json()
    assert initial == {
        "id": user.id,
        "username": USERNAME,
        "nickname": "",
        "email": EMAIL,
        "avatar": "",
        "passwordLength": len(PASSWORD),
        "isAdmin": False,
    }

    avatar = "data:image/jpeg;base64,AAAA"
    saved = await client.put(
        "/api/users/me",
        headers=_auth(user),
        json={"nickname": "Alice", "avatar": avatar},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["nickname"] == "Alice"
    assert saved.json()["avatar"] == avatar
    # 没传邮箱 → 绑定关系保持不变
    assert saved.json()["email"] == EMAIL

    # 重新登录：返回值里带上昵称（name）、头像与邮箱，前端据此渲染侧边栏
    login = await client.post(
        "/api/auth/login", json={"account": USERNAME, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["name"] == "Alice"
    assert login.json()["user"]["avatar"] == avatar
    assert login.json()["user"]["email"] == EMAIL

    # 只传部分字段：其余保持不变
    partial = await client.put(
        "/api/users/me", headers=_auth(user), json={"avatar": ""}
    )
    assert partial.json()["avatar"] == ""
    assert partial.json()["username"] == USERNAME
    assert partial.json()["nickname"] == "Alice"

    # 单独清空昵称：空串表示未设置
    cleared = await client.put(
        "/api/users/me", headers=_auth(user), json={"nickname": ""}
    )
    assert cleared.json()["nickname"] == ""


async def test_username_can_be_changed_but_email_cannot(
    client: object, session: object
) -> None:
    """账号名可以改（它只是个登录把手）；邮箱**传了也不生效**，必须走绑定接口。"""
    user = await _make_user(session)

    r = await client.put(
        "/api/users/me",
        headers=_auth(user),
        json={"username": "alice-new", "email": "hacker@evil.com"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "alice-new"
    # email 字段被忽略：换绑必须先验证新邮箱归属
    assert r.json()["email"] == EMAIL

    await session.refresh(user)
    assert user.username == "alice-new"
    assert user.email == EMAIL

    # 改完账号名，原来的邮箱照样能登录，新账号名也能
    for account in ("alice-new", EMAIL):
        assert (
            await client.post(
                "/api/auth/login", json={"account": account, "password": PASSWORD}
            )
        ).status_code == 200, account


async def test_username_change_enforces_format_and_uniqueness(
    client: object, session: object
) -> None:
    user = await _make_user(session)
    await _make_user(session, username="taken", email=None)

    # 格式：含 @ 的账号名一律拒（账号名与邮箱是两个不相交的命名空间）
    bad_format = await client.put(
        "/api/users/me", headers=_auth(user), json={"username": "alice@example.com"}
    )
    assert bad_format.status_code == 400
    assert bad_format.json()["code"] == 40013

    # 唯一：撞上别人的账号名
    duplicated = await client.put(
        "/api/users/me", headers=_auth(user), json={"username": "taken"}
    )
    assert duplicated.status_code == 400
    assert duplicated.json()["code"] == 40014

    # 保持原值不变：不能因为「跟自己重名」被判冲突
    unchanged = await client.put(
        "/api/users/me", headers=_auth(user), json={"username": USERNAME}
    )
    assert unchanged.status_code == 200, unchanged.text


async def test_bind_email_flow(client: object, session: object) -> None:
    """注册时没填邮箱的用户，可以在用户中心补绑，从而拿回邮箱登录与找回密码。"""
    user = await _make_user(session, username="binder", email=None)
    email = "newbind@example.com"

    sent = await client.post(
        "/api/auth/email-code", json={"account": email, "scene": "login"}
    )
    assert sent.status_code == 200, sent.text
    code = await get_cache().get(f"email_code:code:login:{email}")
    assert code, "验证码没有写进缓存"

    bound = await client.put(
        "/api/users/me/email",
        headers=_auth(user),
        json={"email": email, "code": code},
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["email"] == email

    await session.refresh(user)
    assert user.email == email

    # 绑定后这个邮箱就能登录了
    assert (
        await client.post(
            "/api/auth/login", json={"account": email, "password": PASSWORD}
        )
    ).status_code == 200

    # 解绑：当前已登录，不需要验证码
    unbound = await client.put(
        "/api/users/me/email", headers=_auth(user), json={"email": ""}
    )
    assert unbound.status_code == 200, unbound.text
    assert unbound.json()["email"] == ""

    await session.refresh(user)
    assert user.email is None

    # 解绑后原邮箱不能再登录（它已不属于任何账号）
    assert (
        await client.post(
            "/api/auth/login", json={"account": email, "password": PASSWORD}
        )
    ).status_code == 401


async def test_bind_email_requires_code(client: object, session: object) -> None:
    """不验码就能绑邮箱 = 谁都能把别人的邮箱绑成自己的登录标识，必须拦住。"""
    user = await _make_user(session, username="binder2", email=None)
    email = "needcode@example.com"

    missing = await client.put(
        "/api/users/me/email", headers=_auth(user), json={"email": email}
    )
    assert missing.status_code == 400
    assert missing.json()["code"] == 40008

    await client.post(
        "/api/auth/email-code", json={"account": email, "scene": "login"}
    )
    wrong = await client.put(
        "/api/users/me/email",
        headers=_auth(user),
        json={"email": email, "code": "000000"},
    )
    assert wrong.status_code == 400
    assert wrong.json()["code"] == 40008

    # 邮箱始终没被绑上
    await session.refresh(user)
    assert user.email is None


async def test_unbind_email_rejected_when_no_password(
    client: object, session: object
) -> None:
    """没密码又解绑邮箱 = 这个账号再也登不进来，必须拦住。"""
    user = await _make_user(session, username="nopwd", email=None, password=None)
    user.email = "keepme@example.com"
    await session.commit()

    r = await client.put(
        "/api/users/me/email", headers=_auth(user), json={"email": ""}
    )
    assert r.status_code == 400, r.text

    await session.refresh(user)
    assert user.email == "keepme@example.com"


async def test_change_password(client: object, session: object) -> None:
    user = await _make_user(session)

    # 原密码错误：必须是 400xx（不能被前端当成登录失效）
    wrong = await client.put(
        "/api/users/me/password",
        headers=_auth(user),
        json={"oldPassword": "wrong-pass", "newPassword": "new-pass-123"},
    )
    assert wrong.status_code == 400
    assert wrong.json()["code"] == 40005

    # 新密码太短：参数校验失败
    too_short = await client.put(
        "/api/users/me/password",
        headers=_auth(user),
        json={"oldPassword": PASSWORD, "newPassword": "123"},
    )
    assert too_short.status_code == 422

    ok = await client.put(
        "/api/users/me/password",
        headers=_auth(user),
        json={"oldPassword": PASSWORD, "newPassword": "new-pass-123"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["ok"] is True

    # 改密成功后，资料里带上新密码的位数（用于账号页以 * 占位展示）
    after = (await client.get("/api/users/me", headers=_auth(user))).json()
    assert after["passwordLength"] == len("new-pass-123")

    # 旧密码不再能登录，新密码可以
    assert (
        await client.post(
            "/api/auth/login", json={"account": USERNAME, "password": PASSWORD}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/auth/login", json={"account": USERNAME, "password": "new-pass-123"}
        )
    ).status_code == 200


async def test_passwordless_account_can_set_password_without_old_one(
    client: object, session: object
) -> None:
    """验证码登录自动创建的账号没有密码：允许直接设置，不必填原密码。"""
    user = await _make_user(session, password=None)

    r = await client.put(
        "/api/users/me/password",
        headers=_auth(user),
        json={"newPassword": "brand-new-123"},
    )
    assert r.status_code == 200, r.text

    assert (
        await client.post(
            "/api/auth/login", json={"account": USERNAME, "password": "brand-new-123"}
        )
    ).status_code == 200


async def test_password_login_rejected_for_passwordless_account(
    client: object, session: object
) -> None:
    """没有密码的账号走密码登录，必须明确提示改用验证码登录（40010），而不是含糊的 40101。"""
    await _make_user(session, password=None)

    r = await client.post(
        "/api/auth/login", json={"account": USERNAME, "password": "whatever-123"}
    )
    assert r.status_code == 400
    assert r.json()["code"] == 40010
    assert "验证码" in r.json()["message"]
