import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

DATABASE_URL = settings.db_url

# 创建"异步数据库引擎"：它是连数据库的总开关，程序里全局只用一份
engine = create_async_engine(DATABASE_URL, echo=False)

# 会话工厂：每次请求由它产出一个会话
SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    # 提交后仍能读取对象属性（组装响应要用）
    expire_on_commit=False,
)


# 依赖：FastAPI 会在每个请求时调用它，请求结束自动关闭会话
async def get_db():
    async with SessionLocal() as session:
        # yield = 把会话交给接口函数；请求结束后才继续执行下面（收尾关闭）
        yield session


async def init_db():
    """启动时初始化数据库。

    开发期直接 create_all 建表；生产把 DB_AUTO_CREATE 设为 false，
    改由 `alembic upgrade head` 建表/升级，应用不再动结构。
    """
    if not settings.db_auto_create:
        logger.info("已跳过自动建表（DB_AUTO_CREATE=false），请确保已执行 alembic upgrade head")
        return

    # 延迟导入：保证 models 下所有表都已注册
    from app.models import Base

    # 拿到"建表总闸"并开始一次事务
    async with engine.begin() as conn:
        # run_sync = 让"同步的建表逻辑"在异步连接里执行
        await conn.run_sync(Base.metadata.create_all)
        # create_all 不会改已有表结构：对开发期已存在的库补上新增列，
        # 列已存在时静默忽略，保证老 dev.db 也能直接启动。
        await conn.run_sync(_migrate_dev_columns)


def _migrate_dev_columns(conn) -> None:
    """开发期兼容：为已存在的表补加新列（生产请改用 alembic，勿依赖此函数）。"""
    additions = [
        ("intelligence_events", "ai_analysis", "TEXT"),
        # 周报收藏（跟随账号，服务端持久化）：新增列，老 dev.db 补上
        ("weekly_reports", "favorite", "BOOLEAN NOT NULL DEFAULT 0"),
        # 用户级偏好（跟随账号，原先在前端 localStorage）：新增列，老 dev.db 补上
        ("users", "preferences", "JSON"),
        # 供应商从上游获取到的模型列表（JSON 数组）：新增列，老 dev.db 补上
        ("llm_providers", "models", "TEXT NOT NULL DEFAULT ''"),
        # AI 配置按用户隔离：老 dev.db 补上归属列（存量归最早用户，开发库通常就是 1）
        ("llm_providers", "user_id", "BIGINT NOT NULL DEFAULT 1"),
        ("app_settings", "user_id", "BIGINT NOT NULL DEFAULT 1"),
        # 用户中心：头像（data URL），老 dev.db 补上
        ("users", "avatar", "TEXT"),
        # 用户中心：展示用昵称，老 dev.db 补上（空串表示未设置）
        ("users", "nickname", "VARCHAR(50) NOT NULL DEFAULT ''"),
        # 用户中心：密码位数（仅存长度，不存明文），老 dev.db 补上
        ("users", "password_length", "INTEGER"),
        # 管理员标记：老 dev.db 补上
        ("users", "is_admin", "BOOLEAN NOT NULL DEFAULT 0"),
        # 账号启用状态（管理员可停用）：老 dev.db 补上，默认启用
        ("users", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
        # 竞品软删除（回收站）：老 dev.db 补上，空值表示未删除
        ("competitors", "deleted_at", "DATETIME"),
        # 免登录分享：token + 过期时间（过期为空 = 永久），老 dev.db 补上
        ("weekly_reports", "share_token", "VARCHAR(64)"),
        ("weekly_reports", "share_expires_at", "DATETIME"),
    ]
    for table, column, ctype in additions:
        try:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ctype}")
        except Exception:
            # 列已存在 / 表不存在等：开发期直接忽略，不影响启动
            pass
    # 允许同一周期存多份报告：老 dev.db 里残留的唯一索引主动摘掉，
    # 否则「再生成一份新的」会被 UNIQUE 约束挡下（生产走 alembic 迁移）。
    try:
        conn.exec_driver_sql("DROP INDEX IF EXISTS uq_report_user_range_start")
    except Exception:
        pass
