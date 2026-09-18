"""LLM 当前运行模式的响应模型（验证用，无副作用）。"""
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

_CFG = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LLMStatusOut(BaseModel):
    model_config = _CFG

    # real = 走真实模型；mock = 规则兜底
    mode: str = "mock"
    # .env 里的 LLM_ENABLED
    enabled: bool = False
    # 是否已配置 API Key（不回传 Key 本身）
    has_api_key: bool = False
    base_url: str = ""
    model: str = ""
    timeout_seconds: float = 30.0
    min_change_lines: int = 3
    # 一句话说明当前状态，前端可直接展示
    message: str = ""
