"""抓取相关的响应模型（里程碑 6）。

前端拿它做"立即抓取"的即时反馈：每个页面成功/失败、有没有变化、耗时多久。
"""
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.core.source_registry import SourceType


class CrawlSourceResult(BaseModel):
    """单个监控源的抓取结果。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    source_id: int
    source_name: str
    source_type: SourceType
    status: str  # success | failed
    http_status: int | None = None
    changed: bool = False
    first_time: bool = False
    # 本次变化是否生成了一条情报事件（太轻微时只留快照）
    event_created: bool = False
    error: str | None = None
    duration_ms: int = 0


class CrawlResult(BaseModel):
    """一次"立即抓取"的汇总结果。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    competitor_id: int
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    changed: int = 0
    results: list[CrawlSourceResult] = Field(default_factory=list)
