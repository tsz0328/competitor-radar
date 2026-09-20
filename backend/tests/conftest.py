"""通知中心集成测试的公共 fixture。

用内存 SQLite（StaticPool 让所有连接共享同一内存库）+ dependency_overrides 把
get_db 指向测试库，完全不碰真实数据库（DB_AUTO_CREATE 也设为 false 双保险）。
"""
import os

# 必须在 import app 之前：避免任何启动建表逻辑误连真实库
os.environ.setdefault("DB_AUTO_CREATE", "false")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  确保全部模型注册到 Base.metadata
from app.core.database import get_db
from app.main import app
from app.models.base import Base


@pytest_asyncio.fixture
async def db():
    """内存 SQLite 引擎 + 建表，测试间相互隔离。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield sessionmaker
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    """用测试库覆盖 get_db 依赖的 httpx 异步客户端。"""

    async def override_get_db():
        async with db() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def session(db):
    """供测试直接插入用户/竞品/事件数据。"""
    async with db() as s:
        yield s
