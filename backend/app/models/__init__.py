# 汇总导出：确保 Base 与全部模型被 import，create_all 才能"看到"所有表
from app.models.base import Base
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.setting import AppSetting
from app.models.snapshot import PageSnapshot
from app.models.source import MonitorSource
from app.models.trend import TrendInsight
from app.models.user import User
from app.models.weekly_report import WeeklyReport

__all__ = [
    "Base",
    "AppSetting",
    "Competitor",
    "IntelligenceEvent",
    "MonitorSource",
    "PageSnapshot",
    "TrendInsight",
    "User",
    "WeeklyReport",
]
