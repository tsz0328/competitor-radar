"""系统设置（LLM 模型配置）的请求 / 响应模型。"""
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CFG = ConfigDict(alias_generator=to_camel, populate_by_name=True)


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


class LLMTestRequest(BaseModel):
    """测试连接：优先用请求里的值，缺省则用已保存/环境里的值。"""

    model_config = _CFG

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
