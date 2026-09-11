"""监控源的请求 / 响应模型。

三个角色：
- MonitorSourceCreate：新增竞品时顺带提交的"要盯哪些页面"
- MonitorSourceOut   ：竞品详情里回显的监控源（含注册表里的中文名）
- SourceTypeOption   ：给前端渲染"可选页面类型"用的目录项（来自注册表，口径唯一）
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from pydantic.alias_generators import to_camel

from app.core.source_registry import RenderMode, SourceType, get_source_config

# 频率的合理区间：最短 5 分钟，最长 30 天（防止误填 0 或天文数字）
_MIN_INTERVAL = 5
_MAX_INTERVAL = 43200


def normalize_url(raw: str) -> str:
    """把用户随手输入的地址补成规范 URL，并去掉结尾多余的斜杠。"""
    value = raw.strip().rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value


class MonitorSourceCreate(BaseModel):
    """新增竞品时附带的一个监控源。

    除 source_type 外都可省略：
    - url 省略时用竞品的官网地址兜底
    - name 省略时用注册表里的中文名（如"定价页"）
    - interval_minutes 省略时用注册表默认频率
    """

    # 前端按 camelCase 提交（sourceType / intervalMinutes），这里同时兼容下划线写法
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    source_type: SourceType
    url: str | None = None
    name: str | None = Field(default=None, max_length=100)
    interval_minutes: int | None = Field(default=None, ge=_MIN_INTERVAL, le=_MAX_INTERVAL)

    @field_validator("url")
    @classmethod
    def _clean_url(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        return normalize_url(v)


class SourceTypeOption(BaseModel):
    """前端"选择监控页面"的候选项：类型 + 中文名 + 抓取方式 + 默认频率。"""

    type: SourceType
    label: str
    render: RenderMode
    default_interval_minutes: int
    llm_hint: str = ""


class MonitorSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)

    id: int
    competitor_id: int
    source_type: SourceType
    name: str
    url: str
    render_mode: RenderMode
    interval_minutes: int
    enabled: bool
    # 抓取健康度（里程碑 6 起有真实值）
    last_status: str | None = None  # success | failed
    last_error: str | None = None
    fail_count: int = 0
    last_crawled_at: datetime | None = None

    @computed_field
    @property
    def label(self) -> str:
        """注册表里的中文名，避免前端再维护一份映射。"""
        return get_source_config(self.source_type).label
