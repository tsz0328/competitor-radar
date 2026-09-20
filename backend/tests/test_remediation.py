"""整改回归测试：覆盖 Codex 评审清单里「现有测试没覆盖、问题才没被提前发现」的关键路径。

- #2 暂停竞品后调度仍抓取
- #3 事件按日期筛选的 8 小时时区偏差
- #5 手动生成周报可重复生成同一周
- #6 删除竞品时事件/快照的解绑保留
- #9 通知未读口径持续膨胀（时间窗）
- #12 任意 URL 探测的 SSRF 拦截

这些用例刻意贴近「用户操作后服务端落库 → 再读回来」的真实链路，能挡住对应回归。
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.event_types import EventType
from app.core.network import validate_remote_url
from app.core.security import create_access_token
from app.core.source_registry import RenderMode, SourceType
from app.core.timeutil import local_day_end_utc, local_day_start_utc
from app.models.competitor import Competitor, CompetitorStatus
from app.models.event import IntelligenceEvent
from app.models.source import MonitorSource
from app.models.user import User
from app.models.weekly_report import WeeklyReport
from app.services.scheduler import count_due_sources


# --------------------------------------------------------------------------- #
# 测试 fixture 助手（与既有 test_notifications.py 风格一致）
# --------------------------------------------------------------------------- #
async def _make_user(session: object, username: str = "alice") -> User:
    u = User(username=username, password_hash="hashed")
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _make_competitor(
    session: object, user_id: int, status: CompetitorStatus = CompetitorStatus.ACTIVE
) -> Competitor:
    c = Competitor(user_id=user_id, name="竞品A", status=status)
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return c


async def _make_source(
    session: object,
    competitor_id: int,
    *,
    enabled: bool = True,
    last_crawled_at: datetime | None = None,
) -> MonitorSource:
    s = MonitorSource(
        competitor_id=competitor_id,
        source_type=SourceType.HOMEPAGE,
        name="官网首页",
        url="https://example.com",
        render_mode=RenderMode.HTTP,
        interval_minutes=60,
        enabled=enabled,
        last_crawled_at=last_crawled_at,
    )
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return s


async def _make_event(
    session: object,
    competitor_id: int,
    priority: str = "high",
    *,
    created_at: datetime | None = None,
    source_id: int | None = None,
    event_type: EventType | None = None,
) -> IntelligenceEvent:
    e = IntelligenceEvent(
        competitor_id=competitor_id,
        event_type=event_type or list(EventType)[0],
        title="价格变动",
        priority=priority,
        created_at=created_at,
        source_id=source_id,
    )
    session.add(e)
    await session.commit()
    await session.refresh(e)
    return e


# --------------------------------------------------------------------------- #
# #2 暂停竞品后，定时任务不再把它纳入抓取
# --------------------------------------------------------------------------- #
async def test_scheduler_skips_paused_competitor(session: object) -> None:
    u = await _make_user(session)
    active = await _make_competitor(session, u.id, CompetitorStatus.ACTIVE)
    paused = await _make_competitor(session, u.id, CompetitorStatus.PAUSED)
    # 两个源都"到期"（last_crawled_at=None），但暂停竞品应被过滤掉
    await _make_source(session, active.id)
    await _make_source(session, paused.id)

    due = await count_due_sources(session, u.id)  # type: ignore[arg-type]
    assert due == 1


# --------------------------------------------------------------------------- #
# #3 事件按自然日筛选：业务时区 Asia/Shanghai = UTC+8，无 8 小时偏差
# --------------------------------------------------------------------------- #
def test_timezone_day_boundary_is_china_aware() -> None:
    start = local_day_start_utc(date(2026, 9, 11))
    end = local_day_end_utc(date(2026, 9, 11))
    # 上海 09-11 00:00 == UTC 09-10 16:00
    assert start == datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 9, 11, 16, 0, tzinfo=timezone.utc)
    assert (end - start) == timedelta(days=1)


async def test_event_date_filter_respects_local_day(
    client: object, session: object
) -> None:
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    # 2026-09-11 01:00 UTC == 上海 09-11 09:00，属于 09-11 这一自然日
    await _make_event(
        session, comp.id, created_at=datetime(2026, 9, 11, 1, 0, tzinfo=timezone.utc)
    )

    # 单日窗口用 startDate+endDate；该事件属上海 09-11，应命中
    same_day = await client.get(
        "/api/events",
        params={"startDate": "2026-09-11", "endDate": "2026-09-11"},
        headers=_auth(u),
    )
    assert same_day.status_code == 200, same_day.text
    assert same_day.json()["total"] == 1

    # 前一天单日窗口：事件不在 09-10（8 小时口径已修），应排除
    prev_day = await client.get(
        "/api/events",
        params={"startDate": "2026-09-10", "endDate": "2026-09-10"},
        headers=_auth(u),
    )
    assert prev_day.json()["total"] == 0


# --------------------------------------------------------------------------- #
# #5 手动生成周报：同一自然周重复请求复用已有报告，不新建
# --------------------------------------------------------------------------- #
async def test_weekly_report_generate_is_idempotent(
    client: object, session: object
) -> None:
    # 关掉 LLM，避免测试去打真实模型；无 Key 时周报走规则兜底
    get_settings().llm_enabled = False

    u = await _make_user(session)
    r1 = await client.post(
        "/api/reports/generate", params={"weeksAgo": 1}, headers=_auth(u)
    )
    assert r1.status_code == 200, r1.text
    report_id = r1.json()["id"]

    r2 = await client.post(
        "/api/reports/generate", params={"weeksAgo": 1}, headers=_auth(u)
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["id"] == report_id  # 同一周复用

    total = (
        await session.execute(
            select(func.count())
            .select_from(WeeklyReport)
            .where(WeeklyReport.user_id == u.id)
        )
    ).scalar() or 0
    assert total == 1


# --------------------------------------------------------------------------- #
# #6 删除竞品：监控源与原始网页文件删除，事件/快照解绑后保留历史
# --------------------------------------------------------------------------- #
async def test_delete_competitor_retains_events(
    client: object, session: object
) -> None:
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    src = await _make_source(session, comp.id)
    ev = await _make_event(session, comp.id, source_id=src.id)

    r = await client.delete(f"/api/competitors/{comp.id}", headers=_auth(u))
    assert r.status_code == 204, r.text

    comp_row = (
        await session.execute(
            select(Competitor).where(Competitor.id == comp.id)
        )
    ).scalar_one_or_none()
    assert comp_row is None  # 竞品已删

    ev_row = (
        await session.execute(
            select(IntelligenceEvent)
            .where(IntelligenceEvent.id == ev.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    assert ev_row is not None  # 事件仍在
    assert ev_row.source_id is None  # 但已与已删的监控源解绑


# --------------------------------------------------------------------------- #
# #9 通知未读口径受时间窗约束，旧高优事件不再计入未读
# --------------------------------------------------------------------------- #
async def test_notification_window_excludes_old_events(
    client: object, session: object
) -> None:
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    # 200 天前的高优事件：超出默认 90 天窗口，不应计入未读
    await _make_event(
        session,
        comp.id,
        "high",
        created_at=datetime.now(timezone.utc) - timedelta(days=200),
    )
    # 今天的高优事件：应计入
    await _make_event(session, comp.id, "high")

    r = await client.get("/api/notifications/unread-count", headers=_auth(u))
    assert r.status_code == 200, r.text
    assert r.json()["unread"] == 1


# --------------------------------------------------------------------------- #
# #12 SSRF：回环 / 链路本地 / 私网（默认关）一律拦截；放开私网后仅私网放行
# --------------------------------------------------------------------------- #
async def test_ssrf_blocks_loopback_link_local_and_private() -> None:
    blocked = [
        "http://localhost",
        "http://127.0.0.1",
        "http://[::1]",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1",
        "http://192.168.1.1",
        "http://172.16.0.1",
        "http://10.0.0.1:8080",  # 非标准端口也应被协议/端口校验拦下
    ]
    for url in blocked:
        res = await validate_remote_url(url)
        assert res.ok is False, f"应当拦截：{url} -> {res.message}"


async def test_ssrf_allows_private_when_enabled() -> None:
    from app.core import network

    saved = network.settings.allow_private_network_urls
    network.settings.allow_private_network_urls = True
    try:
        # 私网 IP 字面量不会触发 DNS 查询，可安全断言
        res = await validate_remote_url("http://10.0.0.1")
        assert res.ok is True, res.message
        # 即便放开私网，回环仍必须拦截
        loop = await validate_remote_url("http://127.0.0.1")
        assert loop.ok is False
    finally:
        network.settings.allow_private_network_urls = saved
