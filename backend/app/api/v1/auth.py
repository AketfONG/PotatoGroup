"""认证:注册 / 登录 / 登出。错误码见 docs/02-API约定.md。"""

import time

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.deps import get_current_user, get_db
from app.core.errors import ApiError, conflict, unauthorized
from app.models import User
from app.schemas.auth import LoginIn, LoginOut, RegisterIn, RegisterOut
from app.schemas.common import ApiResponse, ok
from app.schemas.user import UserSummary
from app.services.connection_manager import manager

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=ApiResponse[RegisterOut], status_code=201)
async def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.name == payload.name)):
        raise conflict(2001, "用户名已存在")
    user = User(
        name=payload.name,
        password=security.hash_password(payload.password),
        register_time=int(time.time()),
    )
    db.add(user)
    db.commit()
    return ok(RegisterOut(user_id=user.user_id), message="注册成功")


@router.post("/login", response_model=ApiResponse[LoginOut])
async def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.name == payload.name))
    # 统一错误提示,防止用户名枚举
    if user is None or not security.verify_password(payload.password, user.password):
        raise ApiError(401, 1002, "用户名或密码错误")
    user.login_time = int(time.time())
    db.commit()
    token = security.create_token(user.user_id)
    summary = UserSummary(user_id=user.user_id, name=user.name, avatar=user.avatar, online=manager.is_online(user.user_id))
    return ok(LoginOut(token=token, user=summary))


@router.delete("/logout", response_model=ApiResponse)
async def logout(me: User = Depends(get_current_user)):
    """JWT 无状态登出:客户端丢弃 token 即可;服务端黑名单见 docs/02-API约定.md 扩展章节。"""
    return ok(None, message="已登出")