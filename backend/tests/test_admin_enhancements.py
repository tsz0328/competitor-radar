"""管理端增强特性测试：审计日志、分页、用户时间字段、测试发信、
授权码加密、总览缓存、用户详情、CSV 导出、平台公告。
"""
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.exceptions import ERR_EMAIL_INVALID, ERR_FORBIDDEN
from app.core.security import create_access_token, hash_password
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services import admin_stats, notifier, system_settings

from test_admin import (
    _seed_competitor,
    _seed_crawl_log,
    _seed_event,
    _seed_report,
    _seed_user,
)


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest_asyncio.fixture(autouse=True)
async def _patch_settings_session(session, monkeypatch) -> None:
    """把 system_settings 内部独立的 SessionLocal 指到测试会话。

    get_effective_smtp_config 默认开自己的 SessionLocal（连真实 dev.db，
    且 .env 里配了真实 SMTP），不隔离会读错库甚至把测试邮件发给真实服务器。
    本 fixture 对模块内所有测试生效：读取/懒回写都落在测试内存库上。
    """

    class _FakeSmtpDb:
        def __init__(self, s):
            self._s = s

        async def __aenter__(self):
            return self._s

        async def __aexit__(self, *exc_info):
            return False  # 会话由外层 session fixture 统一管理，不在这里关闭

    monkeypatch.setattr(system_settings, "SessionLocal", lambda: _FakeSmtpDb(session))


# ==================== 审计日志 ====================


async def test_update_user_writes_audit(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")

    resp = await client.put(
        f"/api/admin/users/{alice.id}",
        headers=_auth(admin),
        json={"is_active": False, "new_password": "secret123"},
    )
    assert resp.status_code == 200

    logs = await client.get("/api/admin/audit-logs", headers=_auth(admin))
    body = logs.json()
    assert body["total"] == 1
    entry = body["items"][0]
    assert entry["admin_username"] == "boss"
    assert entry["action"] == "update_user"
    assert entry["target_type"] == "user"
    assert entry["target_id"] == alice.id
    assert "停用" in entry["detail"]
    assert "重置密码" in entry["detail"]


async def test_delete_user_writes_audit(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    bob = await _seed_user(session, "bob")

    resp = await client.delete(f"/api/admin/users/{bob.id}", headers=_auth(admin))
    assert resp.status_code == 200

    logs = await client.get("/api/admin/audit-logs", headers=_auth(admin))
    assert logs.json()["total"] == 1
    assert "删除用户 bob" in logs.json()["items"][0]["detail"]


async def test_system_settings_writes_audit_without_password(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)

    resp = await client.put(
        "/api/admin/system-settings",
        headers=_auth(admin),
        json={"smtp_host": "smtp.example.com", "smtp_password": "supersecret"},
    )
    assert resp.status_code == 200

    logs = await client.get("/api/admin/audit-logs", headers=_auth(admin))
    item = logs.json()["items"][0]
    assert item["action"] == "update_system_settings"
    assert "smtp_password=***" in item["detail"]
    assert "supersecret" not in item["detail"]  # 授权码不进审计明细


async def test_audit_logs_filter_and_admin_only(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")
    carol = await _seed_user(session, "carol")
    await client.put(
        f"/api/admin/users/{alice.id}", headers=_auth(admin), json={"is_active": False}
    )

    # 普通用户 403（用未被停用的 carol，否则先命中 401 鉴权拦截）
    resp = await client.get("/api/admin/audit-logs", headers=_auth(carol))
    assert resp.status_code == 403
    assert resp.json()["code"] == ERR_FORBIDDEN

    # action 过滤：不匹配时为空
    resp = await client.get(
        "/api/admin/audit-logs", headers=_auth(admin), params={"action": "delete_user"}
    )
    assert resp.json()["total"] == 0

    # keyword 过滤命中 detail
    resp = await client.get(
        "/api/admin/audit-logs", headers=_auth(admin), params={"keyword": "停用"}
    )
    assert resp.json()["total"] == 1


# ==================== 分页 ====================


async def test_users_pagination(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    for i in range(5):
        await _seed_user(session, f"user{i}")

    resp = await client.get(
        "/api/admin/users", headers=_auth(admin), params={"page": 2, "page_size": 2}
    )
    body = resp.json()
    assert body["total"] == 6  # boss + 5
    assert len(body["items"]) == 2
    assert [r["username"] for r in body["items"]] == ["user1", "user2"]  # 按 id 升序

    # page_size 上限 100：请求 1000 也只按 100 处理（不报错、返回全量）
    resp = await client.get(
        "/api/admin/users", headers=_auth(admin), params={"page_size": 1000}
    )
    assert resp.json()["total"] == 6


async def test_competitors_pagination(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")
    for i in range(3):
        await _seed_competitor(session, alice.id, f"comp{i}")

    resp = await client.get(
        "/api/admin/competitors", headers=_auth(admin), params={"page": 1, "page_size": 2}
    )
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


# ==================== 用户时间字段 ====================


async def test_users_include_timestamps_and_login_updates(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")
    alice.password_hash = hash_password("secret123")
    alice.password_length = 9
    await session.commit()

    rows = (
        await client.get("/api/admin/users", headers=_auth(admin))
    ).json()["items"]
    by_name = {r["username"]: r for r in rows}
    # 种子用户的 created_at 由 server_default 写入，非空
    assert by_name["alice"]["created_at"]
    assert by_name["alice"]["last_login_at"] == ""  # 从未登录

    login = await client.post(
        "/api/auth/login", json={"account": "alice", "password": "secret123"}
    )
    assert login.status_code == 200

    by_name = {
        r["username"]: r
        for r in (await client.get("/api/admin/users", headers=_auth(admin))).json()["items"]
    }
    assert by_name["alice"]["last_login_at"]  # 登录后非空


# ==================== SMTP 测试发信 ====================


async def test_test_email_invalid_recipient(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    resp = await client.post(
        "/api/admin/system-settings/test-email",
        headers=_auth(admin),
        json={"to": "not-an-email"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == ERR_EMAIL_INVALID


async def test_test_email_missing_config_returns_failure(client, session, monkeypatch) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)

    # 测试库没有 SMTP 覆盖，且把 .env 兜底也清空：确保走「配置缺失」分支，
    # 而不是拿真实 .env 里的 smtp.qq.com 当真去发信
    class _EmptySettings:
        smtp_host = ""
        smtp_port = 0
        smtp_username = ""
        smtp_password = ""
        smtp_sender = ""
        smtp_secret = ""
        jwt_secret = ""

    monkeypatch.setattr(system_settings, "get_settings", lambda: _EmptySettings())
    resp = await client.post(
        "/api/admin/system-settings/test-email",
        headers=_auth(admin),
        json={"to": "someone@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert "SMTP" in resp.json()["message"]


async def test_test_email_success(client, session, monkeypatch) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    await client.put(
        "/api/admin/system-settings",
        headers=_auth(admin),
        json={
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "smtp_username": "sender@example.com",
            "smtp_password": "secret",
            "smtp_sender": "sender@example.com",
        },
    )

    sent: list = []

    def fake_send_smtp(title, message, recipients, sender, host, port, username, password):
        sent.append(
            {
                "title": title,
                "recipients": recipients,
                "password": password,
                "host": host,
            }
        )

    monkeypatch.setattr(notifier, "_send_smtp", fake_send_smtp)
    resp = await client.post(
        "/api/admin/system-settings/test-email",
        headers=_auth(admin),
        json={"to": "someone@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert sent[0]["recipients"] == ["someone@example.com"]
    # 发信用的是解密后的明文授权码
    assert sent[0]["password"] == "secret"


# ==================== 授权码落库加密 ====================


async def test_smtp_password_stored_encrypted(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)

    resp = await client.put(
        "/api/admin/system-settings",
        headers=_auth(admin),
        json={"smtp_password": "plain-secret"},
    )
    assert resp.status_code == 200

    stored = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == "smtp_password"))
    ).scalar_one()
    assert stored.value.startswith(system_settings.PASSWORD_PREFIX)
    assert "plain-secret" not in stored.value

    # 回显只给 smtp_password_set，不回明文
    resp = await client.get("/api/admin/system-settings", headers=_auth(admin))
    assert resp.json()["smtp_password_set"] is True
    assert "password" not in resp.json()


async def test_smtp_password_plaintext_compat(session) -> None:
    """历史明文能被读出并懒回写成密文（走 autouse fixture 隔离后的测试会话）。"""
    session.add(SystemSetting(key="smtp_password", value="legacy-plain"))
    await session.commit()

    # 直接走 service 层读 + 回写逻辑（SessionLocal 已被指到测试会话）
    cfg = await system_settings.get_effective_smtp_config()
    assert cfg["password"] == "legacy-plain"

    # 回读库里：已被重写为密文
    stored_row = (
        await session.execute(select(SystemSetting).where(SystemSetting.key == "smtp_password"))
    ).scalar_one()
    assert stored_row.value.startswith(system_settings.PASSWORD_PREFIX)
    assert "legacy-plain" not in stored_row.value

    # 密文再读一次应还原明文
    cfg2 = await system_settings.get_effective_smtp_config()
    assert cfg2["password"] == "legacy-plain"


async def test_smtp_password_without_secret_stays_plain(monkeypatch) -> None:
    """SMTP_SECRET 与 JWT_SECRET 都为空时：不加密（保底明文，发信可用）。"""

    class NoSecretSettings:
        smtp_secret = ""
        jwt_secret = ""

    monkeypatch.setattr(system_settings, "get_settings", lambda: NoSecretSettings())
    assert system_settings.encrypt_smtp_password("anything") == "anything"


# ==================== 总览缓存 ====================


async def test_overview_totals_cached(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    await _seed_user(session, "alice")

    first = (await client.get("/api/admin/overview", headers=_auth(admin))).json()
    assert first["totals"]["users"] == 2

    # 插入新用户：缓存未失效前总览不变
    await _seed_user(session, "bob")
    second = (await client.get("/api/admin/overview", headers=_auth(admin))).json()
    assert second["totals"]["users"] == 2

    # 失效后重新聚合
    admin_stats.invalidate_overview_cache()
    third = (await client.get("/api/admin/overview", headers=_auth(admin))).json()
    assert third["totals"]["users"] == 3


# ==================== 用户详情 ====================


async def test_user_overview(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")
    c = await _seed_competitor(session, alice.id, "feishu")
    await _seed_event(session, c.id, "t1")
    await _seed_report(session, alice.id, "w1", date(2026, 9, 14), date(2026, 9, 20))
    await _seed_crawl_log(session, alice.id, c.id)

    resp = await client.get(f"/api/admin/users/{alice.id}/overview", headers=_auth(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "alice"
    assert body["competitor_count"] == 1
    assert body["event_count"] == 1
    assert body["report_count"] == 1
    assert body["crawl_log_count"] == 1
    assert body["crawl_success_count"] == 1
    assert body["crawl_fail_count"] == 0
    assert body["competitor_names"] == ["feishu"]
    assert body["report_titles"] == ["w1"]
    assert len(body["event_trend"]) == 30
    assert body["event_trend"][-1]["count"] == 1

    # 不存在的用户 404
    resp = await client.get("/api/admin/users/9999/overview", headers=_auth(admin))
    assert resp.status_code == 404


# ==================== 平台数据（三 tab 分页列表） ====================


async def test_admin_events_list(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")
    bob = await _seed_user(session, "bob")
    c1 = await _seed_competitor(session, alice.id, name="飞书")
    c2 = await _seed_competitor(session, bob.id, name="钉钉")
    await _seed_event(session, c1.id, "飞书降价")
    await _seed_event(session, c2.id, "钉钉改版")

    resp = await client.get(
        "/api/admin/events", headers=_auth(admin), params={"page": 1, "page_size": 10}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    # 按 id 倒序：钉钉在其后
    first, second = body["items"]
    assert second["title"] == "飞书降价"
    assert second["competitor_name"] == "飞书"
    assert second["owner_username"] == "alice"
    assert second["event_type_label"]  # 类型标签非空
    assert first["owner_username"] == "bob"

    # keyword 过滤
    resp = await client.get(
        "/api/admin/events", headers=_auth(admin), params={"keyword": "降价"}
    )
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["title"] == "飞书降价"

    # 普通用户 403
    resp = await client.get("/api/admin/events", headers=_auth(alice))
    assert resp.status_code == 403


async def test_admin_reports_list(client, session) -> None:
    from app.models.weekly_report import WeeklyReport

    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")
    await _seed_report(session, alice.id, "第40周周报", date(2026, 9, 14), date(2026, 9, 20))
    session.add(
        WeeklyReport(
            user_id=alice.id,
            title="第39周周报（已删）",
            range_start=date(2026, 9, 7),
            range_end=date(2026, 9, 13),
            deleted_at=date(2026, 9, 21),
        )
    )
    await session.commit()

    resp = await client.get(
        "/api/admin/reports", headers=_auth(admin), params={"page": 1, "page_size": 10}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    deleted, active = body["items"]
    assert deleted["deleted"] is True
    assert active["deleted"] is False
    assert active["title"] == "第40周周报"
    assert active["report_type"] == "weekly"
    assert active["range_start"] == "2026-09-14"
    assert active["owner_username"] == "alice"

    # 普通用户 403
    resp = await client.get("/api/admin/reports", headers=_auth(alice))
    assert resp.status_code == 403


async def test_admin_crawl_logs_list(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")
    c1 = await _seed_competitor(session, alice.id, name="飞书")
    await _seed_crawl_log(session, alice.id, c1.id)
    await _seed_crawl_log(session, alice.id, c1.id)

    resp = await client.get(
        "/api/admin/crawl-logs",
        headers=_auth(admin),
        params={"page": 1, "page_size": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["competitor_name"] == "probe"
    assert item["source_name"] == "probe-home"
    assert item["status"] == "success"
    assert item["owner_username"] == "alice"

    # keyword 按监控源匹配
    resp = await client.get(
        "/api/admin/crawl-logs", headers=_auth(admin), params={"keyword": "probe-home"}
    )
    assert resp.json()["total"] == 2

    # 普通用户 403
    resp = await client.get("/api/admin/crawl-logs", headers=_auth(alice))
    assert resp.status_code == 403


# ==================== 平台公告 ====================


async def test_announcements_full_flow(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")

    # 发布
    resp = await client.post(
        "/api/admin/announcements",
        headers=_auth(admin),
        json={"content": "今晚 22:00 系统维护"},
    )
    assert resp.status_code == 200
    ann = resp.json()
    assert ann["is_active"] is True

    # 用户端可见
    resp = await client.get("/api/announcements/active", headers=_auth(alice))
    assert [a["id"] for a in resp.json()] == [ann["id"]]

    # 下线后用户端不可见
    resp = await client.patch(
        f"/api/admin/announcements/{ann['id']}",
        headers=_auth(admin),
        json={"is_active": False},
    )
    assert resp.status_code == 200
    resp = await client.get("/api/announcements/active", headers=_auth(alice))
    assert resp.json() == []

    # 管理端仍能看到已下线公告
    resp = await client.get("/api/admin/announcements", headers=_auth(admin))
    assert len(resp.json()) == 1
    assert resp.json()[0]["is_active"] is False


async def test_announcements_guards(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")

    # 普通用户不能发布
    resp = await client.post(
        "/api/admin/announcements", headers=_auth(alice), json={"content": "x"}
    )
    assert resp.status_code == 403

    # 空内容拒绝
    resp = await client.post(
        "/api/admin/announcements", headers=_auth(admin), json={"content": "   "}
    )
    assert resp.status_code == 400

    # 未登录不能读 active
    resp = await client.get("/api/announcements/active")
    assert resp.status_code == 401