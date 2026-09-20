"""LLM 运行模式查询（验证用，无副作用）。

仅观测当前是真实模型还是规则 Mock，以及所用端点/模型，不触发任何网络调用。
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.llm import LLMStatusOut
from app.services import settings as settings_service

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/status", response_model=LLMStatusOut)
async def llm_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """当前账号是真实模型还是规则 Mock，以及所用端点/模型。"""
    cfg, _ = await settings_service.get_llm_setting(db, current_user.id)
    if cfg.ready:
        message = f"已启用真实模型（{cfg.model} @ {cfg.base_url}）"
    else:
        message = "未配置 Key，使用规则 Mock 兜底（可在「设置」页配置模型）"
    return LLMStatusOut(
        mode="real" if cfg.ready else "mock",
        enabled=cfg.enabled,
        has_api_key=bool(cfg.api_key),
        base_url=cfg.base_url,
        model=cfg.model,
        timeout_seconds=cfg.timeout_seconds,
        min_change_lines=cfg.min_change_lines,
        message=message,
    )
