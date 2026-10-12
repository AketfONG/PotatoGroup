"""土豆聊天(Potato Messenger)后端入口。

启动:uvicorn app.main:app --reload --port 8000
文档:启动后访问 /docs(Swagger UI,由 Pydantic 模型自动生成)
契约:docs/02-API约定.md
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.v1.ws import router as ws_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.db.base import Base, engine
from app.models import *  # noqa: F401,F403 - 确保建表前所有模型已注册


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 骨架阶段启动时自动建表;生产环境使用 Alembic 迁移(见 docs/03-数据库设计.md)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="土豆聊天 Potato Messenger API",
    version="0.1.0",
    description="软工大作业即时通讯系统:前后端分离,RESTful + WebSocket。契约见 docs/02-API约定.md。",
    lifespan=lifespan,
)

# CORS:仅放行配置中的前端来源(课程安全要求,禁止 *)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router, prefix="/api/v1")
# WebSocket 按契约挂载在根路径 /ws(不属于 REST 的 /api/v1 前缀,nginx 单独转发)
app.include_router(ws_router)