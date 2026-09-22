"""管理员聚合统计：平台总览、用户统计列、越权拦截。"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.exceptions import ERR_FORBIDDEN
from app.core.security import create_access_token
from app.models.competitor import Competitor
from app.models.crawl_log import CrawlLog
from app.models.event import EventType, IntelligenceEvent
from app.models.user import User
from app.models.weekly_report import WeeklyReport

TREND_DAYS = 30


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _seed_user(
    session,
    username: str,
    *,
    is_admin: bool = False,
    is_active: bool = True,
) -> User:
    u = User(
        username=username,
        email=f"{username}@test.local",
        password_hash="hashed",
        is_admin=is_admin,
        is_active=is_active,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _seed_competitor(session, user_id: int, name: str) -> Competitor:
    c = Competitor(user_id=user_id, name=name, official_url=f"https://{name}.example.com")
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return c


async def _seed_event(session, competitor_id: int, title: str) -> None:
    session.add(
        IntelligenceEvent(
            competitor_id=competitor_id,
            event_type=EventType.OTHER,
            title=title,
        )
    )
    await session.commit()


async def _seed_report(
    session, user_id: int, title: str, range_start: date, range_end: date
) -> None:
    session.add(
        WeeklyReport(
            user_id=user_id,
            title=title,
            range_start=range_start,
            range_end=range_end,
        )
    )
    await session.commit()


async def _seed_crawl_log(session, user_id: int, competitor_id: int) -> None:
    session.add(
        CrawlLog(
            user_id=user_id,
            competitor_id=competitor_id,
            competitor_name="probe",
            source_name="probe-home",
            source_type="website",
            url="https://probe.example.com",
            trigger="manual",
            status="success",
        )
    )
    await session.commit()


# ==================== 越权 ====================


async def test_overview_requires_admin(client, session) -> None:
    alice = await _seed_user(session, "alice")
    resp = await client.get("/api/admin/overview", headers=_auth(alice))
    assert resp.status_code == 403
    assert resp.json()["code"] == ERR_FORBIDDEN


async def test_users_requires_admin(client, session) -> None:
    alice = await _seed_user(session, "alice2")
    resp = await client.get("/api/admin/users", headers=_auth(alice))
    assert resp.status_code == 403


# ==================== 平台总览 ====================


async def test_overview_totals_and_series(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")
    bob = await _seed_user(session, "bob", is_active=False)

    c1 = await _seed_competitor(session, alice.id, "feishu")
    await _seed_competitor(session, bob.id, "dingtalk")
    await _seed_event(session, c1.id, "t1")
    await _seed_event(session, c1.id, "t2")
    await _seed_report(
        session, alice.id, "w1", date(2026, 9, 14), date(2026, 9, 20)
    )
    await _seed_crawl_log(session, alice.id, c1.id)
    await _seed_crawl_log(session, alice.id, c1.id)

    resp = await client.get("/api/admin/overview", headers=_auth(admin))
    assert resp.status_code == 200
    body = resp.json()
    totals = body["totals"]
    assert totals == {
        "users": 3,
        "active_users": 2,
        "admin_users": 1,
        "competitors": 2,
        "sources": 0,
        "events": 2,
        "reports": 1,
        "crawl_logs": 2,
    }

    event_trend = body["event_trend"]
    crawl_trend = body["crawl_trend"]
    assert len(event_trend) == TREND_DAYS
    assert len(crawl_trend) == TREND_DAYS
    assert sum(p["count"] for p in event_trend) == 2
    assert sum(p["count"] for p in crawl_trend) == 2

    # date_iso 连续 30 天且最后一天是今天（本地时区）
    last_iso = datetime.now().astimezone().date().isoformat()
    assert event_trend[-1]["date_iso"] == last_iso
    first = date.fromisoformat(event_trend[0]["date_iso"])
    for offset, point in enumerate(event_trend):
        assert point["date_iso"] == (first + timedelta(days=offset)).isoformat()
        assert point["count"] == crawl_trend[offset]["count"]  # 两条线同日计数一致
    # 今天有 2 条事件 —— 种子的 created_at 默认 now
    assert event_trend[-1]["count"] == 2


# ==================== 用户列表统计 ====================


async def test_users_include_stats(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")
    bob = await _seed_user(session, "bob")

    c = await _seed_competitor(session, alice.id, "feishu")
    await _seed_event(session, c.id, "t1")
    await _seed_report(
        session, alice.id, "w1", date(2026, 9, 14), date(2026, 9, 20)
    )
    await _seed_crawl_log(session, alice.id, c.id)

    resp = await client.get("/api/admin/users", headers=_auth(admin))
    assert resp.status_code == 200
    body = resp.json()
    rows = {r["username"]: r for r in body["items"]}
    assert body["total"] == 3

    assert rows["alice"]["competitor_count"] == 1
    assert rows["alice"]["event_count"] == 1
    assert rows["alice"]["report_count"] == 1
    assert rows["alice"]["crawl_log_count"] == 1

    assert rows["bob"]["competitor_count"] == 0
    assert rows["bob"]["event_count"] == 0
    assert rows["bob"]["report_count"] == 0
    assert rows["bob"]["crawl_log_count"] == 0


async def test_users_keyword_still_works(client, session) -> None:
    admin = await _seed_user(session, "boss", is_admin=True)
    await _seed_user(session, "alice")
    await _seed_user(session, "bobby")

    resp = await client.get("/api/admin/users", headers=_auth(admin), params={"keyword": "bob"})
    assert resp.status_code == 200
    rows = resp.json()["items"]
    assert [r["username"] for r in rows] == ["bobby"]
    assert "crawl_log_count" in rows[0]


# ==================== 软删口径 ====================


async def test_users_stats_exclude_soft_deleted(client, session) -> None:
    """竞品/周报软删后不计入统计；事件作为历史留痕仍保留。"""
    admin = await _seed_user(session, "boss", is_admin=True)
    alice = await _seed_user(session, "alice")

    c = await _seed_competitor(session, alice.id, "feishu")
    await _seed_event(session, c.id, "t1")
    c2 = await _seed_competitor(session, alice.id, "dingtalk")
    c2.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    r = WeeklyReport(
        user_id=alice.id,
        title="soft-deleted",
        range_start=date(2026, 9, 14),
        range_end=date(2026, 9, 20),
        deleted_at=datetime.now(timezone.utc),
    )
    session.add(r)
    await session.commit()

    resp = await client.get("/api/admin/users", headers=_auth(admin))
    rows = {u["username"]: u for u in resp.json()["items"]}
    assert rows["alice"]["competitor_count"] == 1
    assert rows["alice"]["event_count"] == 1
    assert rows["alice"]["report_count"] == 0