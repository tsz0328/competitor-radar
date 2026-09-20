"""LLM 运行时配置的数据结构。

这只是一个**不可变的值对象**：运行时不保存任何"当前生效配置"的全局状态，
而是每次按用户解析（见 services/settings.py 的 get_user_llm_config）。

为什么改成按用户解析：
- AI 配置（开关 / 供应商 / Key）按用户隔离、存在数据库里；
- 抓取、趋势、周报等调用方都能拿到归属用户，直接解析出该用户自己的配置即可，
  既不需要进程级单例，也不会有"一个用户改配置影响所有人"的问题。
"""
from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class LLMConfig:
    """某个用户当前生效的 LLM 配置。"""

    enabled: bool
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    min_change_lines: int

    @property
    def ready(self) -> bool:
        """是否具备走真实模型的最小条件（开关打开 + 地址/模型/Key 齐全）。"""
        return bool(self.enabled and self.api_key and self.base_url and self.model)


def env_llm_config() -> LLMConfig:
    """从 .env / 环境变量构造配置（用户在数据库里还没有记录时的兜底）。"""
    s = get_settings()
    return LLMConfig(
        enabled=s.llm_enabled,
        api_key=s.llm_api_key,
        base_url=s.llm_base_url,
        model=s.llm_model,
        timeout_seconds=s.llm_timeout_seconds,
        min_change_lines=s.llm_min_change_lines,
    )
