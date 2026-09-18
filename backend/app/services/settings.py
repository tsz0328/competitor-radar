"""设置服务：读写系统设置、同步到运行时配置、测试模型连通性。

三层职责：
- 展示：get_llm_setting（只读，不改变运行时状态）
- 保存：save_llm_setting（写库 + 刷新运行时，立即生效）
- 测试：test_llm_connection（用界面填的值发一次最小请求，验证地址/Key/模型）
"""
import logging
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ERR_LLM_CONFIG_INVALID, BusinessError
from app.core.runtime_config import LLMConfig, env_llm_config, set_llm_config
from app.models.setting import SETTINGS_ID, AppSetting
from app.schemas.setting import LLMTestRequest, LLMTestResult

logger = logging.getLogger(__name__)


def mask_api_key(key: str) -> str:
    """脱敏：只露头尾，中间用 ****；空 Key 返回空串。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:3]}****{key[-4:]}"


def _to_config(row: AppSetting) -> LLMConfig:
    return LLMConfig(
        enabled=row.llm_enabled,
        api_key=row.llm_api_key or "",
        base_url=row.llm_base_url or "",
        model=row.llm_model or "",
        timeout_seconds=row.llm_timeout_seconds,
        min_change_lines=row.llm_min_change_lines,
    )


async def _get_row(db: AsyncSession) -> AppSetting | None:
    return await db.get(AppSetting, SETTINGS_ID)


async def get_llm_setting(db: AsyncSession) -> tuple[LLMConfig, str]:
    """读取当前配置用于展示；数据库无记录时回退 .env。返回 (配置, 来源)。"""
    row = await _get_row(db)
    if row is None:
        return env_llm_config(), "env"
    return _to_config(row), "database"


async def load_llm_config(db: AsyncSession) -> tuple[LLMConfig, str]:
    """启动时调用：把数据库配置加载进运行时（无记录则用 .env）。"""
    cfg, source = await get_llm_setting(db)
    set_llm_config(cfg)
    logger.info(
        "LLM 运行时配置已加载：来源=%s 模式=%s 模型=%s",
        source,
        "real" if cfg.ready else "mock",
        cfg.model or "-",
    )
    return cfg, source


async def save_llm_setting(db: AsyncSession, payload) -> tuple[LLMConfig, str]:
    """保存设置：写库后刷新运行时配置，立即生效。

    首次保存时以 .env 当前值为底，再用界面提交的值覆盖，
    这样"只想改一项"也不会把其它项清空。
    """
    row = await _get_row(db)
    if row is None:
        base = env_llm_config()
        row = AppSetting(
            id=SETTINGS_ID,
            llm_enabled=base.enabled,
            llm_api_key=base.api_key,
            llm_base_url=base.base_url,
            llm_model=base.model,
            llm_timeout_seconds=base.timeout_seconds,
            llm_min_change_lines=base.min_change_lines,
        )
        db.add(row)

    if payload.enabled is not None:
        row.llm_enabled = payload.enabled
    if payload.clear_api_key:
        row.llm_api_key = ""
    elif payload.api_key:
        row.llm_api_key = payload.api_key.strip()
    if payload.base_url is not None:
        row.llm_base_url = payload.base_url.strip()
    if payload.model is not None:
        row.llm_model = payload.model.strip()
    if payload.timeout_seconds is not None:
        row.llm_timeout_seconds = payload.timeout_seconds
    if payload.min_change_lines is not None:
        row.llm_min_change_lines = payload.min_change_lines

    # 启用前必须齐活：宁可明确报错，也不要"开了但一直悄悄走 Mock"
    if row.llm_enabled and not (row.llm_api_key and row.llm_base_url and row.llm_model):
        raise BusinessError(
            ERR_LLM_CONFIG_INVALID,
            "启用 AI 前请先填写完整的 API 地址、模型名称与 API Key",
            400,
        )

    await db.commit()
    await db.refresh(row)

    cfg = _to_config(row)
    set_llm_config(cfg)
    return cfg, "database"


def _extract_error(resp: httpx.Response) -> str:
    """从错误响应里尽量抠出可读信息（各家格式不一，失败就退回截断文本）。"""
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])[:160]
            if data.get("message"):
                return str(data["message"])[:160]
    except Exception:  # noqa: BLE001 - 解析失败无所谓，用文本兜底
        pass
    return (resp.text or "").strip()[:160] or "未知错误"


async def test_llm_connection(db: AsyncSession, payload: LLMTestRequest) -> LLMTestResult:
    """用给定或已保存的配置发一次最小请求，验证连通性（不落库）。"""
    cfg, _ = await get_llm_setting(db)
    base_url = (payload.base_url or cfg.base_url).strip()
    model = (payload.model or cfg.model).strip()
    api_key = (payload.api_key or cfg.api_key).strip()
    timeout = payload.timeout_seconds or cfg.timeout_seconds

    if not base_url:
        return LLMTestResult(ok=False, message="请先填写 API 地址")
    if not model:
        return LLMTestResult(ok=False, message="请先填写模型名称")
    if not api_key:
        return LLMTestResult(ok=False, message="请先填写 API Key")

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return LLMTestResult(
            ok=False,
            message=f"连接失败（HTTP {exc.response.status_code}）：{_extract_error(exc.response)}",
            model=model,
            latency_ms=latency,
        )
    except httpx.TimeoutException:
        latency = int((time.perf_counter() - started) * 1000)
        return LLMTestResult(
            ok=False, message=f"连接超时（>{timeout:g}s）", model=model, latency_ms=latency
        )
    except Exception as exc:  # noqa: BLE001 - 网络/解析等杂项异常统一收敛
        latency = int((time.perf_counter() - started) * 1000)
        return LLMTestResult(
            ok=False, message=f"连接失败：{type(exc).__name__}", model=model, latency_ms=latency
        )

    latency = int((time.perf_counter() - started) * 1000)
    return LLMTestResult(
        ok=True, message=f"连接成功，模型可用（耗时 {latency} ms）", model=model, latency_ms=latency
    )
