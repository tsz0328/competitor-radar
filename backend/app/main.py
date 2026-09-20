import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    auth,
    competitors,
    crawl_logs,
    events,
    llm,
    notifications,
    reports,
    scheduler,
    setting,
    snapshots,
    sources,
    trends,
    users,
)
from app.core.config import get_settings
from app.core.database import init_db
from app.core.event_bus import bus
from app.core.exceptions import register_exception_handlers
from app.services import browser
from app.services.scheduler import shutdown_scheduler, start_scheduler

settings = get_settings()

logger = logging.getLogger(__name__)


async def seed_admin() -> None:
    """按配置种入初始管理员；默认关闭，且绝不自动提权或改已有账号密码。"""
    if not settings.bootstrap_admin_enabled:
        logger.info("初始管理员种入已关闭（BOOTSTRAP_ADMIN_ENABLED=false）")
        return
    username = settings.bootstrap_admin_username.strip()
    password = settings.bootstrap_admin_password
    if not username or not password:
        logger.error(
            "BOOTSTRAP_ADMIN_ENABLED=true，但用户名或密码为空，已跳过初始管理员种入"
        )
        return

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models.user import User

    async with SessionLocal() as db:
        admin = (
            await db.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if admin is None:
            db.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    password_length=len(password),
                    is_admin=True,
                )
            )
            await db.commit()
        elif not admin.is_admin:
            logger.warning(
                "系统已存在同名普通账号，按安全策略不会自动提权：%s", username
            )


def _warn_if_selector_loop() -> None:
    """Windows 下若事件循环不是 Proactor，Playwright 无法创建子进程，渲染兜底会失效。

    最常见诱因是 `uvicorn --reload`（会把 loop 换成 SelectorEventLoop）。
    这里启动即告警，避免拖到真正抓取时才以"未提取到有效正文"的形式暴露。
    """
    if sys.platform != "win32":
        return
    loop_name = type(asyncio.get_running_loop()).__name__
    if loop_name != "ProactorEventLoop":
        logger.warning(
            "当前事件循环为 %s，浏览器渲染将不可用（Playwright 无法创建子进程）。"
            "请改用 `python run_dev.py` 启动，或给 uvicorn 加 `--loop asyncio:ProactorEventLoop`。",
            loop_name,
        )


# "生命周期"装饰器：app 启动前执行 with 前面，关闭时执行后面
@asynccontextmanager
async def lifespan(app: FastAPI):
    _warn_if_selector_loop()
    # 启动时先建好数据库
    await init_db()
    # 种入默认管理员账号（admin / 123456），不存在才创建
    await seed_admin()
    # 再拉起进程内调度器：按各监控源的频率自动抓取、每周自动生成周报。
    # AI 配置按用户实时解析（见 services/settings.get_user_llm_config），
    # 不再需要在启动时把某一份配置载入进程内全局状态。
    start_scheduler()
    try:
        # yield 让出控制权，此后 app 正式对外服务
        yield
    finally:
        # 关闭时优雅停止调度器，避免退出阶段还在跑抓取任务
        shutdown_scheduler()
        # 再释放可能已拉起的浏览器（懒启动，没用到就不会创建）
        await browser.close_browser()
        # 最后关闭 Redis pub/sub 中可能残留的 SSE 订阅连接
        await bus.aclose()


# 创建一个 FastAPI 实例，命名 app —— 整个服务的本体, 把 lifespan 挂到 app 上
app = FastAPI(lifespan=lifespan)

# 注册全局异常处理器：把各类异常统一收敛成 {code, message, data} 响应壳
register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)  # 把 users 路由组挂进来
app.include_router(llm.router)
app.include_router(setting.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(competitors.router)
app.include_router(sources.router)
app.include_router(events.router)
app.include_router(notifications.router)
app.include_router(snapshots.router)
app.include_router(crawl_logs.router)
app.include_router(trends.router)
app.include_router(reports.router)
app.include_router(scheduler.router)


# @app.get("/") 是装饰器：注册"GET 请求打到根路径 / 时调用下面函数"
@app.get("/")
async def read_root():
    # 返回一个字典，FastAPI 自动转成 JSON 发给浏览器
    return {"Hello": "World"}
