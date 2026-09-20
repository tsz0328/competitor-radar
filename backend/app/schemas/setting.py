"""系统设置（LLM 模型配置）的请求 / 响应模型。"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

_CFG = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def _check_base_url(v: str) -> str:
    """供应商地址必须是 http(s) 绝对地址，避免存进一个没法请求的值。"""
    url = v.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("API 地址需以 http:// 或 https:// 开头")
    return url


class LLMSettingOut(BaseModel):
    """设置页回显：包含脱敏后的 Key，绝不回传明文 Key。"""

    model_config = _CFG

    enabled: bool = False
    # 是否已配置 API Key
    has_api_key: bool = False
    # 脱敏预览，如 sk-****abcd
    api_key_preview: str = ""
    base_url: str = ""
    model: str = ""
    timeout_seconds: float = 30.0
    min_change_lines: int = 3
    # real = 走真实模型；mock = 规则兜底
    mode: str = "mock"
    # database = 来自设置页保存；env = 尚未保存，读的是 .env 默认值
    source: str = "env"
    # 一句话状态说明，前端直接展示
    message: str = ""


class LLMSettingUpdate(BaseModel):
    """保存设置。

    api_key 的语义：
    - 省略（None）→ 保持不变
    - 空串 ""    → 清除已保存的 Key
    - 有值       → 覆盖
    clear_api_key=true 时无条件清除（前端点"清除 Key"时用）。
    """

    model_config = _CFG

    enabled: bool | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None
    model: str | None = None
    timeout_seconds: float | None = Field(default=None, ge=3, le=300)
    min_change_lines: int | None = Field(default=None, ge=1, le=100)


class LLMProviderOut(BaseModel):
    """供应商列表项：Key 只回传脱敏预览。"""

    model_config = _CFG

    id: int
    name: str = ""
    base_url: str = ""
    model: str = ""
    has_api_key: bool = False
    api_key_preview: str = ""
    # 运行时正在使用这一条
    is_active: bool = False
    # 已缓存的模型数量。完整列表走 /llm/providers/{id}/models 按需取，
    # 避免大列表在每次列表请求里全量传输
    models_count: int = 0


class LLMModelsOut(BaseModel):
    """某条供应商已缓存的完整模型列表（编辑时按需获取）。"""

    model_config = _CFG

    models: list[str] = Field(default_factory=list)


class LLMProviderCreate(BaseModel):
    """添加供应商：地址 / 模型必填，Key 必填（否则无法走真实模型）。"""

    model_config = _CFG

    name: str | None = Field(default=None, max_length=80)
    base_url: str = Field(..., min_length=1, max_length=255)
    model: str = Field(..., min_length=1, max_length=120)
    api_key: str = Field(..., min_length=1, max_length=500)
    # 添加前已从上游拉到的模型列表（可选）
    models: list[str] | None = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: str) -> str:
        return _check_base_url(v)


class LLMProviderUpdate(BaseModel):
    """编辑供应商：字段均可省略只改传了的；api_key 语义同 LLMSettingUpdate。"""

    model_config = _CFG

    name: str | None = Field(default=None, max_length=80)
    base_url: str | None = Field(default=None, min_length=1, max_length=255)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    clear_api_key: bool = False
    # 省略 = 保持不变；传了就覆盖（用于保存本次新拉到的模型列表）
    models: list[str] | None = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: str | None) -> str | None:
        return _check_base_url(v) if v is not None else None


class LLMProviderReorder(BaseModel):
    """拖动排序：按期望顺序传一组供应商 id。"""

    model_config = _CFG

    ids: list[int] = Field(..., min_length=1)


class LLMTestRequest(BaseModel):
    """测试连接：优先用请求里的值，缺省则用已保存/环境里的值。

    provider_id：测试「已保存的供应商」时传入——它的 Key 前端拿不到（脱敏），
    由后端自己取已存 Key 来测。
    """

    model_config = _CFG

    provider_id: int | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    timeout_seconds: float | None = Field(default=None, ge=3, le=300)


class LLMTestResult(BaseModel):
    model_config = _CFG

    ok: bool
    message: str
    model: str = ""
    latency_ms: int = 0


class LLMApiKeyOut(BaseModel):
    """已保存 API Key 的明文回显：仅登录用户、且仅在编辑某条供应商时按需获取。"""

    model_config = _CFG

    api_key: str = ""


class LLMFetchModelsRequest(BaseModel):
    """从上游供应商拉取模型列表：优先用已保存供应商的地址/Key（前端拿不到明文）。"""

    model_config = _CFG

    provider_id: int | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout_seconds: float | None = Field(default=None, ge=3, le=300)


class LLMFetchModelsResult(BaseModel):
    """拉取结果：ok=false 时 models 为空，message 给可读原因。"""

    model_config = _CFG

    ok: bool = False
    models: list[str] = Field(default_factory=list)
    message: str = ""
