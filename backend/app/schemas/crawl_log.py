"""抓取日志的响应模型：列表页分页展示用。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CrawlLogItem(BaseModel):
    """一条抓取日志 = 一个监控源的一次抓取结果。"""

    model_config = ConfigDict(
        from_attributes=True, alias_generator=to_camel, populate_by_name=True
    )

    id: int
    competitor_id: int
    competitor_name: str
    source_id: int | None = None
    source_name: str
    source_type: str
    url: str
    trigger: str  # manual / scheduler
    status: str  # success / failed / skipped
    http_status: int | None = None
    changed: bool = False
    first_time: bool = False
    event_created: bool = False
    duration_ms: int = 0
    error: str | None = None
    created_at: datetime


class CrawlLogPage(BaseModel):
    """分页结果。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    items: list[CrawlLogItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
