"""运行时配置：把"可被界面修改"的配置放进进程内存。

为什么需要它：
- 老的 LLMClient 直接读 .env（lru_cache 单例，构造时只读一次），
  界面改了配置必须重启进程才生效。
- 这里维护一份进程内"当前生效配置"：启动时从数据库加载一次，
  界面保存后再刷新一次；LLM 调用读取它即可"改完即生效"，无需重启。

只维护内存状态，不碰数据库（数据库读写放在 services/settings.py）。
"""
from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class LLMConfig:
    """当前生效的 LLM 配置。"""

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
    """从 .env / 环境变量构造配置（数据库还没有记录时的兜底）。"""
    s = get_settings()
    return LLMConfig(
        enabled=s.llm_enabled,
        api_key=s.llm_api_key,
        base_url=s.llm_base_url,
        model=s.llm_model,
        timeout_seconds=s.llm_timeout_seconds,
        min_change_lines=s.llm_min_change_lines,
    )


# 进程内当前配置；None 表示尚未初始化，首次读取时用 .env 兜底
_current: LLMConfig | None = None


def get_llm_config() -> LLMConfig:
    global _current
    if _current is None:
        _current = env_llm_config()
    return _current


def set_llm_config(cfg: LLMConfig) -> None:
    global _current
    _current = cfg
