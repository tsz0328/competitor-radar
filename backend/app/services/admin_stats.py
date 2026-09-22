"""管理员聚合统计：全局总量、跨用户每日趋势、用户级数据统计子查询。

与 `services/trend.py` 的区别：这里**不做用户过滤**，统计的是全平台数据。
分层：本模块只负责从数据库聚合出数字，schema 与路由留在 `api/admin.py`。
"""
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import to_local
from app.models.competitor import Competitor
from app.models.crawl_log import CrawlLog
from app.models.event import IntelligenceEvent
from app.models.source import MonitorSource
from app.models.user import User
from app.models.weekly_report import WeeklyReport

# 总览趋势图回溯天数（与工作台趋势图口径一致）
OVERVIEW_TREND_DAYS = 30

# ==================== 总览聚合内存缓存 ====================
# 总览是跨用户聚合查询，用户量上来后每刷一次页面就扫全表；开发期不引入
# Redis，先用进程内缓存 + 5 分钟 TTL。业务写入（用户增删改）时调用
# invalidate_overview_cache() 主动失效，保证管理操作后立即看到新数字。

_OVERVIEW_CACHE_TTL_SECONDS = 300
_overview_cache: dict = {"timestamp": 0.0, "data": None}


async def overview_totals_cached(db: AsyncSession) -> dict[str, int]:
    """总览总量：命中缓存直接返回，否则聚合后写入缓存。"""
    global _overview_cache
    now = time.monotonic()
    if _overview_cache["data"] is not None and (
        now - _overview_cache["timestamp"] < _OVERVIEW_CACHE_TTL_SECONDS
    ):
        return _overview_cache["data"]
    data = await overview_totals(db)
    _overview_cache = {"timestamp": now, "data": data}
    return data


def invalidate_overview_cache() -> None:
    """业务写入后立即失效（用户增删改、竞品/报告等归属变化都走这里）。"""
    global _overview_cache
    _overview_cache = {"timestamp": 0.0, "data": None}


def user_stat_subqueries() -> tuple:
    """返回 4 个「按 user_id 计数」的子查询，供用户列表统计列复用。

    每个子查询都只有 (user_id, cnt) 两列；调用方用 outerjoin + coalesce 挂到
    User 上，避免多个一对多 join 同时 count 导致计数翻倍。
    """
    competitor_sub = (
        select(
            Competitor.user_id.label("user_id"),
            func.count().label("cnt"),
        )
        .where(Competitor.deleted_at.is_(None))
        .group_by(Competitor.user_id)
        .subquery()
    )
    # 事件是历史留痕：竞品软删后仍计入该用户产出，故不过滤 deleted_at
    event_sub = (
        select(
            Competitor.user_id.label("user_id"),
            func.count().label("cnt"),
        )
        .join(IntelligenceEvent, IntelligenceEvent.competitor_id == Competitor.id)
        .group_by(Competitor.user_id)
        .subquery()
    )
    report_sub = (
        select(
            WeeklyReport.user_id.label("user_id"),
            func.count().label("cnt"),
        )
        .where(WeeklyReport.deleted_at.is_(None))
        .group_by(WeeklyReport.user_id)
        .subquery()
    )
    crawl_sub = (
        select(
            CrawlLog.user_id.label("user_id"),
            func.count().label("cnt"),
        )
        .group_by(CrawlLog.user_id)
        .subquery()
    )
    return competitor_sub, event_sub, report_sub, crawl_sub


async def overview_totals(db: AsyncSession) -> dict[str, int]:
    """平台全局总量：用户/竞品/监控源/事件/周报/抓取日志。"""
    async def _count(stmt) -> int:
        return int((await db.execute(stmt)).scalar_one())

    users = await _count(select(func.count()).select_from(User))
    active_users = await _count(
        select(func.count()).select_from(User).where(User.is_active.is_(True))
    )
    admin_users = await _count(
        select(func.count()).select_from(User).where(User.is_admin.is_(True))
    )
    competitors = await _count(
        select(func.count())
        .select_from(Competitor)
        .where(Competitor.deleted_at.is_(None))
    )
    sources = await _count(select(func.count()).select_from(MonitorSource))
    events = await _count(select(func.count()).select_from(IntelligenceEvent))
    reports = await _count(
        select(func.count())
        .select_from(WeeklyReport)
        .where(WeeklyReport.deleted_at.is_(None))
    )
    crawl_logs = await _count(select(func.count()).select_from(CrawlLog))
    return {
        "users": users,
        "active_users": active_users,
        "admin_users": admin_users,
        "competitors": competitors,
        "sources": sources,
        "events": events,
        "reports": reports,
        "crawl_logs": crawl_logs,
    }


async def build_global_daily_series(
    db: AsyncSession,
    days: int,
    column: Column,
) -> list[dict]:
    """跨用户按 `created_at` 分桶的近 N 天序列，窗口内无数据的天补 0。

    column 传 `IntelligenceEvent.created_at`（情报趋势）或
    `CrawlLog.created_at`（抓取趋势）。返回
    `[{"date": "9/15", "date_iso": "2026-09-15", "count": 0}, ...]`。

    注意必须走 `to_local` 分桶：SQLite 取回的是 naive UTC，直接取
    `.date()` 会按机器时区解读，差 8 小时。
    """
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=days - 1)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = select(column).where(column >= since)
    buckets: dict[str, int] = {}
    for (created_at,) in (await db.execute(stmt)).all():
        local = to_local(created_at)
        if local is None:
            continue
        key = local.strftime("%Y-%m-%d")
        buckets[key] = buckets.get(key, 0) + 1

    points: list[dict] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        iso = day.strftime("%Y-%m-%d")
        points.append(
            {
                "date": f"{day.month}/{day.day}",
                "date_iso": iso,
                "count": buckets.get(iso, 0),
            }
        )
    return points


async def build_user_daily_series(
    db: AsyncSession,
    days: int,
    column: Column,
    user_id: int,
) -> list[dict]:
    """单个用户近 N 天的 `created_at` 序列（用户详情抽屉用）。

    与 build_global_daily_series 同口径（to_local 分桶、空天补 0），
    只是按 Competitor.user_id 把口径收窄到单个用户。
    """
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=days - 1)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(column)
        .join(Competitor, Competitor.id == IntelligenceEvent.competitor_id)
        .where(Competitor.user_id == user_id, column >= since)
    )
    buckets: dict[str, int] = {}
    for (created_at,) in (await db.execute(stmt)).all():
        local = to_local(created_at)
        if local is None:
            continue
        key = local.strftime("%Y-%m-%d")
        buckets[key] = buckets.get(key, 0) + 1

    points: list[dict] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        iso = day.strftime("%Y-%m-%d")
        points.append(
            {
                "date": f"{day.month}/{day.day}",
                "date_iso": iso,
                "count": buckets.get(iso, 0),
            }
        )
    return points


async def overview_totals_for_user(
    db: AsyncSession, user_id: int, competitor_ids
) -> dict[str, int]:
    """单个用户的数据总量（用户详情抽屉用）。

    口径与用户列表统计列一致：竞品/周报只计未删除，事件/抓取日志全量；
    额外给出抓取日志的成功/失败分布。
    """
    async def _count(stmt) -> int:
        return int((await db.execute(stmt)).scalar_one())

    competitors = await _count(
        select(func.count())
        .select_from(Competitor)
        .where(Competitor.user_id == user_id, Competitor.deleted_at.is_(None))
    )
    events = await _count(
        select(func.count())
        .select_from(IntelligenceEvent)
        .where(IntelligenceEvent.competitor_id.in_(competitor_ids))
    )
    reports = await _count(
        select(func.count())
        .select_from(WeeklyReport)
        .where(WeeklyReport.user_id == user_id, WeeklyReport.deleted_at.is_(None))
    )
    crawl_logs = await _count(
        select(func.count())
        .select_from(CrawlLog)
        .where(CrawlLog.user_id == user_id)
    )
    crawl_success = await _count(
        select(func.count())
        .select_from(CrawlLog)
        .where(CrawlLog.user_id == user_id, CrawlLog.status == "success")
    )
    return {
        "competitors": competitors,
        "events": events,
        "reports": reports,
        "crawl_logs": crawl_logs,
        "crawl_success": crawl_success,
        "crawl_fail": crawl_logs - crawl_success,
    }