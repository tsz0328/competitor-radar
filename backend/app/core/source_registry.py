import enum
from dataclasses import dataclass


class RenderMode(str, enum.Enum):
    """抓取方式：browser=用浏览器渲染 JS；http=直接发请求。"""

    BROWSER = "browser"
    HTTP = "http"


class SourceType(str, enum.Enum):
    """v1 支持的 8 种数据源（白名单见 docs/positioning.md）。"""

    HOMEPAGE = "homepage"
    PRICING = "pricing"
    CHANGELOG = "changelog"
    BLOG = "blog"
    DOCS = "docs"
    STATUS = "status"
    RSS = "rss"
    APP_STORE = "app_store"


@dataclass(frozen=True)
class SourceTypeConfig:
    """一类数据源的采集策略（frozen=创建后不可改）。"""

    label: str  # 中文名，前端展示用
    render: RenderMode  # 怎么抓
    default_interval_minutes: int  # 默认多久抓一次
    extractor: str  # 正文怎么提取
    differ: str  # 怎么比对变化
    llm_hint: str = ""  # 给 AI 的分类提示


SOURCE_TYPE_REGISTRY: dict[SourceType, SourceTypeConfig] = {
    SourceType.HOMEPAGE: SourceTypeConfig(
        "官网首页", RenderMode.BROWSER, 1440, "trafilatura", "full_text", "官网首页内容变化"
    ),
    SourceType.PRICING: SourceTypeConfig(
        "定价页", RenderMode.BROWSER, 1440, "price_table", "full_text", "定价/套餐/计费调整"
    ),
    SourceType.CHANGELOG: SourceTypeConfig(
        "更新日志", RenderMode.BROWSER, 1440, "release_block", "item_set", "新版本/新功能/修复"
    ),
    SourceType.BLOG: SourceTypeConfig(
        "官方博客", RenderMode.HTTP, 1440, "rss", "item_set", "官方文章发布"
    ),
    SourceType.DOCS: SourceTypeConfig(
        "帮助文档", RenderMode.BROWSER, 10080, "trafilatura", "full_text", "文档内容变更"
    ),
    SourceType.STATUS: SourceTypeConfig(
        "服务状态页", RenderMode.BROWSER, 60, "trafilatura", "full_text", "故障/维护公告"
    ),
    SourceType.RSS: SourceTypeConfig(
        "RSS 订阅", RenderMode.HTTP, 60, "rss", "item_set", "订阅源条目变化"
    ),
    SourceType.APP_STORE: SourceTypeConfig(
        "应用商店页", RenderMode.BROWSER, 1440, "store_block", "structured", "版本更新/评分波动"
    ),
}


def get_source_config(source_type) -> SourceTypeConfig:
    """按类型取策略（传字符串或枚举都行）。"""
    key = source_type if isinstance(source_type, SourceType) else SourceType(source_type)
    return SOURCE_TYPE_REGISTRY[key]
