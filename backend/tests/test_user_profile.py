"""用户中心（账号资料 / 头像 / 通知邮箱 / 修改密码）的集成测试。

重点之一：**原密码错误必须是 400xx，不能是 401xx**。
前端 request.ts 把任何 401xx 都当成"登录失效"→ 清 token 跳登录页，
所以改密失败若返回 401xx，用户会被直接踢出去。
"""
from app.core.security import create_access_token, hash_password
from app.models.user import User

PASSWORD = "old-pass-123"


async def _make_user(session: object, username: str, password: str = PASSWORD) -> User:
    u = User(username=username, password_hash=hash_password(password))
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def test_profile_defaults_and_update(client: object, session: object) -> None:
    user = await _make_user(session, "alice")

    initial = (await client.get("/api/users/me", headers=_auth(user))).json()
    assert initial == {
        "id": user.id,
        "username": "alice",
        "nickname": "",
        "email": "",
        "avatar": "",
        "passwordLength": None,
        "isAdmin": False,
    }

    avatar = "data:image/jpeg;base64,AAAA"
    saved = await client.put(
        "/api/users/me",
        headers=_auth(user),
        json={
            "username": "alice-new",
            "nickname": "Alice",
            "email": "a@example.com",
            "avatar": avatar,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["username"] == "alice-new"
    assert saved.json()["nickname"] == "Alice"
    assert saved.json()["email"] == "a@example.com"
    assert saved.json()["avatar"] == avatar

    # 重新登录：返回值里带上昵称（name）、头像与邮箱，前端据此渲染侧边栏
    login = await client.post(
        "/api/auth/login", json={"account": "alice-new", "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["name"] == "Alice"
    assert login.json()["user"]["avatar"] == avatar
    assert login.json()["user"]["email"] == "a@example.com"

    # 只传部分字段：其余保持不变
    partial = await client.put(
        "/api/users/me", headers=_auth(user), json={"avatar": ""}
    )
    assert partial.json()["avatar"] == ""
    assert partial.json()["username"] == "alice-new"
    assert partial.json()["nickname"] == "Alice"

    # 单独清空昵称：空串表示未设置
    cleared = await client.put(
        "/api/users/me", headers=_auth(user), json={"nickname": ""}
    )
    assert cleared.json()["nickname"] == ""


async def test_username_must_be_unique(client: object, session: object) -> None:
    alice = await _make_user(session, "alice")
    await _make_user(session, "bob")

    r = await client.put(
        "/api/users/me", headers=_auth(alice), json={"username": "bob"}
    )
    assert r.status_code == 400
    assert r.json()["code"] == 40001

    # 改成自己原来的名字应该没问题
    ok = await client.put(
        "/api/users/me", headers=_auth(alice), json={"username": "alice"}
    )
    assert ok.status_code == 200


async def test_email_format_validated(client: object, session: object) -> None:
    alice = await _make_user(session, "alice")

    bad = await client.put(
        "/api/users/me", headers=_auth(alice), json={"email": "not-an-email"}
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == 40006

    # 留空是允许的（= 不单独接收通知）
    ok = await client.put("/api/users/me", headers=_auth(alice), json={"email": ""})
    assert ok.status_code == 200
    assert ok.json()["email"] == ""


async def test_change_password(client: object, session: object) -> None:
    user = await _make_user(session, "alice")

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
            "/api/auth/login", json={"account": "alice", "password": PASSWORD}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/auth/login", json={"account": "alice", "password": "new-pass-123"}
        )
    ).status_code == 200
