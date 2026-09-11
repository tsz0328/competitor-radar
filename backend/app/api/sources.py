"""数据源类型的"目录"接口。

前端新增竞品时用它渲染"可选的监控页面"，从而与后端注册表口径完全一致：
以后 SOURCE_TYPE_REGISTRY 新增一种类型，前端无需改代码即可出现新选项。
"""
from fastapi import APIRouter

from app.core.source_registry import SOURCE_TYPE_REGISTRY
from app.schemas.source import SourceTypeOption

router = APIRouter(prefix="/api/source-types", tags=["sources"])


@router.get("", response_model=list[SourceTypeOption])
async def list_source_types():
    """返回 v1 白名单里的全部数据源类型（含中文名、抓取方式、默认频率）。"""
    return [
        SourceTypeOption(
            type=source_type,
            label=cfg.label,
            render=cfg.render,
            default_interval_minutes=cfg.default_interval_minutes,
            llm_hint=cfg.llm_hint,
        )
        for source_type, cfg in SOURCE_TYPE_REGISTRY.items()
    ]
