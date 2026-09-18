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
    ]
    for table, column, ctype in additions:
        try:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ctype}")
        except Exception:
            # 列已存在 / 表不存在等：开发期直接忽略，不影响启动
            pass
