"""周报/月报生成逻辑的全场景测试。

覆盖：
1. 单元：窗口计算（周报/月报的起始与结束日）
2. 单元：重叠分类 classify_overlap（none / covered / duplicate / expanded / 多份取最大）
3. 单元：window_has_report（同一周期去重判断）
4. 集成 API /api/reports/generate：
   - weekly 无已有 → created（新建，窗口=本周一到今天）
   - monthly 无已有 → created（新建，窗口=本月1号到今天）
   - 已有跨度覆盖本次 → covered（直接返回已有，不新建）
   - 已有跨度重复 → conflict（提示用户抉择）
   - 已有跨度更小 → conflict（expanded，提示覆盖/新建）
   - resolve=overwrite → 覆盖指定报告（同周期份数不变）
   - resolve=new → 再生成一份新的（同周期多份）
   - overwrite 缺 id → 400；overwrite id 不存在 → 404
   - 周报与月报互不干扰（各自按类型判断重叠）
5. 调度器：无已有→生成；已有→跳过；锁被占→跳过（不覆盖已有）

LLM 全部用假客户端注入（返回固定 narrative），不依赖真实模型。
"""
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

import app.models  # noqa: F401
from app.core.security import create_access_token
from app.models.base import Base
from app.models.competitor import Competitor
from app.models.event import EventType, IntelligenceEvent
from app.models.user import User
from app.models.weekly_report import ReportType, WeeklyReport
from app.services import report as report_service

# 固定 LLM 返回（服务层拿到什么就写什么，只测报告逻辑、不测 AI 内容）
FAKE_NARRATIVE = {"summary": "AI 摘要", "markdown": "# 正文\n- 点 1"}


async def _make_user(session, username: str) -> User:
    u = User(username=username, email=f"{username}@test.local", password_hash="h")
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _make_competitor(session, user_id: int, name: str = "竞品A") -> Competitor:
    c = Competitor(user_id=user_id, name=name)
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return c


async def _make_event(
    session, competitor_id: int, day: date, event_type=EventType.NEW_FEATURE, priority="high"
) -> IntelligenceEvent:
    e = IntelligenceEvent(
        competitor_id=competitor_id,
        event_type=event_type,
        title=f"事件-{day.isoformat()}",
        confidence=0.9,
        priority=priority,
        created_at=datetime(day.year, day.month, day.day, 9, 0, 0),
    )
    session.add(e)
    await session.commit()
    await session.refresh(e)
    return e


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _patch_llm(monkeypatch):
    """把 LLM 调用换成假客户端，返回固定叙述。"""
    from app.core.llm import ReportNarrative

    class FakeLLM:
        async def weekly_report(self, **kwargs):
            return ReportNarrative(summary=FAKE_NARRATIVE["summary"], markdown=FAKE_NARRATIVE["markdown"])

    monkeypatch.setattr(
        report_service, "get_llm_client", lambda cfg: FakeLLM()
    )
    # get_user_llm_config 仍需真实走库（用户可能无配置 → .env 兜底），
    # 但假客户端不看配置，直接返回 narrative，因此无需 mock 配置解析。


# ============ 单元：窗口计算 ============


def test_window_weekly_is_monday_to_today():
    start, end = report_service.window_for(0, ReportType.WEEKLY)
    today = datetime.now().date()
    assert start == today - timedelta(days=today.weekday())  # 周一
    assert end == today  # 到今天


def test_window_weekly_weeks_ago_goes_back_full_weeks():
    start, end = report_service.window_for(1, ReportType.WEEKLY)
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    assert start == monday - timedelta(days=7)  # 上周一
    assert end == start + timedelta(days=6)  # 上周日（早于今天）


def test_window_monthly_is_first_of_month_to_today():
    start, end = report_service.window_for(0, ReportType.MONTHLY)
    today = datetime.now().date()
    assert start == today.replace(day=1)  # 本月1号
    assert end == today  # 到今天


# ============ 单元：重叠分类 ============


def _fake_report(rid: int, end: date, report_type=ReportType.WEEKLY) -> WeeklyReport:
    r = WeeklyReport(id=rid, user_id=1, report_type=report_type, title="t")
    r.range_start = date(2026, 1, 5)
    r.range_end = end
    return r


def test_classify_none_when_no_existing():
    target, kind = report_service.classify_overlap([], date(2026, 1, 10))
    assert target is None
    assert kind == "none"


def test_classify_covered_when_existing_spans_further():
    existing = [_fake_report(1, date(2026, 1, 12))]  # 已有到12号
    target, kind = report_service.classify_overlap(existing, date(2026, 1, 10))
    assert kind == "covered"
    assert target.id == 1


def test_classify_duplicate_when_same_end():
    existing = [_fake_report(1, date(2026, 1, 10))]
    _, kind = report_service.classify_overlap(existing, date(2026, 1, 10))
    assert kind == "duplicate"


def test_classify_expanded_when_existing_is_smaller():
    existing = [_fake_report(1, date(2026, 1, 9))]  # 已有到9号，本次到10号
    _, kind = report_service.classify_overlap(existing, date(2026, 1, 10))
    assert kind == "expanded"


def test_classify_picks_largest_span_as_overwrite_target():
    existing = [
        _fake_report(1, date(2026, 1, 8)),
        _fake_report(2, date(2026, 1, 9)),  # 跨度最大 → 应作为覆盖目标
        _fake_report(3, date(2026, 1, 7)),
    ]
    target, kind = report_service.classify_overlap(existing, date(2026, 1, 10))
    assert kind == "expanded"
    assert target.id == 2


# ============ 单元：window_has_report（定时去重） ============


async def test_window_has_report_true_after_insert(session):
    user = await _make_user(session, "dup_check")
    start, _ = report_service.window_for(0, ReportType.WEEKLY)
    assert not await report_service.window_has_report(session, user.id, start)

    session.add(
        WeeklyReport(
            user_id=user.id,
            report_type=ReportType.WEEKLY,
            title="x",
            range_start=start,
            range_end=start,
        )
    )
    await session.commit()
    assert await report_service.window_has_report(session, user.id, start)


async def test_window_has_report_is_type_aware(session):
    """周报存在不影响月报的去重判断（range_start 不同月份，也按类型隔离）。"""
    user = await _make_user(session, "type_aware")
    w_start, _ = report_service.window_for(0, ReportType.WEEKLY)
    m_start, _ = report_service.window_for(0, ReportType.MONTHLY)
    session.add(
        WeeklyReport(
            user_id=user.id,
            report_type=ReportType.WEEKLY,
            title="w",
            range_start=w_start,
            range_end=w_start,
        )
    )
    await session.commit()
    assert await report_service.window_has_report(session, user.id, w_start, ReportType.WEEKLY)
    assert not await report_service.window_has_report(session, user.id, m_start, ReportType.MONTHLY)


# ============ 集成 API：手动生成 ============


async def test_generate_weekly_creates_with_monday_to_today(client, session, monkeypatch):
    _patch_llm(monkeypatch)
    user = await _make_user(session, "gen_weekly")
    comp = await _make_competitor(session, user.id)
    await _make_event(session, comp.id, datetime.now().date())

    r = await client.post("/api/reports/generate", params={"reportType": "weekly"}, headers=_auth(user))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "created"
    assert data["report"]["type"] == "weekly"
    start, end = report_service.window_for(0, ReportType.WEEKLY)
    assert data["report"]["rangeStart"] == start.isoformat()
    assert data["report"]["rangeEnd"] == end.isoformat()
    # 事件数通过冻结的 stats 快照体现（events 行 value=1）
    events_stat = next(s for s in data["report"]["stats"] if s["key"] == "events")
    assert events_stat["value"] == 1
    assert "AI 摘要" in data["report"]["summary"]

    # 确实落库一份
    count = len((await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().all())
    assert count == 1


async def test_generate_monthly_creates_with_first_to_today(client, session, monkeypatch):
    _patch_llm(monkeypatch)
    user = await _make_user(session, "gen_monthly")
    comp = await _make_competitor(session, user.id)
    await _make_event(session, comp.id, datetime.now().date())

    r = await client.post("/api/reports/generate", params={"reportType": "monthly"}, headers=_auth(user))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "created"
    assert data["report"]["type"] == "monthly"
    start, end = report_service.window_for(0, ReportType.MONTHLY)
    assert data["report"]["rangeStart"] == start.isoformat()
    assert data["report"]["rangeEnd"] == end.isoformat()


async def test_generate_weekly_again_adds_second_in_same_period(client, session, monkeypatch):
    """同周期已有一份 → 再点生成直接新建第二份（可重复生成，不冲突不覆盖）。"""
    _patch_llm(monkeypatch)
    user = await _make_user(session, "dup_again")
    start, end = report_service.window_for(0, ReportType.WEEKLY)
    session.add(
        WeeklyReport(
            user_id=user.id, report_type=ReportType.WEEKLY, title="旧",
            range_start=start, range_end=end,
        )
    )
    await session.commit()

    r = await client.post("/api/reports/generate", params={"reportType": "weekly"}, headers=_auth(user))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "created"
    assert data["report"]["id"] is not None
    assert data["report"]["id"] != (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().first().id

    rows = (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().all()
    assert len(rows) == 2  # 旧 + 新，互不覆盖


async def test_generate_weekly_again_ignores_expanded_existing(client, session, monkeypatch):
    """已有报告跨度更小（只到昨天）→ 再点生成仍直接新建，不提示覆盖。"""
    _patch_llm(monkeypatch)
    user = await _make_user(session, "expanded_again")
    start, end = report_service.window_for(0, ReportType.WEEKLY)
    yesterday = end - timedelta(days=1)
    session.add(
        WeeklyReport(
            user_id=user.id, report_type=ReportType.WEEKLY, title="旧",
            range_start=start, range_end=yesterday,
        )
    )
    await session.commit()

    r = await client.post("/api/reports/generate", params={"reportType": "weekly"}, headers=_auth(user))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "created"
    assert data["report"]["rangeEnd"] == end.isoformat()  # 新报告窗口覆盖到今天

    rows = (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().all()
    assert len(rows) == 2


async def test_generate_weekly_again_keeps_existing_even_if_spans_further(client, session, monkeypatch):
    """已有报告跨度更大 → 再点生成仍直接新建一份，不动旧报告。"""
    _patch_llm(monkeypatch)
    user = await _make_user(session, "bigger_again")
    start, end = report_service.window_for(0, ReportType.WEEKLY)
    session.add(
        WeeklyReport(
            user_id=user.id, report_type=ReportType.WEEKLY, title="完整",
            range_start=start, range_end=end + timedelta(days=1),
        )
    )
    await session.commit()

    r = await client.post("/api/reports/generate", params={"reportType": "weekly"}, headers=_auth(user))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "created"
    assert data["report"]["title"].endswith("竞品周报")

    rows = (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().all()
    assert len(rows) == 2  # 旧报告保留 + 新增一份


async def test_delete_report_moves_to_trash(client, session, monkeypatch):
    """删除自己的报告 → 200 ok，行保留（软删除）、deleted_at 非空。"""
    _patch_llm(monkeypatch)
    user = await _make_user(session, "del_own")
    start, end = report_service.window_for(0, ReportType.WEEKLY)
    session.add(
        WeeklyReport(
            user_id=user.id, report_type=ReportType.WEEKLY, title="待删",
            range_start=start, range_end=end,
        )
    )
    await session.commit()
    rid = (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().first().id

    r = await client.delete(f"/api/reports/{rid}", headers=_auth(user))
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    rows = (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().all()
    assert len(rows) == 1  # 行仍在
    assert rows[0].deleted_at is not None  # 已软删除

    # 常规列表不再包含它
    r2 = await client.get("/api/reports", headers=_auth(user))
    assert r2.status_code == 200
    assert r2.json()["reports"] == []


async def test_trash_flows(client, session, monkeypatch):
    """回收站全流程：删除→列表可见→恢复→列表消失→再删除→彻底删除后行消失。"""
    _patch_llm(monkeypatch)
    user = await _make_user(session, "trash_flow")
    start, end = report_service.window_for(0, ReportType.WEEKLY)
    session.add(
        WeeklyReport(
            user_id=user.id, report_type=ReportType.WEEKLY, title="回收站试验",
            range_start=start, range_end=end,
        )
    )
    await session.commit()
    rid = (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().first().id

    # 删除 → 进回收站
    r = await client.delete(f"/api/reports/{rid}", headers=_auth(user))
    assert r.status_code == 200

    # 回收站列表可见
    r2 = await client.get("/api/reports/trash", headers=_auth(user))
    assert r2.status_code == 200, r2.text
    assert [i["id"] for i in r2.json()] == [rid]
    assert r2.json()[0]["deletedAt"]

    # 已删除的报告常规详情 404
    r3 = await client.get(f"/api/reports/{rid}", headers=_auth(user))
    assert r3.status_code == 404

    # 恢复 → 从回收站消失、常规列表可见
    r4 = await client.post(f"/api/reports/trash/{rid}", headers=_auth(user))
    assert r4.status_code == 200, r4.text
    assert r4.json()["id"] == rid
    assert not r4.json()["deletedAt"]
    r5 = await client.get("/api/reports/trash", headers=_auth(user))
    assert r5.json() == []

    # 再删除 → 彻底删除 → 行消失
    await client.delete(f"/api/reports/{rid}", headers=_auth(user))
    r6 = await client.delete(f"/api/reports/trash/{rid}", headers=_auth(user))
    assert r6.status_code == 204
    rows = (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().all()
    assert len(rows) == 0


async def test_trash_restore_not_in_trash_is_400(client, session, monkeypatch):
    """恢复一份未删除的报告 → 400。"""
    _patch_llm(monkeypatch)
    user = await _make_user(session, "trash_bad_restore")
    start, end = report_service.window_for(0, ReportType.WEEKLY)
    session.add(
        WeeklyReport(
            user_id=user.id, report_type=ReportType.WEEKLY, title="未删",
            range_start=start, range_end=end,
        )
    )
    await session.commit()
    rid = (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().first().id

    r = await client.post(f"/api/reports/trash/{rid}", headers=_auth(user))
    assert r.status_code == 400


async def test_purge_expired_removes_stale(client, session, monkeypatch):
    """超过保留期的软删除报告在访问回收站时被惰性清理。"""
    _patch_llm(monkeypatch)
    user = await _make_user(session, "trash_stale")
    start, end = report_service.window_for(0, ReportType.WEEKLY)
    session.add(
        WeeklyReport(
            user_id=user.id, report_type=ReportType.WEEKLY, title="过期",
            range_start=start, range_end=end,
            deleted_at=datetime.now() - timedelta(days=31),
        )
    )
    await session.commit()

    r = await client.get("/api/reports/trash", headers=_auth(user))
    assert r.status_code == 200
    assert r.json() == []  # 已自动清理

    rows = (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().all()
    assert len(rows) == 0


async def test_delete_report_not_found_is_404(client, session, monkeypatch):
    _patch_llm(monkeypatch)
    user = await _make_user(session, "del_missing")
    r = await client.delete("/api/reports/99999", headers=_auth(user))
    assert r.status_code == 404


async def test_delete_other_users_report_is_404(client, session, monkeypatch):
    """不能删除别人的报告。"""
    _patch_llm(monkeypatch)
    owner = await _make_user(session, "del_owner")
    thief = await _make_user(session, "del_thief")
    start, end = report_service.window_for(0, ReportType.WEEKLY)
    session.add(
        WeeklyReport(
            user_id=owner.id, report_type=ReportType.WEEKLY, title="别人的",
            range_start=start, range_end=end,
        )
    )
    await session.commit()
    rid = (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().first().id

    r = await client.delete(f"/api/reports/{rid}", headers=_auth(thief))
    assert r.status_code == 404

    # 别人的报告还在
    rows = (await session.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().all()
    assert len(rows) == 1


async def test_generate_types_are_independent(client, session, monkeypatch):
    """已有周报不影响生成月报（类型隔离）。"""
    _patch_llm(monkeypatch)
    user = await _make_user(session, "type_indep")
    w_start, w_end = report_service.window_for(0, ReportType.WEEKLY)
    session.add(
        WeeklyReport(
            user_id=user.id, report_type=ReportType.WEEKLY, title="周报",
            range_start=w_start, range_end=w_end,
        )
    )
    await session.commit()

    r = await client.post("/api/reports/generate", params={"reportType": "monthly"}, headers=_auth(user))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "created"  # 月报不受周报影响，正常新建


# ============ 调度器：每周/每月最后一天自动生成，不覆盖已有 ============


@pytest.fixture
def scheduler_env(db, monkeypatch):
    """把调度器的 SessionLocal / 锁 / 通知 注入到测试环境。"""
    from app.core.cache import MemoryCache
    from app.services import scheduler

    cache = MemoryCache()  # 共享同一实例，测试抢占锁与调度器取锁一致
    monkeypatch.setattr(scheduler, "SessionLocal", db)
    monkeypatch.setattr(scheduler, "get_cache", lambda: cache)
    monkeypatch.setattr(scheduler, "notifier", AsyncMock())
    scheduler.cache = cache
    return scheduler


async def test_scheduler_weekly_creates_when_missing(session, scheduler_env):
    user = await _make_user(session, "sch_weekly_new")
    start, _ = report_service.window_for(0, ReportType.WEEKLY)

    # 需要给 scheduler 的 DB 插入用户；直接用同一 sessionmaker 插入
    async with scheduler_env.SessionLocal() as s:
        # 用户在测试 session 已提交，但 scheduler 用新连接 → 先确认能查到
        users = (await s.execute(__import__("sqlalchemy").select(User))).scalars().all()
        assert len(users) >= 1

    created = await scheduler_env.generate_weekly_reports()
    assert created == 1

    # 落库且窗口正确
    async with scheduler_env.SessionLocal() as s:
        rows = (await s.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().all()
        assert len(rows) == 1
        assert rows[0].range_start == start


async def test_scheduler_weekly_skips_when_exists(session, scheduler_env):
    """已有报告 → 跳过，不再生成、不覆盖。"""
    user = await _make_user(session, "sch_weekly_skip")
    start, end = report_service.window_for(0, ReportType.WEEKLY)
    async with scheduler_env.SessionLocal() as s:
        s.add(
            WeeklyReport(
                user_id=user.id, report_type=ReportType.WEEKLY, title="已有",
                range_start=start, range_end=end,
            )
        )
        await s.commit()

    created = await scheduler_env.generate_weekly_reports()
    assert created == 0  # 跳过

    async with scheduler_env.SessionLocal() as s:
        rows = (await s.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().all()
        assert len(rows) == 1
        assert rows[0].title == "已有"  # 未被覆盖


async def test_scheduler_monthly_creates_and_skips(session, scheduler_env):
    """月报：无→生成，有→跳过。"""
    user = await _make_user(session, "sch_monthly")
    m_start, _ = report_service.window_for(0, ReportType.MONTHLY)
    async with scheduler_env.SessionLocal() as s:
        s.add(
            WeeklyReport(
                user_id=user.id, report_type=ReportType.MONTHLY, title="已有月报",
                range_start=m_start, range_end=m_start,
            )
        )
        await s.commit()

    created = await scheduler_env.generate_monthly_reports()
    assert created == 0  # 已有月报 → 跳过

    # 移除已有后 → 生成
    async with scheduler_env.SessionLocal() as s:
        for r in (await s.execute(__import__("sqlalchemy").select(WeeklyReport))).scalars().all():
            await s.delete(r)
        await s.commit()
    created = await scheduler_env.generate_monthly_reports()
    assert created == 1


async def test_scheduler_lock_held_skips(session, scheduler_env):
    """锁被其他实例占用 → 本轮跳过（不生成）。"""
    await _make_user(session, "sch_lock")

    cache = scheduler_env.cache  # 与调度器取锁共用的同一实例
    token = await cache.acquire(scheduler_env.LOCK_REPORT, ttl=60)
    assert token is not None

    created = await scheduler_env.generate_weekly_reports()
    assert created == 0  # 没抢到锁，直接跳过


async def test_scheduler_notifies_owner_only(session, scheduler_env):
    """报告生成完成的通知只发给**有竞品、且绑了邮箱**的账号本人。

    回归（2026-09-22）：原先统一发一句「已为 N 个账号生成本周竞品周报」给
    NOTIFY_RECIPIENTS（运维/管理员邮箱），用户自己的报告通知进了别人的信箱。
    """
    owner = await _make_user(session, "sch_notify_owner")
    await _make_competitor(session, owner.id)
    # 第二个账号：没绑邮箱 → 不该收到任何邮件
    session.add(User(username="sch_notify_nomail", email=None, password_hash="h"))
    await session.commit()

    created = await scheduler_env.generate_weekly_reports()
    assert created == 2  # 两个账号都生成了，但只有一个该收信

    calls = scheduler_env.notifier.notify.call_args_list
    assert len(calls) == 1
    assert calls[0].kwargs["to"] == [owner.email]
