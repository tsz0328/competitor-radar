from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend 根目录（本文件在 backend/app/core/ 下，往上两级就是 backend）
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置：优先读环境变量 / .env 文件，读不到就用这里的默认值。"""

    # ---- 数据库（开发期 SQLite；生产换 MySQL 只改这一行）----
    db_url: str = "sqlite+aiosqlite:///./dev.db"
    # ---- 通用运行参数 ----
    # 业务时区：事件日期、通知未读窗口、周报自然周均按此时区口径计算
    app_timezone: str = "Asia/Shanghai"
    # 默认拦截内网 / 回环 / 链路本地地址，防止伪造 URL 让服务端发起 SSRF 请求
    allow_private_network_urls: bool = False
    # 通知中心只把最近 N 个自然日的高优事件计为未读，全部已读也只写这个窗口
    notification_window_days: int = 90
    # 启动时自动建表：开发期方便；生产置为 false，改由 `alembic upgrade head` 建表，
    # 避免应用"越权"修改已上线库的结构。
    db_auto_create: bool = True

    # ---- 缓存（里程碑 3.4 落地 / 11 接入 Redis）----
    # memory = 进程内（开发）；redis = 多副本共享（生产）
    cache_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"
    # 分布式调度锁的持有时长（秒），需大于单轮抓取耗时
    scheduler_lock_ttl_seconds: int = 600

    # ---- JWT ----
    jwt_secret: str = "dev-secret-change-me"  # ⚠️ 必须在 .env 里覆盖成随机值
    jwt_algorithm: str = "HS256"
    # ---- 初始管理员 ----
    # 默认关闭，避免固定弱密码账号被直接种进生产环境
    bootstrap_admin_enabled: bool = False
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""
    # 初始管理员邮箱：email 已是登录标识且必填（同 username 值），种入时必须一起给
    bootstrap_admin_email: str = ""
    # 兜底时长：调用方没显式指定时用它（登录接口会按「记住我」传具体值）
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 天
    # 登录时按「记住我」二选一：
    #   勾选 → 长期令牌，关掉浏览器再打开仍是登录态
    #   不勾 → 会话令牌，前端只存 sessionStorage，这里再给一个短命上限兜底
    remember_token_expire_minutes: int = 60 * 24 * 30  # 30 天
    session_token_expire_minutes: int = 60 * 24  # 24 小时

    # ---- CORS：允许哪些前端地址访问后端 ----
    cors_origins: list[str] = ["http://localhost:5173"]

    # ---- 爬虫采集（里程碑 6）----
    # 原始 HTML 落盘目录；库里只存相对路径
    storage_dir: Path = BACKEND_DIR / "storage"
    # 开发期可关掉落盘省空间（关掉后 raw_html_path 恒为 None）
    save_raw_html: bool = True
    crawl_timeout_seconds: float = 15.0
    # 新增/编辑竞品时「校验网址可达」用的更短超时：逐个页面检测，别卡太久
    check_url_timeout_seconds: float = 12.0
    # 连续失败达到该次数就自动停用该监控源，避免反复无效抓取
    crawl_max_fail_count: int = 5
    # 单个监控源抓取的互斥锁 TTL：防止手动触发和定时任务同时抓同一个页面
    crawl_source_lock_ttl_seconds: int = 180
    # 抓取 429/5xx 与网络错误时的额外重试次数（0=不重试）
    crawl_retry_count: int = 2
    crawl_retry_base_seconds: float = 1.0
    # 尊重目标站点 Retry-After，但最多等待这么久（秒）
    crawl_retry_max_wait_seconds: float = 5.0
    # 提取到的正文短于该长度，视为"没抓到有效内容"（多为需要 JS 渲染的页面）
    crawl_min_text_length: int = 30
    # 存进快照的 diff 文本上限，防止整页改写时把库撑爆
    crawl_max_diff_chars: int = 4000

    # ---- 竞品图标库 ----
    # 管理员上传竞品图标的大小上限（字节）；文件落在 storage_dir/icons 下，
    # 由 /api/icons 静态路由对外提供（见 services/icon_library.py）
    icon_max_bytes: int = 2 * 1024 * 1024
    crawl_user_agent: str = (
        "Mozilla/5.0 (compatible; CRBot/0.1; +https://github.com/competitor-radar)"
    )

    # ---- 浏览器渲染（里程碑 6 补全：SPA 页面兜底）----
    # 总开关；关闭后所有页面只走 httpx
    browser_render_enabled: bool = True
    browser_timeout_seconds: float = 20.0
    # 渲染后等 SPA 拉数据的上限；部分站点长轮询永不空闲，等不到就继续
    browser_network_idle_seconds: float = 5.0
    # 渲染时屏蔽图片/字体/媒体：正文提取用不到，省带宽也更快
    browser_block_assets: bool = True

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

    # ---- 任务调度（里程碑 10）----
    # 进程内 APScheduler；关闭后只能手动点「立即抓取」
    scheduler_enabled: bool = True
    # "找活干"的间隔（秒）：每分钟扫一次有没有到期的监控源
    scheduler_tick_seconds: int = 60
    # 单次扫描最多抓多少个源，避免长时间停机后积压任务一把冲垮目标站点
    scheduler_batch_limit: int = 20
    # 同批相邻两次抓取之间的间隔（秒），做温和错峰，不做并发压测
    scheduler_jitter_seconds: float = 0.5
    # 自动生成周报的时间（按服务器本地时间）：每周最后一天(周日) 06:00
    report_cron_day_of_week: str = "sun"
    report_cron_hour: int = 6
    report_cron_minute: int = 0
    # 自动生成月报：每月最后一天 06:00（apscheduler 用 day='last'）
    report_monthly_cron_day: str = "last"

    # ---- 通知推送（里程碑 10.2，可选）----
    notify_enabled: bool = False
    # log = 只写日志（开发/验证用，零外部依赖）；smtp = 发邮件
    notify_backend: str = "log"
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_sender: str = ""
    # 界面保存的 SMTP 授权码加密密钥（Fernet）；留空回退 JWT_SECRET。
    # ⚠️ 生产环境务必固定：换密钥后历史密文无法解密（会按明文失败处理）。
    smtp_secret: str = ""
    # 运维告警收件人：**仅**用于"调用方未指定收件人"的系统级通知，多个用英文逗号分隔。
    # 留空 = 这类通知不发信、只落一条 warning（安全失败）；**不要填个人/管理员常用邮箱**，
    # 历史上它正是"用户的竞品动态被投进管理员信箱"的通道。
    notify_recipients: str = ""
    # 通知里"查看详情"跳转地址（前端部署地址）；用于高优先级事件即时通知的链接
    frontend_base_url: str = "http://localhost:5173"

    # ---- 邮箱验证码（登录 / 重置密码）----
    # 验证码有效期（秒）：超过即失效，需重新获取
    email_code_ttl_seconds: int = 300
    # 同一个邮箱两次获取之间的最小间隔（秒）：防连点刷接口
    email_code_resend_seconds: int = 60
    # 同一个邮箱每小时最多获取几次（按自然小时滑动窗口内的固定桶计数）
    email_code_hourly_limit: int = 10

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",  # 从 backend/.env 读取
        env_file_encoding="utf-8",
        extra="ignore",  # .env 里有多余变量也不报错
    )


@lru_cache
def get_settings() -> Settings:
    """返回全局单例配置（进程内只构造一次，不会反复读文件）。"""
    return Settings()
