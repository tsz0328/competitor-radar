"""时间展示的通用工具。

SQLite 不保存时区，SQLAlchemy 取回的是 naive datetime（实为 UTC），
所有对外展示的时间都必须先按 UTC 解读、再转成本地时区，否则会差 8 小时。
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def app_timezone() -> ZoneInfo:
    """返回业务时区；配置错误会在首次使用时显式失败，避免静默落错日期。"""
    return ZoneInfo(get_settings().app_timezone)


def local_day_start_utc(day: date) -> datetime:
    """业务时区某自然日 00:00 对应的 UTC 时刻。"""
    local_start = datetime(day.year, day.month, day.day, tzinfo=app_timezone())
    return local_start.astimezone(timezone.utc)


def local_day_end_utc(day: date) -> datetime:
    """业务时区某自然日 24:00 对应的 UTC 时刻。"""
    next_day = day + timedelta(days=1)
    return local_day_start_utc(next_day)


def to_utc(moment: datetime | None) -> datetime | None:
    """把库里取回的时间统一解读成带时区的 UTC 时间。"""
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def to_local(moment: datetime | None) -> datetime | None:
    utc = to_utc(moment)
    return utc.astimezone(app_timezone()) if utc else None


def humanize_ago(moment: datetime | None, *, empty: str = "从未") -> str:
    """相对时间，如 刚刚 / 12 分钟前 / 3 小时前 / 2 天前。"""
    utc = to_utc(moment)
    if utc is None:
        return empty
    seconds = (datetime.now(timezone.utc) - utc).total_seconds()
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    return f"{int(seconds // 86400)} 天前"


def format_time(moment: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    local = to_local(moment)
    return local.strftime(fmt) if local else ""


def date_parts(moment: datetime | None) -> tuple[str, str, str]:
    """返回 (日期, 时间, 日期标签)：如 ("2026-09-11", "10:24", "今天")。"""
    local = to_local(moment)
    if local is None:
        return "", "", ""
    date_text = local.strftime("%Y-%m-%d")
    time_text = local.strftime("%H:%M")
    delta = (datetime.now(app_timezone()).date() - local.date()).days
    if delta == 0:
        label = "今天"
    elif delta == 1:
        label = "昨天"
    else:
        label = date_text
    return date_text, time_text, label
