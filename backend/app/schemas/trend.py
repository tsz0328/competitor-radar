"""趋势分析相关的响应模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field
from pydantic.alias_generators import to_camel

from app.core.timeutil import format_time
from app.models.trend import TREND_DIRECTION_LABELS, TrendDirection


class TrendPointOut(BaseModel):
    """趋势图上的一个数据点，与前端 TrendChart 的五条折线一一对应。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    date: str  # 如 9/11
    feature: int = 0  # 功能更新
    price: int = 0  # 价格变化
    sentiment: int = 0  # 舆论动态
    content: int = 0  # 内容更新
    other: int = 0  # 其他


class TrendInsightOut(BaseModel):
    """某个竞品的趋势判断。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    competitor_id: int
    competitor_name: str = ""
    period_days: int = 30
    direction: TrendDirection
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)

    # 统计口径全部来自真实事件
    event_count: int = 0
    high_impact_count: int = 0
    coverage_days: int = 0
    created_at: datetime

    @computed_field
    @property
    def direction_label(self) -> str:
        return TREND_DIRECTION_LABELS[self.direction]

    @computed_field
    @property
    def generated_at(self) -> str:
        return format_time(self.created_at, "%Y-%m-%d %H:%M")


class SeriesPointOut(BaseModel):
    """多竞品对比折线上的一个数据点（某天的变化总数）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    date: str  # 如 9/11
    count: int = 0


class DailyCountOut(BaseModel):
    """全部竞品汇总的每日变化总数（工作台「近 N 天情报变化趋势」用）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    date: str  # 图表 x 轴，如 9/15
    date_iso: str  # 点击钻取用，如 2026-09-15
    count: int = 0


class CompetitorSeriesOut(BaseModel):
    """某个竞品在一段时间内的每日变化总数（多竞品对比折线的一条线）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    competitor_id: int
    competitor_name: str = ""
    points: list[SeriesPointOut] = Field(default_factory=list)
