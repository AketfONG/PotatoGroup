"""API v1 路由汇总。注意:WebSocket 路由挂在根路径 /ws,在 main.py 单独 include。"""

from fastapi import APIRouter

from app.api.v1 import auth, conversations, friends, health, messages, sync, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(friends.router)
api_router.include_router(conversations.router)
api_router.include_router(messages.router)
api_router.include_router(sync.router)