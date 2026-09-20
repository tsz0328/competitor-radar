from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from pydantic.alias_generators import to_camel

from app.core.timeutil import format_time, humanize_ago, to_utc
from app.models.competitor import CompetitorStatus
from app.schemas.source import MonitorSourceCreate, MonitorSourceOut, normalize_url

# 列表里最多平铺展示几个页面名，多出来的折叠成 "+N"
_MAX_VISIBLE_PAGES = 3

# 频率换算：按"周 → 天 → 小时"从大到小试，能整除就用对应单位
_INTERVAL_UNITS = ((10080, "周"), (1440, "天"), (60, "小时"))


def _humanize_interval(minutes: int) -> str:
    """把分钟数说成人话，如 1440 → 每天。"""
    for unit_minutes, unit in _INTERVAL_UNITS:
        if minutes % unit_minutes == 0:
            count = minutes // unit_minutes
            return f"每{unit}" if count == 1 else f"每 {count} {unit}"
    return f"每 {minutes} 分钟"


def _failed_sources(sources: list[MonitorSourceOut]) -> list[MonitorSourceOut]:
    """最近一次抓取失败的监控源（含因连续失败被自动停用的，状态要如实反映）。"""
    return [s for s in sources if s.last_status == "failed"]


def _auto_disabled_sources(sources: list[MonitorSourceOut]) -> list[MonitorSourceOut]:
    """因连续失败被自动停用、当前仍处于禁用态的监控源。"""
    return [s for s in sources if s.auto_disabled]


def _next_crawl_at(sources: list[MonitorSourceOut]) -> str:
    """预计下次抓取时间：取所有**启用中**的源里最早到期的那个。

    口径与调度器一致（上次抓取时间 + 该源自己的间隔）。
    调度器每分钟扫一次，所以这里给的是"最早可能被抓"的时间点——
    界面上用「即将」而不是精确到秒，避免给出比实际更精确的暗示。
    """
    enabled = [s for s in sources if s.enabled]
    if not enabled:
        return "已暂停"

    now = datetime.now(timezone.utc)
    due_times: list[datetime] = []
    for source in enabled:
        last = to_utc(source.last_crawled_at)
        if last is None:
            return "即将抓取"  # 从未抓过 → 下一轮扫描就会抓
        due_times.append(last + timedelta(minutes=max(1, source.interval_minutes)))

    earliest = min(due_times)
    if earliest <= now:
        return "即将抓取"

    local = earliest.astimezone()
    delta_days = (local.date() - datetime.now().astimezone().date()).days
    if delta_days == 0:
        return f"今天 {local:%H:%M}"
    if delta_days == 1:
        return f"明天 {local:%H:%M}"
    return f"{local.month}月{local.day}日 {local:%H:%M}"


class CompetitorCreate(BaseModel):
    """新增竞品时传的字段。

    official_url 必填：竞品监控的核心就是"盯官网"，没有网址无从监控。
    sources 可选：不传时后端自动为官网首页建一个监控源，做到"填完即可开始监控"。
    """

    # 前端按 camelCase 提交（officialUrl / sources[].sourceType），同时兼容下划线写法
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=100)
    official_url: str = Field(..., min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=50)
    sources: list[MonitorSourceCreate] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("竞品名称不能为空")
        return v

    @field_validator("official_url")
    @classmethod
    def _normalize_official_url(cls, v: str) -> str:
        value = normalize_url(v)
        if not value:
            raise ValueError("官网地址不能为空")
        return value


class CompetitorUpdate(BaseModel):
    """修改竞品：所有字段都可省略，只改传了的那些。

    sources 是"整份替换"语义：传了就以它为准做增删改，不传则完全不动监控源。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    official_url: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=50)
    status: CompetitorStatus | None = None
    sources: list[MonitorSourceCreate] | None = None

    @field_validator("official_url")
    @classmethod
    def _normalize_official_url(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        return normalize_url(v)


class CompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)

    id: int
    user_id: int
    name: str
    official_url: str | None = None
    category: str | None = None
    status: CompetitorStatus
    created_at: datetime

    # 该竞品下的监控源（selectin 预加载，直接可读）
    sources: list[MonitorSourceOut] = Field(default_factory=list)

    # 由列表接口聚合填充：
    changes: int = 0
    today_changes: int = 0

    # ---- 以下为前端展示用的派生字段，均由上面的原始字段/监控源算出 ----

    @computed_field
    @property
    def domain(self) -> str:
        return self.official_url or ""

    @computed_field
    @property
    def category_type(self) -> str:
        return "saas"  # 前端用于 CSS 类名（tag-saas）

    @computed_field
    @property
    def pages(self) -> list[str]:
        return [s.name for s in self.sources[:_MAX_VISIBLE_PAGES]]

    @computed_field
    @property
    def extra_pages(self) -> int:
        return max(0, len(self.sources) - _MAX_VISIBLE_PAGES)

    @computed_field
    @property
    def frequency(self) -> str:
        intervals = [s.interval_minutes for s in self.sources if s.enabled]
        return _humanize_interval(min(intervals)) if intervals else "未配置"

    @computed_field
    @property
    def frequency_desc(self) -> str:
        return "定时抓取" if self.sources else "暂无监控源"

    @computed_field
    @property
    def last_fetch_ago(self) -> str:
        times = [s.last_crawled_at for s in self.sources if s.last_crawled_at]
        return humanize_ago(max(times), empty="从未抓取") if times else "从未抓取"

    @computed_field
    @property
    def last_fetch_time(self) -> str:
        times = [s.last_crawled_at for s in self.sources if s.last_crawled_at]
        return format_time(max(times)) if times else ""

    @computed_field
    @property
    def next_crawl_at(self) -> str:
        """预计下次抓取时间（由定时调度器驱动，见里程碑 10）。"""
        return _next_crawl_at(self.sources)

    @computed_field
    @property
    def enabled(self) -> bool:
        return self.status == CompetitorStatus.ACTIVE

    @computed_field
    @property
    def status_label(self) -> str:
        if self.status != CompetitorStatus.ACTIVE:
            return "已暂停"
        return "监控异常" if _failed_sources(self.sources) else "监控中"

    @computed_field
    @property
    def status_type(self) -> str:
        if self.status != CompetitorStatus.ACTIVE:
            return "info"
        return "warning" if _failed_sources(self.sources) else "success"

    @computed_field
    @property
    def status_desc(self) -> str:
        if self.status != CompetitorStatus.ACTIVE:
            return "手动暂停"
        failed = _failed_sources(self.sources)
        if not failed:
            return "正常"
        desc = f"抓取失败 {sum(s.fail_count for s in failed)} 次"
        stopped = _auto_disabled_sources(self.sources)
        if stopped:
            desc += f"，{len(stopped)} 个页面已停用"
        return desc


    @computed_field
    @property
    def logo_url(self) -> str | None:
        """首选图标地址：竞品官网自身的 favicon。

        不用 Clearbit 之类的第三方 logo 服务——它们不稳定且部分已弃用，
        而且前端还有 favicon → apple-touch-icon → 首字母头像的多级回退。
        """
        if not self.official_url:
            return None
        host = self.official_url.split("//")[-1].split("/")[0].strip()
        host = host[4:] if host.startswith("www.") else host
        return f"https://{host}/favicon.ico" if host else None


class FaviconOut(BaseModel):
    """真实图标解析结果（给 SPA 站点兜底，见 services/favicon.py）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    logo_url: str | None = None


class SuggestRequest(BaseModel):
    """「智能预填」接口的请求：竞品名称 + 可选分类候选项。

    use_llm：是否允许调用 AI 推断官网/分类。
    - True（默认）：「智能检测填充」按钮走 LLM，能处理中文品牌名等复杂情况；
    - False：用户自己填竞品时的自动预填，只用规则域名探测，不消耗 AI。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=100)
    categories: list[str] = Field(default_factory=list)
    use_llm: bool = True


class SuggestResult(BaseModel):
    """「智能预填」接口的响应：推断出的官网地址与分类（可能为空）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    official_url: str | None = None
    category: str | None = None
    source: str = "none"  # llm | probe | none
    message: str = ""
