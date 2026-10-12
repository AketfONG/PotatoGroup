"""用户:资料查看/修改、搜索、注销。"""

import time

from fastapi import APIRouter, Depends
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core import security
from app.core.deps import get_current_user, get_db
from app.core.errors import bad_request, conflict, not_found
from app.models import Friend, FriendRequest, InboxMessage, ConversationMember, User
from app.schemas.common import ApiResponse, ok
from app.schemas.user import UserProfile, UserSearchOut, UserSummary, UserUpdateIn
from app.services.connection_manager import manager

router = APIRouter(prefix="/users", tags=["用户"])


def _summary(db: Session, user: User) -> UserSummary:
    return UserSummary(
        user_id=user.user_id,
        name=user.name,
        avatar=user.avatar,
        online=manager.is_online(user.user_id),
    )


@router.get("/me", response_model=ApiResponse[UserProfile])
async def my_profile(me: User = Depends(get_current_user)):
    return ok(
        UserProfile(
            user_id=me.user_id,
            name=me.name,
            avatar=me.avatar,
            email=me.email,
            phone=me.phone,
            register_time=me.register_time,
            login_time=me.login_time,
        )
    )


@router.patch("/me", response_model=ApiResponse[UserProfile])
async def update_profile(
    payload: UserUpdateIn,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.new_password is not None:
        if payload.old_password is None or not security.verify_password(payload.old_password, me.password):
            raise bad_request("旧密码错误")
        me.password = security.hash_password(payload.new_password)
    if payload.name is not None and payload.name != me.name:
        if db.scalar(select(User).where(User.name == payload.name)):
            raise conflict(2001, "用户名已存在")
        me.name = payload.name
    if payload.email is not None:
        me.email = payload.email
    if payload.phone is not None:
        me.phone = payload.phone
    if payload.avatar is not None:
        me.avatar = payload.avatar
    me.login_time = me.login_time  # 不变
    db.commit()
    return ok(
        UserProfile(
            user_id=me.user_id,
            name=me.name,
            avatar=me.avatar,
            email=me.email,
            phone=me.phone,
            register_time=me.register_time,
            login_time=me.login_time,
        )
    )


@router.get("", response_model=ApiResponse[UserSearchOut])
async def search_users(
    keyword: str = "",
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按用户名模糊搜索(加好友场景)。"""
    stmt = select(User).where(User.user_id != me.user_id)
    if keyword.strip():
        stmt = stmt.where(User.name.like(f"{keyword.strip()}%"))
    users = list(db.scalars(stmt.limit(20)))
    return ok(UserSearchOut(items=[_summary(db, u) for u in users]))


@router.get("/{user_id}", response_model=ApiResponse[UserSummary])
async def get_user(user_id: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise not_found("用户不存在")
    return ok(_summary(db, user))


@router.delete("/me", response_model=ApiResponse)
async def delete_account(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """注销:级联清理好友关系、好友申请、群成员关系、用户链(需求:完全清除相关数据)。"""
    uid = me.user_id
    db.execute(delete(Friend).where(or_(Friend.user_id == uid, Friend.friend_user_id == uid)))
    db.execute(delete(FriendRequest).where(or_(FriendRequest.from_user_id == uid, FriendRequest.to_user_id == uid)))
    db.execute(delete(ConversationMember).where(ConversationMember.member_user_id == uid))
    db.execute(delete(InboxMessage).where(InboxMessage.user_id == uid))
    db.delete(me)
    db.commit()
    return ok(None, message="账号已注销")