"""通知中心接口集成测试：覆盖未授权、列表、未读数、标记已读、SSE。

事件不是经公开 API 创建，而是直接落库（贴近 analyzer 产生高优事件后的状态），
重点验证「通知 = 自己竞品下的高优事件 + 服务端已读态」这一核心语义。
"""

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

    async def fake_notify(title: str, message: str, to: list[str] | None = None):
        mails.append({"title": title, "to": to})
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



