"""系统设置接口：AI 模型（LLM）配置的读取 / 保存 / 连接测试。

**按用户隔离**：每个登录用户只能看到 / 修改自己的 AI 配置与供应商；
传别人的 provider_id 等同「不存在」（404），不会跨用户读写。

列表与设置回显只给脱敏预览；仅「编辑某条自己的供应商」时可按 id 单独取回明文
Key（见 /llm/providers/{id}/api-key），用于直接修改。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.runtime_config import LLMConfig
from app.models.user import User
from app.schemas.setting import (
    LLMApiKeyOut,
    LLMFetchModelsRequest,
    LLMFetchModelsResult,
    LLMModelsOut,
    LLMProviderCreate,
    LLMProviderOut,
    LLMProviderReorder,
    LLMProviderUpdate,
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
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """读取当前账号的 AI 模型配置（Key 脱敏）。"""
    cfg, source = await settings_service.get_llm_setting(db, current_user.id)
    return _to_out(cfg, source)


@router.put("/llm", response_model=LLMSettingOut)
async def update_llm_setting(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: LLMSettingUpdate,
):
    """保存当前账号的 AI 模型配置，保存后立即生效、无需重启。"""
    cfg, source = await settings_service.save_llm_setting(db, current_user.id, payload)
    return _to_out(cfg, source)


@router.post("/llm/test", response_model=LLMTestResult)
async def test_llm_setting(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: LLMTestRequest,
):
    """测试模型连通性：用界面填的值（缺省用自己已保存的）发一次最小请求。"""
    return await settings_service.test_llm_connection(db, current_user.id, payload)


# ---- 供应商管理：多个模型服务商，运行时使用「使用中」的那一条 ----


@router.get("/llm/providers", response_model=list[LLMProviderOut])
async def list_llm_providers(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """当前账号已配置的供应商列表（Key 脱敏）。"""
    return await settings_service.list_providers(db, current_user.id)


@router.post("/llm/providers", response_model=LLMProviderOut)
async def create_llm_provider(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: LLMProviderCreate,
):
    """添加供应商；当前账号的第一条自动设为「使用中」。"""
    return await settings_service.create_provider(db, current_user.id, payload)


@router.post("/llm/providers/models", response_model=LLMFetchModelsResult)
async def fetch_llm_provider_models(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: LLMFetchModelsRequest,
):
    """从上游供应商拉取模型列表（OpenAI 兼容的 GET /models），用于界面下拉选择。"""
    return await settings_service.fetch_provider_models(db, current_user.id, payload)


@router.post("/llm/providers/reorder", response_model=None)
async def reorder_llm_providers(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: LLMProviderReorder,
):
    """拖动排序：按期望顺序传一组自己的供应商 id（仅改展示顺序）。"""
    await settings_service.reorder_providers(db, current_user.id, payload.ids)


@router.put("/llm/providers/{provider_id}", response_model=LLMProviderOut)
async def update_llm_provider(
    provider_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: LLMProviderUpdate,
):
    """编辑自己的供应商（只改传了的字段；别人的 id 返回 404）。"""
    return await settings_service.update_provider(
        db, current_user.id, provider_id, payload
    )


@router.delete("/llm/providers/{provider_id}", response_model=None)
async def delete_llm_provider(
    provider_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """删除自己的供应商；删的是「使用中」的则自动切换到最新一条。"""
    await settings_service.delete_provider(db, current_user.id, provider_id)


@router.get("/llm/providers/{provider_id}/models", response_model=LLMModelsOut)
async def read_llm_provider_models(
    provider_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """读取自己某条供应商已缓存的完整模型列表（列表接口只回数量）。"""
    return LLMModelsOut(
        models=await settings_service.get_provider_models(
            db, current_user.id, provider_id
        )
    )


@router.get("/llm/providers/{provider_id}/api-key", response_model=LLMApiKeyOut)
async def read_llm_provider_api_key(
    provider_id: int,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """读取自己某条供应商已保存的 API Key 明文（编辑弹窗回显用）。

    明文只用于界面查看，明确禁止任何缓存，避免留存在浏览器缓存/磁盘里；
    且只有该供应商的归属用户能取到。
    """
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return LLMApiKeyOut(
        api_key=await settings_service.get_provider_api_key(
            db, current_user.id, provider_id
        )
    )


@router.post("/llm/providers/{provider_id}/activate", response_model=LLMProviderOut)
async def activate_llm_provider(
    provider_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """切换自己「使用中」的供应商。"""
    return await settings_service.activate_provider(
        db, current_user.id, provider_id
    )


@router.post("/llm/providers/{provider_id}/duplicate", response_model=LLMProviderOut)
async def duplicate_llm_provider(
    provider_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """复制自己的供应商（含已保存的 Key），副本追加到末尾且不设为「使用中」。"""
    return await settings_service.duplicate_provider(
        db, current_user.id, provider_id
    )
