"""系统设置接口：AI 模型（LLM）配置的读取 / 保存 / 连接测试。

仅登录用户可访问；Key 只回传脱敏预览，绝不回传明文。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.runtime_config import LLMConfig
from app.models.user import User
from app.schemas.setting import (
    LLMSettingOut,
    LLMSettingUpdate,
    LLMTestRequest,
    LLMTestResult,
)
from app.services import settings as settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_out(cfg: LLMConfig, source: str) -> LLMSettingOut:
    mode = "real" if cfg.ready else "mock"
    if mode == "real":
        message = f"已启用真实模型（{cfg.model}）"
    elif cfg.enabled and not cfg.api_key:
        message = "已开启 AI 分析，但尚未填写 API Key，当前仍走规则 Mock"
    elif cfg.enabled:
        message = "已开启 AI 分析，但配置不完整（缺少地址或模型），当前仍走规则 Mock"
    else:
        message = "未启用 AI 分析，当前走规则 Mock（无需 Key 也能跑通全链路）"

    return LLMSettingOut(
        enabled=cfg.enabled,
        has_api_key=bool(cfg.api_key),
        api_key_preview=settings_service.mask_api_key(cfg.api_key),
        base_url=cfg.base_url,
        model=cfg.model,
        timeout_seconds=cfg.timeout_seconds,
        min_change_lines=cfg.min_change_lines,
        mode=mode,
        source=source,
        message=message,
    )


@router.get("/llm", response_model=LLMSettingOut)
async def read_llm_setting(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """读取当前 AI 模型配置（Key 脱敏）。"""
    cfg, source = await settings_service.get_llm_setting(db)
    return _to_out(cfg, source)


@router.put("/llm", response_model=LLMSettingOut)
async def update_llm_setting(
    payload: LLMSettingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存 AI 模型配置，保存后立即生效、无需重启。"""
    cfg, source = await settings_service.save_llm_setting(db, payload)
    return _to_out(cfg, source)


@router.post("/llm/test", response_model=LLMTestResult)
async def test_llm_setting(
    payload: LLMTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """测试模型连通性：用界面填的值（缺省用已保存的）发一次最小请求。"""
    return await settings_service.test_llm_connection(db, payload)
