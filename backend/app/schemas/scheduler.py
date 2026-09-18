"""调度器状态的响应模型（排障与验收用）。"""
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CFG = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SchedulerJobOut(BaseModel):
    model_config = _CFG

    id: str
    name: str = ""
    trigger: str = ""
    next_run_at: str = ""


class SchedulerStatusOut(BaseModel):
    model_config = _CFG

    enabled: bool = False
    running: bool = False
    tick_seconds: int = 60
    batch_limit: int = 20
    notify_enabled: bool = False
    notify_backend: str = "log"
    # 当前到期、等待抓取的监控源数量
    pending_sources: int = 0
    jobs: list[SchedulerJobOut] = Field(default_factory=list)
