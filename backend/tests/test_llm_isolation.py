"""AI 配置按用户隔离的集成测试。

覆盖两类越权：
1) 别人的供应商：列表看不到、读不到明文 Key / 模型列表、改 / 删 / 激活一律 404；
2) 别人的账号资料：/api/users 只返回本人，查别人按不存在处理。

以及「配置互不串台」：A 开启真实模型不影响 B（B 仍读自己的 .env 兜底）。
"""
from app.core.security import create_access_token
from app.models.user import User


async def _make_user(session: object, username: str) -> User:
    u = User(username=username, password_hash="hashed")
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _create_provider(client: object, user: User, name: str = "我的供应商") -> int:
    r = await client.post(
        "/api/settings/llm/providers",
        headers=_auth(user),
        json={
            "name": name,
            "baseUrl": "https://api.example.com/v1",
            "model": "some-model",
            "apiKey": f"sk-{user.username}-secret",
            "models": ["some-model", "another-model"],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def test_provider_list_is_per_user(client: object, session: object) -> None:
    alice = await _make_user(session, "alice")
    bob = await _make_user(session, "bob")

    await _create_provider(client, alice, "Alice 的供应商")
    await _create_provider(client, bob, "Bob 的供应商")

    alice_list = (await client.get("/api/settings/llm/providers", headers=_auth(alice))).json()
    bob_list = (await client.get("/api/settings/llm/providers", headers=_auth(bob))).json()

    assert [p["name"] for p in alice_list] == ["Alice 的供应商"]
    assert [p["name"] for p in bob_list] == ["Bob 的供应商"]


async def test_cannot_read_other_users_provider_secrets(
    client: object, session: object
) -> None:
    alice = await _make_user(session, "alice")
    bob = await _make_user(session, "bob")
    pid = await _create_provider(client, alice)

    # 明文 Key、模型列表：都当作「不存在」，不泄露任何信息
    assert (
        await client.get(f"/api/settings/llm/providers/{pid}/api-key", headers=_auth(bob))
    ).status_code == 404
    assert (
        await client.get(f"/api/settings/llm/providers/{pid}/models", headers=_auth(bob))
    ).status_code == 404

    # 归属用户自己可以读到
    assert (
        await client.get(f"/api/settings/llm/providers/{pid}/api-key", headers=_auth(alice))
    ).json()["apiKey"] == "sk-alice-secret"


async def test_cannot_modify_other_users_provider(client: object, session: object) -> None:
    alice = await _make_user(session, "alice")
    bob = await _make_user(session, "bob")
    pid = await _create_provider(client, alice)

    assert (
        await client.put(
            f"/api/settings/llm/providers/{pid}",
            headers=_auth(bob),
            json={"name": "被改名了"},
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/settings/llm/providers/{pid}/activate", headers=_auth(bob)
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/settings/llm/providers/{pid}/duplicate", headers=_auth(bob)
        )
    ).status_code == 404
    assert (
        await client.delete(
            f"/api/settings/llm/providers/{pid}", headers=_auth(bob)
        )
    ).status_code == 404
    # 排序里混入别人的 id 也要被挡住
    assert (
        await client.post(
            "/api/settings/llm/providers/reorder",
            headers=_auth(bob),
            json={"ids": [pid]},
        )
    ).status_code == 404

    # 确认没有被改动
    names = [
        p["name"]
        for p in (await client.get("/api/settings/llm/providers", headers=_auth(alice))).json()
    ]
    assert names == ["我的供应商"]


async def test_settings_and_status_are_per_user(client: object, session: object) -> None:
    alice = await _make_user(session, "alice")
    bob = await _make_user(session, "bob")
    await _create_provider(client, alice)

    # Alice 开启 AI（她有自己的供应商）
    r = await client.put(
        "/api/settings/llm", headers=_auth(alice), json={"enabled": True}
    )
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "database"
    assert r.json()["mode"] == "real"

    # Bob 什么都没配：读的是 .env 兜底，且没有 Alice 的供应商
    bob_setting = (await client.get("/api/settings/llm", headers=_auth(bob))).json()
    assert bob_setting["source"] == "env"
    assert bob_setting["hasApiKey"] is False
    assert (await client.get("/api/settings/llm/providers", headers=_auth(bob))).json() == []
    assert (await client.get("/api/llm/status", headers=_auth(bob))).json()["mode"] == "mock"


async def test_users_endpoints_are_self_only(client: object, session: object) -> None:
    alice = await _make_user(session, "alice")
    bob = await _make_user(session, "bob")

    listing = (await client.get("/api/users", headers=_auth(alice))).json()
    assert [u["username"] for u in listing] == ["alice"]

    assert (
        await client.get(f"/api/users/{bob.id}", headers=_auth(alice))
    ).status_code == 404
    assert (
        await client.get(f"/api/users/{alice.id}", headers=_auth(alice))
    ).json()["username"] == "alice"

    # 未登录不再能拿到任何账号信息
    assert (await client.get("/api/users")).status_code == 401
