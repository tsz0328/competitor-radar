from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend 根目录（本文件在 backend/app/core/ 下，往上两级就是 backend）
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置：优先读环境变量 / .env 文件，读不到就用这里的默认值。"""

    # ---- 数据库（开发期 SQLite；生产换 MySQL 只改这一行）----
    db_url: str = "sqlite+aiosqlite:///./dev.db"

    # ---- JWT ----
    jwt_secret: str = "dev-secret-change-me"  # ⚠️ 必须在 .env 里覆盖成随机值
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 天

    # ---- CORS：允许哪些前端地址访问后端 ----
    cors_origins: list[str] = ["http://localhost:5173"]

    # ---- 爬虫采集（里程碑 6）----
    # 原始 HTML 落盘目录；库里只存相对路径
    storage_dir: Path = BACKEND_DIR / "storage"
    # 开发期可关掉落盘省空间（关掉后 raw_html_path 恒为 None）
    save_raw_html: bool = True
    crawl_timeout_seconds: float = 15.0
    # 连续失败达到该次数就自动停用该监控源，避免反复无效抓取
    crawl_max_fail_count: int = 5
    # 提取到的正文短于该长度，视为"没抓到有效内容"（多为需要 JS 渲染的页面）
    crawl_min_text_length: int = 30
    # 存进快照的 diff 文本上限，防止整页改写时把库撑爆
    crawl_max_diff_chars: int = 4000
    crawl_user_agent: str = (
        "Mozilla/5.0 (compatible; AICRBot/0.1; +https://github.com/ai-competitor-radar)"
    )

    # ---- LLM 分析（里程碑 7）----
    # 默认关闭：没有 Key 时走规则 Mock，整条链路照样端到端跑通
    llm_enabled: bool = False
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"  # 任何 OpenAI 兼容端点均可
    llm_model: str = "deepseek-chat"
    llm_timeout_seconds: float = 30.0
    # 变化行数低于该值就不生成事件：避免噪声打扰用户，也省 LLM 开销
    llm_min_change_lines: int = 3
    # 送给 LLM 的 diff 最大字符数
    llm_max_diff_chars: int = 3000

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",  # 从 backend/.env 读取
        env_file_encoding="utf-8",
        extra="ignore",  # .env 里有多余变量也不报错
    )


@lru_cache
def get_settings() -> Settings:
    """返回全局单例配置（进程内只构造一次，不会反复读文件）。"""
    return Settings()
