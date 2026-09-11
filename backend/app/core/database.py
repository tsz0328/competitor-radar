from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

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
    # 延迟导入：保证 models 下所有表都已注册
    from app.models import Base

    # 拿到"建表总闸"并开始一次事务
    async with engine.begin() as conn:
        # run_sync = 让"同步的建表逻辑"在异步连接里执行
        await conn.run_sync(Base.metadata.create_all)
