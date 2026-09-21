"""「账号 + 选填邮箱」双标识体系的回归测试。

覆盖四块：
1. 注册：账号必填、邮箱选填；填了邮箱必须验码；两个不填邮箱的账号必须能共存；
2. 登录：账号与邮箱都能登录，且**标识撞车时必须报错而不是登错人**；
3. 验证码：登录（含自动建号）/ 重置密码（支持用账号名发起）/ 限流 / 防爆破 / 场景隔离；
4. 跨列唯一：账号名与邮箱共享同一命名空间。

发信是旁路能力，测试里不去连真 SMTP：把 `notify_enabled` 打开、后端设成 `log`，
`notify()` 就会返回 True（只写日志），验证码照常写进缓存 —— 测试直接从缓存里读出来用。

注意：`get_cache()` 是模块级单例，不重置的话验证码、限流计数会跨用例串味。
所以这里加了一个 autouse fixture，每个用例前后都把单例丢掉重建。
"""
import pytest_asyncio
from sqlalchemy import select

from app.core.cache import get_cache
from app.core.config import get_settings
from app.models.user import User

PASSWORD = "pass-123456"


@pytest_asyncio.fixture(autouse=True)
async def _fresh_cache():
    """每个用例一套干净的缓存，避免验证码 / 限流计数跨用例互相污染。"""
    from app.core import cache as cache_module

    cache_module._cache = None
    yield
    cache_module._cache = None


@pytest_asyncio.fixture(autouse=True)
def _enable_log_notify(monkeypatch):
    """打开通知并把后端设成 log：不发真邮件，但 notify() 返回 True，链路可跑通。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "notify_enabled", True)
    monkeypatch.setattr(settings, "notify_backend", "log")


async def _peek_code(scene: str, email: str) -> str:
    code = await get_cache().get(f"email_code:code:{scene}:{email}")
    assert code, "验证码没有写进缓存"
    return code


async def _send(client: object, account: str, scene: str = "login"):
    """取验证码。account 在 login 场景必须是邮箱，在 reset 场景可以是账号或邮箱。"""
    return await client.post(
        "/api/auth/email-code", json={"account": account, "scene": scene}
    )


async def _register(
    client: object,
    username: str,
    email: str = "",
    password: str = PASSWORD,
):
    """注册：账号必填；给了邮箱才需要先取验证码。

    注册会消费掉验证码，且发码已占掉 60 秒重发冷却——这里顺手清掉冷却，因为后续
    用例常需要再发一次码（重发限流本身另有专门用例覆盖）。
    """
    payload: dict[str, str] = {"username": username, "password": password}
    if email:
        sent = await _send(client, email)
        assert sent.status_code == 200, sent.text
        payload["email"] = email
        payload["code"] = await _peek_code("login", email)

    result = await client.post("/api/auth/register", json=payload)
    if email:
        await get_cache().delete(f"email_code:cd:{email}")
    return result


# --------------------------------------------------------------------------- #
# 注册：账号必填、邮箱选填
# --------------------------------------------------------------------------- #
async def test_register_with_username_only(client: object, session: object) -> None:
    """不填邮箱也能注册：这是「邮箱选填」的核心诉求。"""
    r = await _register(client, "solo")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["username"] == "solo"
    # 未绑定邮箱时对外统一回空串（而不是 null），前端少一层判断
    assert body["user"]["email"] == ""

    # 库里存的是 NULL，绝不能是空串——空串会占用 uq_users_email 的唯一名额
    user = (
        await session.execute(select(User).where(User.username == "solo"))
    ).scalar_one()
    assert user.email is None

    # 账号 + 密码能登录
    login = await client.post(
        "/api/auth/login", json={"account": "solo", "password": PASSWORD}
    )
    assert login.status_code == 200, login.text


async def test_two_accounts_without_email_can_coexist(client: object) -> None:
    """两个都不绑定邮箱的账号必须都能建成功。

    这是「email 可空 + 唯一索引」最容易踩的坑：如果空值写成空串，第二个账号会
    直接撞 uq_users_email 而 IntegrityError。多个 NULL 才是唯一索引允许的形态。
    """
    first = await _register(client, "alpha")
    second = await _register(client, "beta")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text


async def test_register_with_email_binds_both_identifiers(client: object) -> None:
    """填了邮箱：账号名与邮箱是两个不同的值，且都能用来登录。"""
    email = "both@example.com"
    r = await _register(client, "bothuser", email=email)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["username"] == "bothuser"
    assert body["user"]["email"] == email

    for account in ("bothuser", email, email.upper()):
        login = await client.post(
            "/api/auth/login", json={"account": account, "password": PASSWORD}
        )
        assert login.status_code == 200, f"{account} 登录失败：{login.text}"


async def test_register_rejects_duplicate_username(client: object) -> None:
    first = await _register(client, "dupuser")
    assert first.status_code == 200, first.text

    dup = await client.post(
        "/api/auth/register", json={"username": "dupuser", "password": PASSWORD}
    )
    assert dup.status_code == 400
    assert dup.json()["code"] == 40014


async def test_register_requires_code_only_when_email_given(client: object) -> None:
    """邮箱是选填，但**填了就必须验码**：否则等于允许抢注别人的邮箱，而它同时是收件人。"""
    email = "needcode@example.com"

    # 带邮箱但一个码都不给 → 明确提示「请先获取验证码」
    missing = await client.post(
        "/api/auth/register",
        json={"username": "withcode1", "email": email, "password": PASSWORD},
    )
    assert missing.status_code == 400
    assert missing.json()["code"] == 40008

    # 给了码但不对 → 拒
    await _send(client, email)
    real = await _peek_code("login", email)
    wrong = await client.post(
        "/api/auth/register",
        json={
            "username": "withcode1",
            "email": email,
            "password": PASSWORD,
            "code": "000000",
        },
    )
    assert wrong.status_code == 400
    assert wrong.json()["code"] == 40008

    # 邮箱没被占用：真码可以正常注册
    good = await client.post(
        "/api/auth/register",
        json={
            "username": "withcode1",
            "email": email,
            "password": PASSWORD,
            "code": real,
        },
    )
    assert good.status_code == 200, good.text

    # 反证：同一批数据不填邮箱时完全不需要 code
    plain = await _register(client, "nocodeuser")
    assert plain.status_code == 200, plain.text


async def test_register_rejects_invalid_account_name(client: object) -> None:
    """账号名规则：3–30 位、字母/数字/下划线/中划线；**禁 @**、禁中文、禁空格。"""
    bad_names = [
        "ab",  # 太短
        "a" * 31,  # 太长
        "has@sign",  # 含 @（关键：禁 @ 能让两个命名空间天然不相交）
        "zhang san",  # 含空格
        "张三",  # 中文
        "bad!char",  # 非法符号
    ]
    for name in bad_names:
        r = await client.post(
            "/api/auth/register", json={"username": name, "password": PASSWORD}
        )
        assert r.status_code == 400, f"{name} 竟然通过了"
        assert r.json()["code"] == 40013, f"{name} 报的不是账号格式错误：{r.text}"

    # 合法形态（含大小写、下划线、中划线）：归一化成小写后被接受
    ok = await _register(client, "Good-Name_1")
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["username"] == "good-name_1"


async def test_register_rejects_invalid_email(client: object) -> None:
    r = await client.post(
        "/api/auth/register",
        json={"username": "bademail", "email": "not-an-email", "password": PASSWORD},
    )
    assert r.status_code == 400
    assert r.json()["code"] == 40006


# --------------------------------------------------------------------------- #
# 跨列唯一：账号名与邮箱共享同一个命名空间
# --------------------------------------------------------------------------- #
async def test_legacy_username_blocks_same_string_as_email(
    client: object, session: object
) -> None:
    """账号名与邮箱共享命名空间：注册邮箱不能撞上别人的账号名。

    账号名现在禁 `@`、邮箱必含 `@`，所以正常路径下两者天然不相交，这条校验是
    **纵深防御**。但存量数据可能不满足（例如自动建号早期把邮箱写成了账号名），
    所以直接插一条这种账号来验证校验确实生效。
    """
    session.add(
        User(username="legacy@example.com", email=None, password_hash="hashed")
    )
    await session.commit()

    # 新用户想把这个字符串注册成邮箱 → 必须拦住
    r = await client.post(
        "/api/auth/register",
        json={
            "username": "newcomer",
            "email": "legacy@example.com",
            "password": PASSWORD,
            "code": "000000",
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == 40014


async def test_binding_email_that_matches_other_account_username_is_rejected(
    client: object, session: object
) -> None:
    """用户中心绑定邮箱时同样要过跨列唯一：不能绑成别人的账号名。"""
    session.add(
        User(username="taken@example.com", email=None, password_hash="hashed")
    )
    binder = User(username="binder", email=None, password_hash="hashed")
    session.add(binder)
    await session.commit()
    await session.refresh(binder)

    from app.core.security import create_login_token

    headers = {"Authorization": f"Bearer {create_login_token(binder.id, False)}"}
    r = await client.put(
        "/api/users/me/email",
        json={"email": "taken@example.com", "code": "000000"},
        headers=headers,
    )
    # 占用检查排在验码之前，所以这里的 code 是占位、不会被消费
    assert r.status_code == 400, r.text
    assert r.json()["code"] == 40014


async def test_login_is_ambiguous_when_identifier_matches_two_rows(
    client: object, session: object
) -> None:
    """标识在库里命中两行时**必须报错**，绝不能取第一条——那等于随机会登进别人的账号。

    正常写入路径已挡住这种数据，所以这里直接插两行来构造。
    """
    session.add(User(username="clash_a", email="clash@example.com", password_hash="h"))
    session.add(User(username="clash@example.com", email=None, password_hash="h"))
    await session.commit()

    r = await client.post(
        "/api/auth/login", json={"account": "clash@example.com", "password": "h"}
    )
    assert r.status_code == 409, r.text
    assert r.json()["code"] == 40901


# --------------------------------------------------------------------------- #
# 密码登录：账号或邮箱
# --------------------------------------------------------------------------- #
async def test_login_by_bound_email_of_differently_named_account(
    client: object,
) -> None:
    """账号名与邮箱不同时，邮箱也能登录（第二个标识的实质意义）。"""
    email = "second@example.com"
    await _register(client, "primary", email=email)

    r = await client.post(
        "/api/auth/login", json={"account": email, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["username"] == "primary"


async def test_login_wrong_password_and_unknown_account(client: object) -> None:
    await _register(client, "known")

    wrong = await client.post(
        "/api/auth/login", json={"account": "known", "password": "not-the-password"}
    )
    assert wrong.status_code == 401
    assert wrong.json()["code"] == 40101

    unknown = await client.post(
        "/api/auth/login", json={"account": "nobody", "password": PASSWORD}
    )
    assert unknown.status_code == 401
    # 提示不区分「账号不存在」与「密码错误」，避免免费告诉探测者账号是否存在
    assert unknown.json()["code"] == 40101
    assert unknown.json()["message"] == wrong.json()["message"]


# --------------------------------------------------------------------------- #
# 验证码登录：不存在的邮箱会自动建号
# --------------------------------------------------------------------------- #
async def test_code_login_creates_passwordless_account(
    client: object, session: object
) -> None:
    email = "newbie@example.com"
    assert (await _send(client, email)).status_code == 200
    code = await _peek_code("login", email)

    r = await client.post(
        "/api/auth/login-by-code", json={"email": email, "code": code}
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == email
    # 自动建号时账号名取邮箱本地部分（不含 @），与「账号名禁 @」规则一致
    assert r.json()["user"]["username"] == email.split("@")[0]
    assert "@" not in r.json()["user"]["username"]

    user = (
        await session.execute(
            select(User).where(User.username == email.split("@")[0])
        )
    ).scalar_one()
    assert user.email == email
    assert user.password_hash is None
    assert user.password_length is None
    assert user.is_admin is False


async def test_code_login_derives_local_part_with_suffix_on_conflict(
    client: object, session: object
) -> None:
    """本地部分与已有账号名撞车：自动建号应加数字后缀，而不是崩或越权。"""
    # 先占住账号名 `foo`（纯账号、不带邮箱）
    await _register(client, "foo")
    email = "foo@other.example.com"
    assert (await _send(client, email)).status_code == 200
    code = await _peek_code("login", email)

    r = await client.post(
        "/api/auth/login-by-code", json={"email": email, "code": code}
    )
    assert r.status_code == 200, r.text
    username = r.json()["user"]["username"]
    # 本地部分 `foo` 已被占用 → 追加后缀；绝不取第一条、绝不报 500
    assert username == "foo2", username
    assert "@" not in username

    created = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one()
    assert created.email == email


async def test_code_login_sanitizes_illegal_chars_in_local_part(
    client: object, session: object
) -> None:
    """邮箱本地部分含非法字符（`.` `+`）：自动建号应清洗成合法账号名。"""
    email = "first.last+spam@x.com"
    assert (await _send(client, email)).status_code == 200
    code = await _peek_code("login", email)

    r = await client.post(
        "/api/auth/login-by-code", json={"email": email, "code": code}
    )
    assert r.status_code == 200, r.text
    username = r.json()["user"]["username"]
    # `.` 和 `+` 被删除，只留 `a-z0-9_-`
    assert username == "firstlastspam", username
    assert "@" not in username


async def test_code_login_finds_account_by_bound_email(
    client: object, session: object
) -> None:
    """已绑定该邮箱的账号，验证码登录应命中原账号，**不能另建一个号**。"""
    email = "bound@example.com"
    await _register(client, "bounduser", email=email)
    assert (await _send(client, email)).status_code == 200
    code = await _peek_code("login", email)

    r = await client.post(
        "/api/auth/login-by-code", json={"email": email, "code": code}
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["username"] == "bounduser"

    # 库里仍然只有一个账号（没有分裂出 username == email 的第二行）
    count = len(
        (
            await session.execute(
                select(User).where((User.username == email) | (User.email == email))
            )
        ).scalars().all()
    )
    assert count == 1


async def test_code_login_rejects_wrong_code(client: object) -> None:
    email = "wrongcode@example.com"
    assert (await _send(client, email)).status_code == 200

    r = await client.post(
        "/api/auth/login-by-code", json={"email": email, "code": "000000"}
    )
    assert r.status_code == 400
    assert r.json()["code"] == 40008


async def test_code_is_consumed_after_success(client: object) -> None:
    email = "once@example.com"
    assert (await _send(client, email)).status_code == 200
    code = await _peek_code("login", email)

    first = await client.post(
        "/api/auth/login-by-code", json={"email": email, "code": code}
    )
    assert first.status_code == 200, first.text

    # 一次性：同一枚验证码不能用第二次
    second = await client.post(
        "/api/auth/login-by-code", json={"email": email, "code": code}
    )
    assert second.status_code == 400
    assert second.json()["code"] == 40008


async def test_code_scene_isolation(client: object) -> None:
    """重置密码拿到的验证码，不能拿去登录。"""
    email = "scene@example.com"
    await _register(client, "sceneuser", email=email)
    assert (await _send(client, email, scene="reset")).status_code == 200
    reset_code = await _peek_code("reset", email)

    r = await client.post(
        "/api/auth/login-by-code", json={"email": email, "code": reset_code}
    )
    assert r.status_code == 400
    assert r.json()["code"] == 40008


async def test_brute_force_invalidates_code(client: object) -> None:
    """连续猜错达到上限后，即使拿到正确验证码也失效，必须重新获取。"""
    email = "brute@example.com"
    assert (await _send(client, email)).status_code == 200
    good = await _peek_code("login", email)

    for _ in range(5):
        await client.post(
            "/api/auth/login-by-code", json={"email": email, "code": "999999"}
        )

    r = await client.post(
        "/api/auth/login-by-code", json={"email": email, "code": good}
    )
    assert r.status_code == 400
    assert r.json()["code"] == 40008


async def test_code_login_rejected_for_disabled_account(
    client: object, session: object
) -> None:
    email = "disabled@example.com"
    session.add(User(username="disableduser", email=email, is_active=False))
    await session.commit()

    assert (await _send(client, email)).status_code == 200
    code = await _peek_code("login", email)

    r = await client.post(
        "/api/auth/login-by-code", json={"email": email, "code": code}
    )
    assert r.status_code == 401
    assert r.json()["code"] == 40104


# --------------------------------------------------------------------------- #
# 发送限流
# --------------------------------------------------------------------------- #
async def test_send_code_is_rate_limited(client: object) -> None:
    email = "flood@example.com"
    assert (await _send(client, email)).status_code == 200

    again = await _send(client, email)
    assert again.status_code == 429
    assert again.json()["code"] == 40009


async def test_send_reset_code_requires_existing_account(client: object) -> None:
    r = await _send(client, "nobody@example.com", scene="reset")
    assert r.status_code == 404


async def test_send_login_code_rejects_non_email(client: object) -> None:
    """登录/绑定场景必须给邮箱：验证码就是发到这个信箱来证明归属的。"""
    r = await _send(client, "not-an-email")
    assert r.status_code == 400
    assert r.json()["code"] == 40006


# --------------------------------------------------------------------------- #
# 重置密码
# --------------------------------------------------------------------------- #
async def test_reset_password_flow_with_email(client: object) -> None:
    email = "resetme@example.com"
    await _register(client, "resetuser", email=email)
    assert (await _send(client, email, scene="reset")).status_code == 200
    code = await _peek_code("reset", email)

    new_password = "brand-new-789"
    r = await client.post(
        "/api/auth/reset-password",
        json={"account": email, "code": code, "newPassword": new_password},
    )
    assert r.status_code == 200, r.text

    # 旧密码失效，新密码可用
    assert (
        await client.post(
            "/api/auth/login", json={"account": "resetuser", "password": PASSWORD}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/auth/login",
            json={"account": "resetuser", "password": new_password},
        )
    ).status_code == 200


async def test_reset_password_can_be_started_with_username(client: object) -> None:
    """用账号名也能发起重置：后端定位账号后，往它绑定的邮箱发码。"""
    email = "byuser@example.com"
    await _register(client, "byusername", email=email)

    sent = await _send(client, "byusername", scene="reset")
    assert sent.status_code == 200, sent.text
    # 码写在**该账号绑定的邮箱**名下，而不是用户输入的那个账号名
    code = await _peek_code("reset", email)

    r = await client.post(
        "/api/auth/reset-password",
        json={"account": "byusername", "code": code, "newPassword": "another-123"},
    )
    assert r.status_code == 200, r.text


async def test_reset_password_requires_bound_email(
    client: object, session: object
) -> None:
    """没绑邮箱 = 没有自助重置通道，必须明确告知，而不是让用户干等一封不来的信。"""
    session.add(User(username="noemail", password_hash="hashed"))
    await session.commit()

    sent = await _send(client, "noemail", scene="reset")
    assert sent.status_code == 400, sent.text
    assert sent.json()["code"] == 40015


# --------------------------------------------------------------------------- #
# 令牌续期（企业 SaaS 式「即将过期 → 保持登录」）
# --------------------------------------------------------------------------- #
async def test_refresh_token_issues_new_valid_token(client: object) -> None:
    """续期：用仍有效的令牌换发新令牌，新令牌能正常访问 /me。"""
    reg = await _register(client, "renewuser")
    assert reg.status_code == 200, reg.text
    token = reg.json()["token"]

    r = await client.post(
        "/api/auth/refresh",
        json={"remember": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    new_token = r.json()["token"]
    assert new_token  # 注意：JWT 无随机因子，同秒同参可能签出完全相同的串，别断言「必不同」

    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}
    )
    assert me.status_code == 200
    assert me.json()["username"] == "renewuser"


async def test_refresh_rejects_expired_token(client: object) -> None:
    """真正过期的令牌不能续期：必须回去重新登录（前端据此走「到点强退」）。"""
    from app.core.security import create_access_token

    reg = await _register(client, "expireduser")
    assert reg.status_code == 200, reg.text
    uid = reg.json()["user"]["id"]

    expired = create_access_token(uid, -1)  # expires_minutes=-1 → exp 落在过去
    r = await client.post(
        "/api/auth/refresh",
        json={"remember": False},
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == 40102
