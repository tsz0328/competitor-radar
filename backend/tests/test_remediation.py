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
from app.schemas.source import normalize_url
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
    # email 已是必填的登录标识（与 username 恒等），造数据时必须一起给
    u = User(
        username=username, email=f"{username}@test.local", password_hash="hashed"
    )
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
# #5 手动生成周报：同一自然周重复请求每次都新建一份，可重复生成
# --------------------------------------------------------------------------- #
async def test_weekly_report_generate_creates_new_each_time(
    client: object, session: object
) -> None:
    # 关掉 LLM，避免测试去打真实模型；无 Key 时周报走规则兜底
    get_settings().llm_enabled = False

    u = await _make_user(session)
    r1 = await client.post(
        "/api/reports/generate", params={"weeksAgo": 1}, headers=_auth(u)
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["status"] == "created"
    report_id_1 = body1["report"]["id"]

    # 同一自然周再次请求：直接生成一份新报告，不复用
    r2 = await client.post(
        "/api/reports/generate", params={"weeksAgo": 1}, headers=_auth(u)
    )
    assert r2.status_code == 200, r2.text
    report_id_2 = r2.json()["report"]["id"]
    assert report_id_2 != report_id_1

    total = (
        await session.execute(
            select(func.count())
            .select_from(WeeklyReport)
            .where(WeeklyReport.user_id == u.id)
        )
    ).scalar() or 0
    assert total == 2


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
            select(Competitor)
            .where(Competitor.id == comp.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    assert comp_row is not None  # 软删除：行仍在
    assert comp_row.deleted_at is not None  # 已移入回收站（30 天内可恢复）

    ev_row = (
        await session.execute(
            select(IntelligenceEvent)
            .where(IntelligenceEvent.id == ev.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    assert ev_row is not None  # 事件仍在
    assert ev_row.source_id == src.id  # 软删除保留监控源关联，恢复后历史数据自动连回


async def test_hard_delete_purges_trend_and_event_reads(
    client: object, session: object
) -> None:
    """彻底删除竞品：趋势分析(trend_insights)与事件已读标记(event_reads)一并清掉，不留孤儿。

    此前趋势分析因无外键级联、又不在清理列表里，竞品硬删后成了指向已删竞品的孤儿记录。
    """
    from app.models.notification import EventRead
    from app.models.trend import TrendInsight

    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    src = await _make_source(session, comp.id)
    ev = await _make_event(session, comp.id, source_id=src.id)

    trend = TrendInsight(
        competitor_id=comp.id,
        period_days=30,
        direction="stable",
        summary="近 30 天节奏平稳",
        event_count=1,
        high_impact_count=0,
        coverage_days=30,
    )
    session.add(trend)
    read = EventRead(user_id=u.id, event_id=ev.id, is_read=True)
    session.add(read)
    await session.commit()
    await session.refresh(trend)
    await session.refresh(read)

    # 软删除 → 移入回收站：趋势/已读应保留，以支持回收站恢复后历史连回
    r = await client.delete(f"/api/competitors/{comp.id}", headers=_auth(u))
    assert r.status_code == 204, r.text
    soft_trend = (
        await session.execute(
            select(TrendInsight).where(TrendInsight.id == trend.id)
        )
    ).scalar_one_or_none()
    assert soft_trend is not None  # 软删保留趋势
    soft_read = (
        await session.execute(select(EventRead).where(EventRead.id == read.id))
    ).scalar_one_or_none()
    assert soft_read is not None  # 软删保留已读标记

    # 从回收站彻底删除
    r2 = await client.delete(f"/api/competitors/trash/{comp.id}", headers=_auth(u))
    assert r2.status_code == 204, r2.text

    gone_trend = (
        await session.execute(
            select(TrendInsight).where(TrendInsight.id == trend.id)
        )
    ).scalar_one_or_none()
    assert gone_trend is None  # 趋势已随竞品清除
    gone_read = (
        await session.execute(select(EventRead).where(EventRead.id == read.id))
    ).scalar_one_or_none()
    assert gone_read is None  # 事件已读标记已随竞品清除


async def test_trash_restore_and_re_add_reconnects(
    client: object, session: object
) -> None:
    """回收站回归：软删除后可恢复；重加同官网竞品会恢复原行、历史事件自动连回。"""
    u = await _make_user(session)
    comp = await _make_competitor(session, u.id)
    comp.official_url = normalize_url("https://example.com")  # 与创建接口归一化口径一致
    await session.commit()
    await session.refresh(comp)
    src = await _make_source(session, comp.id)
    ev = await _make_event(session, comp.id, source_id=src.id)

    # 移入回收站
    r = await client.delete(f"/api/competitors/{comp.id}", headers=_auth(u))
    assert r.status_code == 204, r.text

    # 回收站可见，且常规列表不可见
    trash = await client.get("/api/competitors/trash", headers=_auth(u))
    assert trash.status_code == 200, trash.text
    trash_ids = {c["id"] for c in trash.json()}
    assert comp.id in trash_ids

    normal = await client.get("/api/competitors", headers=_auth(u))
    normal_ids = {c["id"] for c in normal.json()}
    assert comp.id not in normal_ids

    # 重加同官网竞品：命中回收站里的同名行 -> 直接恢复，restored=True，旧事件 competitor_id 不变
    payload = {
        "name": comp.name,
        "official_url": comp.official_url,
        "sources": [{"sourceType": "homepage", "url": comp.official_url, "enabled": True}],
    }
    ra = await client.post("/api/competitors", json=payload, headers=_auth(u))
    assert ra.status_code == 201, ra.text
    body = ra.json()
    assert body["id"] == comp.id  # 复用原行
    assert body.get("restored") is True  # 提示前端"已重新连接历史数据"

    # 恢复后：常规列表可见、回收站不可见，历史事件连回
    restored = (
        await session.execute(
            select(Competitor)
            .where(Competitor.id == comp.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    assert restored is not None and restored.deleted_at is None

    normal_after = await client.get("/api/competitors", headers=_auth(u))
    assert comp.id in {c["id"] for c in normal_after.json()}
    trash_after = await client.get("/api/competitors/trash", headers=_auth(u))
    assert comp.id not in {c["id"] for c in trash_after.json()}

    ev_row = (
        await session.execute(
            select(IntelligenceEvent)
            .where(IntelligenceEvent.id == ev.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    assert ev_row is not None and ev_row.competitor_id == comp.id  # 历史数据连回


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
