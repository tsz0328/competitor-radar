"""竞品周报的响应模型（字段与前端 ReportDetail 一一对应）。

注意：这里的所有数字都来自数据库聚合，只有 summary / content 两段叙述文字是 AI 产出。
"""
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CFG = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ReportFavoriteIn(BaseModel):
    """收藏切换入参。"""

    model_config = _CFG

    favorite: bool


class ReportShareIn(BaseModel):
    """生成免登录分享链接入参。"""

    model_config = _CFG

    # 有效期（天）；为空表示永久有效
    expires_days: int | None = Field(default=None, ge=1, le=365)


class ReportShareOut(BaseModel):
    """免登录分享链接的响应（前端拼完整 URL 供复制）。"""

    model_config = _CFG

    token: str
    # 生成时间+过期时间；expires_at 为空 = 永久有效
    expires_at: str = ""


class ReportListItemOut(BaseModel):
    model_config = _CFG

    id: int
    title: str
    type: str = "weekly"
    type_label: str = "周报"
    range: str = ""
    competitors: int = 0
    generated_at: str = ""
    favorite: bool = False
    month_group: str = ""
    deleted_at: str = ""  # 非空 = 已移入回收站（回收站列表展示删除时间）


class ReportListOut(BaseModel):
    model_config = _CFG

    total: int = 0
    reports: list[ReportListItemOut] = Field(default_factory=list)


class ReportStatItemOut(BaseModel):
    model_config = _CFG

    key: str
    label: str
    value: int = 0
    delta: int = 0  # 环比百分比（绝对值）
    delta_type: str = "up"  # up | down


class ReportHighlightOut(BaseModel):
    model_config = _CFG

    id: int
    title: str
    tag: str
    tag_type: str
    impact: str = "中影响"
    impact_type: str = "mid"  # high | mid
    points: list[str] = Field(default_factory=list)
    affected: list[str] = Field(default_factory=list)
    found_at: str = ""
    ai_confidence: int = 0


class NameValueOut(BaseModel):
    model_config = _CFG

    name: str
    value: int = 0


class ImpactTrendOut(BaseModel):
    model_config = _CFG

    dates: list[str] = Field(default_factory=list)
    current: list[int] = Field(default_factory=list)
    previous: list[int] = Field(default_factory=list)


class ReportRelatedEventOut(BaseModel):
    model_config = _CFG

    id: int
    brand: str
    title: str
    tag: str
    tag_type: str
    time: str = ""


class ReportRelatedCompetitorOut(BaseModel):
    model_config = _CFG

    name: str
    # 官网主机名：前端据此取竞品图标（favicon → apple-touch-icon → 解析首页
    # → 首字母头像）。早期生成的周报内容里没有这个字段，缺失时前端走首字母。
    domain: str = ""
    icon_text: str = "?"
    icon_bg: str = "#e8f0fe"
    icon_color: str = "#4285f4"
    changes: int = 0


class ReportAiStepOut(BaseModel):
    model_config = _CFG

    title: str
    desc: str
    time: str = ""


class ReportDetailOut(BaseModel):
    model_config = _CFG

    id: int
    title: str
    type: str = "weekly"  # weekly | monthly
    type_label: str = "周报"
    range_start: str = ""
    range_end: str = ""
    competitors: int = 0
    favorite: bool = False

    summary: str = ""
    content: str = ""  # AI 写的周报正文（Markdown）

    stats: list[ReportStatItemOut] = Field(default_factory=list)
    highlights: list[ReportHighlightOut] = Field(default_factory=list)
    category_dist: list[NameValueOut] = Field(default_factory=list)
    competitor_rank: list[NameValueOut] = Field(default_factory=list)
    impact_trend: ImpactTrendOut = Field(default_factory=ImpactTrendOut)
    related_events: list[ReportRelatedEventOut] = Field(default_factory=list)
    related_competitors: list[ReportRelatedCompetitorOut] = Field(default_factory=list)
    ai_steps: list[ReportAiStepOut] = Field(default_factory=list)


class ReportGenerateOut(BaseModel):
    """生成接口的结果：每次调用都直接新建一份新的报告。"""

    model_config = _CFG

    status: str = "created"
    report: ReportDetailOut | None = None


class ReportGenerateStatusOut(BaseModel):
    """当前用户正在生成的报告类型（null 表示无进行中的生成）。

    生成是同步请求，前端刷新后靠它恢复「生成中」按钮状态。
    """

    model_config = _CFG

    generating: str | None = None
