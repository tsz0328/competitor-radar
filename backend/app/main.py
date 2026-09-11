from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, competitors, events, sources, users
from app.core.config import get_settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers

settings = get_settings()


# "生命周期"装饰器：app 启动前执行 with 前面，关闭时执行后面
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时先建好数据库
    await init_db()
    # yield 让出控制权，此后 app 正式对外服务
    yield


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
app.include_router(auth.router)
app.include_router(competitors.router)
app.include_router(sources.router)
app.include_router(events.router)


# @app.get("/") 是装饰器：注册"GET 请求打到根路径 / 时调用下面函数"
@app.get("/")
async def read_root():
    # 返回一个字典，FastAPI 自动转成 JSON 发给浏览器
    return {"Hello": "World"}
