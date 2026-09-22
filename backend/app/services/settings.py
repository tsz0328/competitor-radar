"""设置服务：读写「按用户隔离」的 AI 配置、测试模型连通性。

数据模型（多供应商、按用户隔离）：
- app_settings：每个用户一行，只存开关（启用 AI / 超时 / 最小变更行数）；
- llm_providers：每个用户若干个模型服务商（地址 / 模型 / Key），其中一条「使用中」。
运行时配置 = **该用户**的开关 + 该用户「使用中」的供应商（get_user_llm_config）。
用户没有任何记录时回退 .env 默认值；旧版「app_settings 单行存凭证」的数据会在
首次访问时迁移成该用户的一条使用中供应商（见 _ensure_legacy_provider）。

三层职责：
- 展示：get_llm_setting / list_providers（只读）
- 保存：save_llm_setting 与供应商 CRUD（写库即生效，无需重启）
- 测试：test_llm_connection（用界面填的值发一次最小请求，验证地址/Key/模型）

所有对外函数都要求传 user_id：查询一律带 user_id 条件，改 / 删前先校验归属，
不是自己的记录等同「不存在」。
"""
import json
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ERR_LLM_CONFIG_INVALID,
    BusinessError,
)
from app.core.runtime_config import LLMConfig, env_llm_config
from app.models.llm_provider import LlmProvider
from app.models.setting import AppSetting
from app.schemas.setting import (
    LLMFetchModelsRequest,
    LLMFetchModelsResult,
    LLMProviderCreate,
    LLMProviderOut,
    LLMProviderUpdate,
    LLMTestRequest,
    LLMTestResult,
)

logger = logging.getLogger(__name__)

# 供应商不存在 / 操作对象无效时的统一提示
_ERR_PROVIDER_NOT_FOUND = "供应商不存在或已被删除，请刷新后重试或重新添加"


def mask_api_key(key: str) -> str:
    """脱敏：只露头尾，中间用 ****；空 Key 返回空串。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:3]}****{key[-4:]}"


# ---------- 内部工具 ----------


async def _get_row(db: AsyncSession, user_id: int) -> AppSetting | None:
    """该用户的设置行（一人一行）。"""
    res = await db.execute(select(AppSetting).where(AppSetting.user_id == user_id))
    return res.scalars().first()


async def _active_provider(db: AsyncSession, user_id: int) -> LlmProvider | None:
    """该用户当前「使用中」的供应商（历史脏数据允许多条时取最新一条）。"""
    res = await db.execute(
        select(LlmProvider)
        .where(LlmProvider.user_id == user_id, LlmProvider.is_active.is_(True))
        .order_by(LlmProvider.id.desc())
        .limit(1)
    )
    return res.scalars().first()


async def _get_owned_provider(
    db: AsyncSession, user_id: int, provider_id: int
) -> LlmProvider:
    """取某条供应商并校验归属：不是自己的等同「不存在」（避免越权读写）。"""
    res = await db.execute(
        select(LlmProvider).where(
            LlmProvider.id == provider_id, LlmProvider.user_id == user_id
        )
    )
    prov = res.scalars().first()
    if prov is None:
        raise BusinessError(ERR_LLM_CONFIG_INVALID, _ERR_PROVIDER_NOT_FOUND, 404)
    return prov


def _compose(row: AppSetting | None, prov: LlmProvider | None) -> LLMConfig:
    """该用户的开关 + 使用中的供应商 → 运行时配置。两者皆空时回退 .env。"""
    if row is None and prov is None:
        return env_llm_config()
    env = env_llm_config()
    return LLMConfig(
        enabled=row.llm_enabled if row else False,
        api_key=prov.api_key if prov else "",
        base_url=prov.base_url if prov else "",
        model=prov.model if prov else "",
        timeout_seconds=row.llm_timeout_seconds if row else env.timeout_seconds,
        min_change_lines=row.llm_min_change_lines if row else env.min_change_lines,
    )


async def _ensure_legacy_provider(db: AsyncSession, user_id: int) -> None:
    """旧数据迁移：该用户还没有供应商、但其设置行里存有历史凭证时，
    把它拷成一条「使用中」的供应商，保证升级后配置不丢（幂等）。"""
    count = await db.scalar(
        select(func.count())
        .select_from(LlmProvider)
        .where(LlmProvider.user_id == user_id)
    )
    if count:
        return
    row = await _get_row(db, user_id)
    if row is None or not (row.llm_base_url and row.llm_model):
        return
    db.add(
        LlmProvider(
            user_id=user_id,
            name="已保存配置",
            base_url=row.llm_base_url,
            model=row.llm_model,
            api_key=row.llm_api_key or "",
            is_active=True,
        )
    )
    await db.commit()
    logger.info("已把旧 LLM 配置迁移为 user=%s 的一条供应商记录", user_id)


async def get_user_llm_config(db: AsyncSession, user_id: int) -> LLMConfig:
    """解析某个用户当前生效的 LLM 配置（该用户的开关 + 使用中的供应商）。

    用户既没有设置行也没有供应商时回退 .env 默认值（自托管单用户场景友好）。
    """
    await _ensure_legacy_provider(db, user_id)
    return _compose(await _get_row(db, user_id), await _active_provider(db, user_id))


async def _propagate_models(
    db: AsyncSession, user_id: int, base_url: str, models: str, exclude_id: int | None
) -> None:
    """同一用户、同一地址的供应商共用一份模型列表：把本次保存的列表同步给它们。

    否则会出现「A、B 同地址，编辑 A 拉到了列表、编辑 B 却是空的」这种割裂。
    只在本用户范围内同步，绝不跨用户。
    """
    res = await db.execute(
        select(LlmProvider).where(
            LlmProvider.user_id == user_id, LlmProvider.base_url == base_url
        )
    )
    for p in res.scalars().all():
        if exclude_id is not None and p.id == exclude_id:
            continue
        p.models = models


async def get_provider_models(
    db: AsyncSession, user_id: int, provider_id: int
) -> list[str]:
    """读取某条供应商已缓存的完整模型列表（编辑弹窗按需获取）。"""
    prov = await _get_owned_provider(db, user_id, provider_id)
    return _parse_models(prov.models)


async def get_provider_api_key(db: AsyncSession, user_id: int, provider_id: int) -> str:
    """读取某条供应商已保存的 API Key 明文（仅供编辑弹窗回显 / 修改）。

    只有该供应商的归属用户本人能取到自己的明文 Key。
    """
    prov = await _get_owned_provider(db, user_id, provider_id)
    return prov.api_key


def _parse_models(raw: str | None) -> list[str]:
    """把库里的 JSON 数组字符串解析成字符串列表（脏数据一律当空）。"""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [m for m in data if isinstance(m, str)]


def _dump_models(models: list[str] | None) -> str:
    """模型列表存成 JSON 数组字符串（空列表存空串，便于与「未获取过」区分）。"""
    if not models:
        return ""
    return json.dumps(models, ensure_ascii=False)


def _extract_model_ids(data: object) -> list[str]:
    """从上游 /models 的返回里抠出模型 id，尽量兼容各家格式：

    - OpenAI 风格：{"data": [{"id": "gpt-4"}, ...]}
    - Ollama 风格：{"models": [{"name": "llama3"}, ...]}
    - 直接是数组：["m1", {"id": "m2"}]

    条目取 id / name / model 里第一个非空字符串；去重并保持原顺序。
    """
    if isinstance(data, dict):
        arr = data.get("data")
        if not isinstance(arr, list):
            arr = data.get("models")
        if not isinstance(arr, list):
            arr = []
    elif isinstance(data, list):
        arr = data
    else:
        arr = []

    out: list[str] = []
    for item in arr:
        if isinstance(item, str):
            mid: object = item
        elif isinstance(item, dict):
            mid = item.get("id") or item.get("name") or item.get("model")
        else:
            mid = None
        if isinstance(mid, str) and mid and mid not in out:
            out.append(mid)
    return out


# 明显不支持 /chat/completions 的模型（文生图/图生图/嵌入/语音/重排/审核等）的 id 特征。
# 上游 /models 没有标准的「能力」字段，只能按 id 启发式识别；
# 仅用于拉取列表的过滤与前端手填提示，不做硬校验（手填可绕过，靠「测试连接」兜底）。
_NON_CHAT_MODEL_PATTERNS: tuple[str, ...] = (
    "dall-e",            # 文生图（OpenAI）
    "gpt-image",         # 图生图（OpenAI）
    "wanx",              # 通义万相 文生图
    "cogview",           # 智谱 文生图
    "seedream",          # 即梦/豆包 文生图
    "stable-diffusion",  # 扩散文生图
    "sdxl",              # SDXL 文生图
    "flux",              # FLUX 文生图
    "embedding",         # 嵌入（text-embedding-* / embed-*）
    "bge-",              # BGE 嵌入
    "tts",               # 语音合成
    "whisper",           # 语音识别
    "transcribe",        # 语音转写（gpt-4o-transcribe 等）
    "realtime",          # 实时语音（gpt-4o-realtime）
    "rerank",            # 重排（gte-rerank 等）
    "moderation",        # 内容审核
    "video",             # 视频生成
    "sora",              # 视频生成（OpenAI）
    "kling",             # 可灵 视频生成
)


def looks_non_chat_model(model_id: str) -> bool:
    """按 id 启发式判断模型是否明显不支持对话补全（文生图/嵌入/语音等）。"""
    mid = (model_id or "").strip().lower()
    return any(p in mid for p in _NON_CHAT_MODEL_PATTERNS)


def _provider_out(p: LlmProvider) -> LLMProviderOut:
    return LLMProviderOut(
        id=p.id,
        name=p.name,
        base_url=p.base_url,
        model=p.model,
        has_api_key=bool(p.api_key),
        api_key_preview=mask_api_key(p.api_key),
        is_active=p.is_active,
        # 只回数量：完整列表用 get_provider_models 按需取，避免大列表全量传输
        models_count=len(_parse_models(p.models)),
        test_status=p.last_test_status,
        last_test_at=p.last_test_at,
    )


# ---------- 展示 / 全局设置（按用户） ----------


async def get_llm_setting(db: AsyncSession, user_id: int) -> tuple[LLMConfig, str]:
    """读取该用户当前生效配置用于展示（Key 脱敏在外层处理）。返回 (配置, 来源)。"""
    await _ensure_legacy_provider(db, user_id)
    row = await _get_row(db, user_id)
    prov = await _active_provider(db, user_id)
    if row is None and prov is None:
        return env_llm_config(), "env"
    return _compose(row, prov), "database"


async def save_llm_setting(
    db: AsyncSession, user_id: int, payload
) -> tuple[LLMConfig, str]:
    """保存该用户的全局设置：写库即生效（运行时按用户实时解析，无需刷新全局状态）。

    payload 里的 base_url / model / api_key 是旧版单配置接口的兼容入参：
    会落到该用户「使用中」的供应商上（没有则新建一条并启用）。
    """
    row = await _get_row(db, user_id)
    if row is None:
        base = env_llm_config()
        row = AppSetting(
            user_id=user_id,
            llm_enabled=base.enabled,
            llm_api_key="",
            llm_base_url="",
            llm_model="",
            llm_timeout_seconds=base.timeout_seconds,
            llm_min_change_lines=base.min_change_lines,
        )
        db.add(row)

    if payload.enabled is not None:
        row.llm_enabled = payload.enabled
    if payload.timeout_seconds is not None:
        row.llm_timeout_seconds = payload.timeout_seconds
    if payload.min_change_lines is not None:
        row.llm_min_change_lines = payload.min_change_lines

    await _ensure_legacy_provider(db, user_id)
    prov = await _active_provider(db, user_id)

    # 兼容旧客户端：凭证类字段改到「使用中」的供应商上
    touches_credentials = (
        payload.base_url is not None
        or payload.model is not None
        or payload.api_key is not None
        or payload.clear_api_key
    )
    if touches_credentials:
        if prov is None:
            if not (payload.base_url and payload.model and payload.api_key):
                raise BusinessError(
                    ERR_LLM_CONFIG_INVALID,
                    "请先在「添加供应商」中填写 API 地址、模型名称与 API Key",
                    400,
                )
            prov = LlmProvider(
                user_id=user_id,
                base_url=payload.base_url.strip(),
                model=payload.model.strip(),
                api_key=payload.api_key.strip(),
                is_active=True,
            )
            db.add(prov)
        else:
            if payload.base_url is not None:
                prov.base_url = payload.base_url.strip()
            if payload.model is not None:
                prov.model = payload.model.strip()
            if payload.clear_api_key:
                prov.api_key = ""
            elif payload.api_key:
                prov.api_key = payload.api_key.strip()

    # 启用前必须齐活：宁可明确报错，也不要"开了但一直悄悄走 Mock"
    if row.llm_enabled and not (prov and prov.api_key and prov.base_url and prov.model):
        raise BusinessError(
            ERR_LLM_CONFIG_INVALID,
            "启用 AI 前请先添加完整的供应商（API 地址、模型名称与 API Key）",
            400,
        )

    await db.commit()
    await db.refresh(row)

    return _compose(row, prov), "database"


# ---------- 供应商 CRUD（按用户） ----------


async def list_providers(db: AsyncSession, user_id: int) -> list[LLMProviderOut]:
    """该用户已配置的供应商（按手动排序 sort_order 升序展示）。"""
    await _ensure_legacy_provider(db, user_id)
    res = await db.execute(
        select(LlmProvider)
        .where(LlmProvider.user_id == user_id)
        .order_by(LlmProvider.sort_order.asc(), LlmProvider.id.asc())
    )
    return [_provider_out(p) for p in res.scalars().all()]


async def create_provider(
    db: AsyncSession, user_id: int, payload: LLMProviderCreate
) -> LLMProviderOut:
    """添加供应商；该用户的第一条自动设为「使用中」，追加到列表末尾。"""
    count = await db.scalar(
        select(func.count())
        .select_from(LlmProvider)
        .where(LlmProvider.user_id == user_id)
    )
    max_order = await db.scalar(
        select(func.coalesce(func.max(LlmProvider.sort_order), 0)).where(
            LlmProvider.user_id == user_id
        )
    )
    prov = LlmProvider(
        user_id=user_id,
        name=(payload.name or "").strip(),
        base_url=payload.base_url.strip(),
        model=payload.model.strip(),
        api_key=payload.api_key.strip(),
        # 添加前若已从上游拉到模型列表，一并存下（编辑时可直接回填）
        models=_dump_models(payload.models),
        is_active=not count,
        sort_order=(max_order or 0) + 1,
    )
    db.add(prov)
    await db.commit()
    await db.refresh(prov)
    # 同一用户、同地址的其它供应商共用一份模型列表
    if prov.models:
        await _propagate_models(
            db, user_id, prov.base_url, prov.models, exclude_id=prov.id
        )
        await db.commit()
    return _provider_out(prov)


async def reorder_providers(db: AsyncSession, user_id: int, ids: list[int]) -> None:
    """按传入顺序重排该用户的供应商（仅改展示顺序，不影响运行时选中的那条）。"""
    res = await db.execute(
        select(LlmProvider).where(
            LlmProvider.user_id == user_id, LlmProvider.id.in_(ids)
        )
    )
    objs = {p.id: p for p in res.scalars().all()}
    if len(objs) != len(ids):
        raise BusinessError(ERR_LLM_CONFIG_INVALID, "供应商不存在或已被删除，请刷新后重试或重新添加", 404)
    for i, pid in enumerate(ids):
        objs[pid].sort_order = i
    await db.commit()


async def update_provider(
    db: AsyncSession, user_id: int, provider_id: int, payload: LLMProviderUpdate
) -> LLMProviderOut:
    """编辑该用户自己的供应商（改「使用中」的那条即刻影响该用户的 AI 行为）。"""
    prov = await _get_owned_provider(db, user_id, provider_id)

    if payload.name is not None:
        prov.name = payload.name.strip()
    if payload.base_url is not None:
        new_url = payload.base_url.strip()
        # 地址变了：旧地址获取到的模型列表不再适用；本次没显式带新列表就先清掉，
        # 避免出现「新地址配着旧地址的模型列表」
        if new_url != prov.base_url and payload.models is None:
            prov.models = ""
        prov.base_url = new_url
    if payload.model is not None:
        prov.model = payload.model.strip()
    if payload.models is not None:
        # 传了就覆盖（保存本次新拉到的模型列表），并同步给同地址的供应商
        prov.models = _dump_models(payload.models)
        await _propagate_models(
            db, user_id, prov.base_url, prov.models, exclude_id=prov.id
        )
    if payload.clear_api_key:
        prov.api_key = ""
    elif payload.api_key:
        prov.api_key = payload.api_key.strip()

    # 配置被改过：旧测试结果作废，回到「未测试」，避免标签显示过时状态
    if any(
        x is not None
        for x in (payload.name, payload.base_url, payload.model, payload.api_key)
    ) or payload.clear_api_key:
        prov.last_test_status = "none"
        prov.last_test_at = None

    if prov.is_active and not (prov.api_key and prov.base_url and prov.model):
        raise BusinessError(
            ERR_LLM_CONFIG_INVALID,
            "使用中的供应商必须保留完整的地址、模型与 API Key（可先切换到其它供应商）",
            400,
        )

    await db.commit()
    await db.refresh(prov)
    return _provider_out(prov)


async def delete_provider(db: AsyncSession, user_id: int, provider_id: int) -> None:
    """删除该用户的供应商；删的是「使用中」的则自动顶上最新一条，否则回退 Mock。"""
    prov = await _get_owned_provider(db, user_id, provider_id)

    was_active = prov.is_active
    await db.delete(prov)
    await db.commit()

    if was_active:
        res = await db.execute(
            select(LlmProvider)
            .where(LlmProvider.user_id == user_id)
            .order_by(LlmProvider.id.desc())
            .limit(1)
        )
        nxt = res.scalars().first()
        if nxt is not None:
            nxt.is_active = True
            await db.commit()


async def activate_provider(
    db: AsyncSession, user_id: int, provider_id: int
) -> LLMProviderOut:
    """切换该用户「使用中」的供应商，其后续 AI 调用改用它的地址 / 模型 / Key。"""
    prov = await _get_owned_provider(db, user_id, provider_id)

    res = await db.execute(select(LlmProvider).where(LlmProvider.user_id == user_id))
    for p in res.scalars().all():
        p.is_active = p.id == provider_id
    await db.commit()
    await db.refresh(prov)
    return _provider_out(prov)


async def duplicate_provider(
    db: AsyncSession, user_id: int, provider_id: int
) -> LLMProviderOut:
    """复制供应商：连同已保存的 Key 一起拷贝（Key 前端拿不到明文）。

    副本追加到列表末尾、默认不设为「使用中」，避免影响正在跑的抓取。
    """
    prov = await _get_owned_provider(db, user_id, provider_id)

    max_order = await db.scalar(
        select(func.coalesce(func.max(LlmProvider.sort_order), 0)).where(
            LlmProvider.user_id == user_id
        )
    )
    # 超长原名要截断，但不能把「副本」后缀一起截掉
    suffix = " 副本"
    base_name = prov.name or "自定义"
    copy_name = (
        base_name[: 80 - len(suffix)] + suffix
        if len(base_name) + len(suffix) > 80
        else base_name + suffix
    )
    copy = LlmProvider(
        user_id=user_id,
        name=copy_name,
        base_url=prov.base_url,
        model=prov.model,
        api_key=prov.api_key,
        models=prov.models,
        is_active=False,
        sort_order=(max_order or 0) + 1,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return _provider_out(copy)


# ---------- 连通性测试 ----------


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


def _friendly_fetch_error(status_code: int, raw: str) -> str:
    """把拉取 /models 的 HTTP 错误转成可读提示：识别常见 Key / 地址 / 限流问题。"""
    lowered = (raw or "").lower()
    if status_code in (401, 403):
        if any(
            kw in lowered
            for kw in (
                "key",
                "credential",
                "token",
                "auth",
                "denied",
                "forbidden",
                "invalid",
                "unauthorized",
            )
        ):
            return f"API Key 无效或已过期，请检查后重试（HTTP {status_code}：{raw}）"
        return f"无权限访问该接口（HTTP {status_code}），请确认 API Key 是否正确"
    if status_code == 404:
        return "API 地址或接口路径不存在（HTTP 404），请确认是否为 OpenAI 兼容接口"
    if status_code == 429:
        return "请求过于频繁，请稍后再试（HTTP 429）"
    if status_code >= 500:
        return f"上游服务异常（HTTP {status_code}），请稍后再试"
    return f"获取失败（HTTP {status_code}）：{raw}"


def _friendly_connection_error(exc: Exception) -> str:
    """把连接类异常翻译成带操作引导的中文提示（避免把异常类名直接丢给用户）。"""
    if isinstance(exc, httpx.ConnectError):
        return "无法连接到 API 地址，请检查地址是否正确、网络是否可达"
    if isinstance(exc, httpx.UnsupportedProtocol):
        return "API 地址协议不受支持，请以 http:// 或 https:// 开头"
    if isinstance(exc, httpx.InvalidURL):
        return "API 地址格式不正确，请以 http:// 或 https:// 开头"
    if isinstance(exc, ValueError):  # 含 json.JSONDecodeError：上游返回的不是合法 JSON
        return "上游返回内容无法解析，可能不是 OpenAI 兼容接口，请检查 API 地址"
    return "连接失败，请检查 API 地址、Key 与网络后重试"


async def test_llm_connection(
    db: AsyncSession, user_id: int, payload: LLMTestRequest
) -> LLMTestResult:
    """用给定或已保存的配置发一次最小请求，验证连通性（不落库）。

    payload.provider_id 指向**自己**已保存的供应商时，缺省值取它的地址 / 模型 / Key
    （Key 前端拿不到，必须由后端自己取）；别人的供应商等同不存在。
    """
    prov: LlmProvider | None = None

    async def _save_test(ok: bool) -> None:
        """把测试结果落到已保存的供应商上（未保存的草稿不落库）。"""
        if prov is None:
            return
        prov.last_test_status = "ok" if ok else "fail"
        prov.last_test_at = datetime.now(timezone.utc)
        await db.commit()

    if payload.provider_id is not None:
        prov = await _get_owned_provider(db, user_id, payload.provider_id)
        saved = LLMConfig(
            enabled=True,
            api_key=prov.api_key,
            base_url=prov.base_url,
            model=prov.model,
            timeout_seconds=30.0,
            min_change_lines=3,
        )
    else:
        saved, _ = await get_llm_setting(db, user_id)

    base_url = (payload.base_url or saved.base_url).strip()
    model = (payload.model or saved.model).strip()
    api_key = (payload.api_key or saved.api_key).strip()
    timeout = payload.timeout_seconds or saved.timeout_seconds

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
        await _save_test(False)
        return LLMTestResult(
            ok=False,
            message=_friendly_fetch_error(
                exc.response.status_code, _extract_error(exc.response)
            ),
            model=model,
            latency_ms=latency,
        )
    except httpx.TimeoutException:
        latency = int((time.perf_counter() - started) * 1000)
        await _save_test(False)
        return LLMTestResult(
            ok=False,
            message=f"连接超时（>{timeout:g}s），请检查网络后重试，或在设置中调大超时时间",
            model=model,
            latency_ms=latency,
        )
    except Exception as exc:  # noqa: BLE001 - 网络/解析等杂项异常统一收敛
        latency = int((time.perf_counter() - started) * 1000)
        await _save_test(False)
        return LLMTestResult(
            ok=False,
            message=_friendly_connection_error(exc),
            model=model,
            latency_ms=latency,
        )

    latency = int((time.perf_counter() - started) * 1000)
    await _save_test(True)
    return LLMTestResult(
        ok=True, message=f"连接成功，模型可用（耗时 {latency} ms）", model=model, latency_ms=latency
    )


async def fetch_provider_models(
    db: AsyncSession, user_id: int, payload: LLMFetchModelsRequest
) -> LLMFetchModelsResult:
    """从上游供应商拉取模型列表（OpenAI 兼容的 GET /models）。

    优先用自己已保存供应商的地址 / Key；新供应商则用界面填的。

    只读不写：拉到的列表不落库，由前端暂存、点「保存」时才随供应商一起提交，
    这样用户放弃修改（关掉弹窗）不会被这次拉取悄悄改掉配置。
    """
    prov: LlmProvider | None = None
    if payload.provider_id is not None:
        prov = await _get_owned_provider(db, user_id, payload.provider_id)
        base_url = prov.base_url
        api_key = prov.api_key
    else:
        base_url = (payload.base_url or "").strip()
        api_key = (payload.api_key or "").strip()

    if not base_url:
        return LLMFetchModelsResult(ok=False, models=[], message="请先填写 API 地址")
    if not api_key:
        return LLMFetchModelsResult(ok=False, models=[], message="请先填写 API Key")

    timeout = payload.timeout_seconds or 15.0
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        return LLMFetchModelsResult(
            ok=False,
            models=[],
            message=_friendly_fetch_error(
                exc.response.status_code, _extract_error(exc.response)
            ),
        )
    except httpx.TimeoutException:
        return LLMFetchModelsResult(
            ok=False, models=[], message=f"获取超时（>{timeout:g}s），请检查网络后重试"
        )
    except Exception as exc:  # noqa: BLE001 - 网络/解析等杂项异常统一收敛
        return LLMFetchModelsResult(
            ok=False, models=[], message=_friendly_connection_error(exc)
        )

    models = _extract_model_ids(data)
    if not models:
        return LLMFetchModelsResult(
            ok=False,
            models=[],
            message="上游未返回任何模型，请确认地址是否为 OpenAI 兼容接口",
        )
    chat_models = [m for m in models if not looks_non_chat_model(m)]
    filtered = [m for m in models if looks_non_chat_model(m)]
    if not chat_models:
        return LLMFetchModelsResult(
            ok=False,
            models=[],
            filtered_models=filtered,
            message="上游返回的均为非对话模型（文生图/嵌入/语音等），本系统需要支持对话补全的模型",
        )
    message = f"已获取 {len(chat_models)} 个对话模型"
    if filtered:
        message += f"，已过滤 {len(filtered)} 个非对话模型"
    return LLMFetchModelsResult(
        ok=True, models=chat_models, filtered_models=filtered, message=message
    )
