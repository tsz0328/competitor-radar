"""通知中心接口集成测试：覆盖未授权、列表、未读数、标记已读、SSE。

事件不是经公开 API 创建，而是直接落库（贴近 analyzer 产生高优事件后的状态），
重点验证「通知 = 自己竞品下的高优事件 + 服务端已读态」这一核心语义。
"""

from datetime import datetime, timedelta, timezone

from app.core.event_types import EventType
from app.core.security import create_access_token
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.user import User


async def _make_user(session: object, username: str = "alice") -> User:
    # 账号名与邮箱已解绑：造数据时账号名是自定义值，邮箱另给一个（也可以不给）
    u = User(
        username=username, email=f"{username}@test.local", password_hash="hashed"
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _make_competitor(session: object, user_id: int) -> Competitor:
    c = Competitor(user_id=user_id, name="竞品A")
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return c


async def _make_event(
    session: object, competitor_id: int, priority: str = "high"
) -> IntelligenceEvent:
    e = IntelligenceEvent(
        competitor_id=competitor_id,
        event_type=list(EventType)[0],
        title="价格变动",
        priority=priority,
    )
    session.add(e)
    await session.commit()
    await session.refresh(e)
    return e


async def _make_event_days_ago(
    session: object, competitor_id: int, days_ago: int, priority: str = "high"
) -> IntelligenceEvent:
    """造一条「N 天前」的高优事件——用于验证时间窗与归档视图的边界。

    created_at 是 server_default，创建后显式赋值再 commit 会走 UPDATE，稳定生效。
    """
    e = await _make_event(session, competitor_id, priority)
    e.created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    await session.commit()
    await session.refresh(e)
    return e


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def test_unauthorized(client: object) -> None:
    r = await client.get("/api/notifications")
    assert r.status_code == 401


async def test_empty_unread(client: object, session: object) -> None:
    u = await _make_user(session)
    r = await client.get("/api/notifications", headers=_auth(u))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["unread"] == 0


async def test_high_event_shows_and_unread(client: object, session: object) -> None:
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    await _make_event(session, comp.id, "high")
    body = (await client.get("/api/notifications", headers=_auth(u))).json()
    assert body["total"] == 1
    assert body["unread"] == 1
    assert body["records"][0]["isRead"] is False


async def test_non_high_event_not_in_notifications(
    client: object, session: object
) -> None:
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    await _make_event(session, comp.id, "low")
    body = (await client.get("/api/notifications", headers=_auth(u))).json()
    assert body["total"] == 0
    assert body["unread"] == 0


async def test_other_user_cannot_see_my_event(client: object, session: object) -> None:
    u1 = await _make_user(session, "alice")
    u2 = await _make_user(session, "bob")
    comp = await _make_competitor(session, u1.id)
    await _make_event(session, comp.id, "high")
    body = (await client.get("/api/notifications", headers=_auth(u2))).json()
    assert body["total"] == 0
    assert body["unread"] == 0


async def test_mark_read_single(client: object, session: object) -> None:
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    e = await _make_event(session, comp.id, "high")
    r = await client.post(f"/api/notifications/{e.id}/read", headers=_auth(u))
    assert r.status_code == 200
    assert r.json()["unread"] == 0
    body = (await client.get("/api/notifications", headers=_auth(u))).json()
    assert body["records"][0]["isRead"] is True


async def test_mark_all_read(client: object, session: object) -> None:
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    await _make_event(session, comp.id, "high")
    await _make_event(session, comp.id, "high")
    r = await client.post("/api/notifications/read-all", headers=_auth(u))
    assert r.status_code == 200
    assert r.json()["unread"] == 0
    body = (await client.get("/api/notifications", headers=_auth(u))).json()
    assert all(rec["isRead"] for rec in body["records"])


async def test_unread_count_endpoint(client: object, session: object) -> None:
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    await _make_event(session, comp.id, "high")
    r = await client.get("/api/notifications/unread-count", headers=_auth(u))
    assert r.status_code == 200
    assert r.json()["unread"] == 1


# --------------------------------------------------------------------------- #
# 归档视图：days=0 拉全量高优事件（不受系统默认时间窗限制）
# --------------------------------------------------------------------------- #
async def test_archive_days_zero_includes_old_events(
    client: object, session: object
) -> None:
    """默认时间窗（90 天）外的老事件，只有 days=0 归档视图才看得到。"""
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    await _make_event(session, comp.id, "high")  # 今天
    await _make_event_days_ago(session, comp.id, 200)  # 超出默认窗口

    default_body = (await client.get("/api/notifications", headers=_auth(u))).json()
    assert default_body["total"] == 1, "默认窗口应只含今天那条"

    archive = (
        await client.get("/api/notifications?days=0", headers=_auth(u))
    ).json()
    assert archive["total"] == 2, "days=0 应含全部历史高优事件"
    assert archive["unread"] == 2
    # 倒序：今天那条在前
    assert archive["records"][0]["isRead"] is False


async def test_days_scopes_window(client: object, session: object) -> None:
    """days=N 是 N 天窗口：200 天前的事件在 days=100 里看不到，days=0 才看得到。"""
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    await _make_event_days_ago(session, comp.id, 200)

    assert (
        await client.get("/api/notifications?days=100", headers=_auth(u))
    ).json()["total"] == 0
    assert (
        await client.get("/api/notifications?days=0", headers=_auth(u))
    ).json()["total"] == 1


async def test_archive_read_all_scoped_by_window(
    client: object, session: object
) -> None:
    """read-all 默认只标时间窗内的；带 days=0 才把归档里的老事件也标已读。"""
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    await _make_event_days_ago(session, comp.id, 200)

    # 默认 read-all 命中窗口内 0 条 → 老事件仍未读
    assert (
        await client.post("/api/notifications/read-all", headers=_auth(u))
    ).status_code == 200
    assert (
        await client.get("/api/notifications?days=0", headers=_auth(u))
    ).json()["unread"] == 1

    # 归档 read-all（days=0）→ 老事件也标已读
    assert (
        await client.post("/api/notifications/read-all?days=0", headers=_auth(u))
    ).json()["unread"] == 0
    assert (
        await client.get("/api/notifications?days=0", headers=_auth(u))
    ).json()["unread"] == 0


# --------------------------------------------------------------------------- #
# 高优事件推送：没绑邮箱就只推站内，不发邮件
# --------------------------------------------------------------------------- #
async def test_high_priority_without_email_skips_mail(monkeypatch) -> None:
    """用户没绑邮箱时只推站内事件，**不发邮件**。

    这里刻意不走「传空收件人」那条路——`notifier._recipients()` 对空收件人会回退到
    `NOTIFY_RECIPIENTS`（运维邮箱），那会把**别人的**竞品情报投到运维信箱。
    所以 analyzer 必须在没邮箱时直接跳过邮件分支，本用例就是钉住这一点。
    """
    from types import SimpleNamespace

    from app.core import event_bus
    from app.services import analyzer, notifier

    mails: list[dict] = []
    published: list[dict] = []

    async def fake_notify(
        title: str, message: str, to: list[str] | None = None, email_enabled: bool = True
    ):
        mails.append({"title": title, "to": to, "email_enabled": email_enabled})
        return True

    class FakeBus:
        async def publish(self, user_id: int, payload: dict) -> None:
            published.append(payload)

    monkeypatch.setattr(notifier, "notify", fake_notify)
    monkeypatch.setattr(event_bus, "bus", FakeBus())

    competitor = SimpleNamespace(name="竞品A", user_id=1)
    source = SimpleNamespace(name="官网", url="https://example.com")
    event = SimpleNamespace(
        id=7,
        title="价格变动",
        summary="摘要",
        event_type=list(EventType)[0],
        priority="high",
    )

    # 没绑邮箱：站内事件照发，邮件不发
    await analyzer._notify_high_priority(competitor, source, event, [])
    assert mails == [], "没绑邮箱时不应该发任何邮件"
    assert published == [{"type": "high_event", "eventId": 7}]

    # 绑了邮箱：邮件发给本人
    await analyzer._notify_high_priority(competitor, source, event, ["owner@example.com"])
    assert len(mails) == 1
    assert mails[0]["to"] == ["owner@example.com"]
    assert len(published) == 2


async def test_high_priority_email_switch_off_passes_flag(monkeypatch) -> None:
    """用户关闭「接收邮件通知」开关后，analyzer 必须把 email_enabled=False 透传给
    notifier——这样 notifier 会直接跳过发信，只保留站内铃铛（不涉及 SMTP 配置）。

    钉住 2026-09-22 新增的开关链路：settings→analyzer→notifier。开关关掉时即便绑定了
    邮箱，邮件也不该发出去；开关开启时照常透传 email_enabled=True。
    """
    from types import SimpleNamespace

    from app.services import analyzer, notifier

    calls: list[dict] = []

    async def fake_notify(
        title: str, message: str, to: list[str] | None = None, email_enabled: bool = True
    ):
        calls.append({"to": to, "email_enabled": email_enabled})
        return True

    monkeypatch.setattr(notifier, "notify", fake_notify)

    competitor = SimpleNamespace(name="竞品A", user_id=1)
    source = SimpleNamespace(name="官网", url="https://example.com")
    event = SimpleNamespace(
        id=7,
        title="价格变动",
        summary="摘要",
        event_type=list(EventType)[0],
        priority="high",
    )

    # 开关关闭：即使绑了邮箱，邮件也不该发（email_enabled=False 透传）
    await analyzer._notify_high_priority(
        competitor, source, event, ["owner@example.com"], email_enabled=False
    )
    assert len(calls) == 1
    assert calls[0]["to"] == ["owner@example.com"]
    assert calls[0]["email_enabled"] is False

    # 开关开启：照常透传 email_enabled=True
    await analyzer._notify_high_priority(
        competitor, source, event, ["owner@example.com"], email_enabled=True
    )
    assert calls[1]["email_enabled"] is True


# --------------------------------------------------------------------------- #
# 调度器通知：按用户分别发，绝不回退运维邮箱
# --------------------------------------------------------------------------- #
async def test_crawl_summary_goes_to_each_owner(monkeypatch) -> None:
    """批次抓取汇总必须**按用户分别发**给各自的账号邮箱。

    回归（2026-09-22）：这两封原先不传收件人 → `notifier._recipients()` 回退
    `NOTIFY_RECIPIENTS`（运维/管理员邮箱），于是一个用户的竞品动态被投到另一个
    用户的信箱里。本用例钉住「谁是竞品的主人，邮件就发给谁」。
    """
    from app.services import notifier, scheduler

    mails: list[dict] = []

    async def fake_notify(
        title: str, message: str, to: list[str] | None = None, email_enabled: bool = True
    ):
        mails.append({"title": title, "message": message, "to": to, "email_enabled": email_enabled})
        return True

    monkeypatch.setattr(notifier, "notify", fake_notify)

    # emails 的契约是 id → (邮箱, 是否开启邮件通知)；关闭开关的账号只推站内、不发信
    per_user = {
        1: {"crawled": 3, "changed": 1, "events": 1},  # 有变化 → 发
        2: {"crawled": 5, "changed": 0, "events": 0},  # 抓了但没变 → 不打扰
        3: {"crawled": 2, "changed": 2, "events": 2},  # 没绑邮箱 → 只推站内，不发信
        4: {"crawled": 1, "changed": 1, "events": 0},  # 绑了邮箱但关了开关 → 不发信
    }
    emails = {
        1: ("owner@test.local", True),
        2: ("quiet@test.local", True),
        3: (None, True),
        4: ("muted@test.local", False),
    }

    await scheduler._notify_crawl_summary(per_user, emails)

    assert len(mails) == 1
    assert mails[0]["to"] == ["owner@test.local"]
    assert mails[0]["email_enabled"] is True
    assert "1 处" in mails[0]["title"]
    assert "3 个监控页面" in mails[0]["message"]


def test_report_ready_mail_skips_without_email_or_competitors() -> None:
    """报告生成通知：没绑邮箱、或名下没有竞品的账号都不发。"""
    from types import SimpleNamespace

    from app.services.scheduler import _report_ready_mail

    report = SimpleNamespace(
        title="2026年第39周 竞品周报", competitor_count=3, event_count=5
    )
    assert _report_ready_mail(None, report, "周报") is None
    assert (
        _report_ready_mail(
            "empty@test.local",
            SimpleNamespace(title="空报告", competitor_count=0, event_count=0),
            "周报",
        )
        is None
    )

    mail = _report_ready_mail("owner@test.local", report, "周报")
    assert mail is not None
    assert mail[0] == "owner@test.local"
    assert "2026年第39周 竞品周报" in mail[2]
    assert "3 个竞品" in mail[2]


def test_recipients_never_falls_back_to_sender(monkeypatch) -> None:
    """没传收件人时只认显式配置的 NOTIFY_RECIPIENTS，绝不复用发件账号。

    发件账号（SMTP_USERNAME / SMTP_SENDER）往往就是管理员本人的邮箱，
    一旦回退，用户数据就会被静默投进管理员信箱——这正是本次要堵的坑。
    """
    from types import SimpleNamespace

    from app.services import notifier

    monkeypatch.setattr(notifier, "settings", SimpleNamespace(notify_recipients=""))
    assert notifier._recipients(None) == []  # 宁可一封不发，也不猜收件人

    monkeypatch.setattr(
        notifier, "settings", SimpleNamespace(notify_recipients="ops@test.local")
    )
    assert notifier._recipients(None) == ["ops@test.local"]
    # 传了 to 就只发给 to，运维配置不参与
    assert notifier._recipients(["me@test.local"]) == ["me@test.local"]




