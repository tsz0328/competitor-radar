"""Alembic 运行环境（里程碑 11）。

三个要点：
1. **连接串复用应用配置**：`alembic.ini` 里不写 URL，这里读 `settings.db_url`，
   保证迁移和应用操作的一定是同一个库；
2. **用异步 engine**：项目全程异步（aiosqlite / aiomysql），迁移同样走 async engine，
   再通过 `run_sync` 执行同步的迁移逻辑；
3. **`render_as_batch=True`**：SQLite 不支持多数 `ALTER TABLE`，批处理模式会
   自动用"建新表 → 拷数据 → 换名"实现，这样开发期也能用同一条迁移。
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = get_settings()

# autogenerate 的比对基准：导入 app.models 即注册了全部表
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只把 SQL 打到标准输出，不连数据库（用于人工审阅或手工执行）。"""
    context.configure(
        url=settings.db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # 字段类型变更也要能识别出来
        compare_server_default=True,
        render_as_batch=True,  # SQLite 的 ALTER 兼容（见模块说明）
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(settings.db_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
