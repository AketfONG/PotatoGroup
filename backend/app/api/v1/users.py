"""用户:资料查看/修改、搜索、注销。"""

import time

from fastapi import APIRouter, Depends
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.deps import get_current_user, get_db
from app.core.errors import bad_request, conflict, not_found
from app.models import (
    Conversation,
    ConversationMember,
    Friend,
    FriendRequest,
    InboxMessage,
    Message,
    User,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.user import DeleteAccountIn, UserProfile, UserSearchOut, UserSummary, UserUpdateIn
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


def _delete_conversation(db: Session, conv: Conversation) -> None:
    """物理删除整段会话:消息、全部成员关系与所有用户的用户链条目。"""
    db.execute(delete(InboxMessage).where(InboxMessage.conversation_id == conv.conversation_id))
    db.execute(delete(Message).where(Message.conversation_id == conv.conversation_id))
    db.execute(delete(ConversationMember).where(ConversationMember.conversation_id == conv.conversation_id))
    db.delete(conv)


@router.delete("/me", response_model=ApiResponse)
async def delete_account(
    payload: DeleteAccountIn,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """注销账号(需当前密码确认)。

    清理策略:
    - 删除好友关系、好友申请、会话成员关系与我的用户链;
    - 私聊会话及其消息整体删除;
    - 群聊保留历史消息,但把发送者置空;群主注销时优先转让给管理员,其次最早加入的成员,
      没有剩余成员则删除整个群聊。
    """
    if not security.verify_password(payload.password, me.password):
        raise bad_request("密码错误,无法注销账号")

    uid = me.user_id
    now = int(time.time())
    try:
        memberships = list(
            db.scalars(select(ConversationMember).where(ConversationMember.member_user_id == uid))
        )
        for membership in memberships:
            conv = db.get(Conversation, membership.conversation_id)
            if conv is None:
                continue
            if conv.type == "private":
                _delete_conversation(db, conv)
                continue

            remaining = list(
                db.scalars(
                    select(ConversationMember).where(
                        ConversationMember.conversation_id == conv.conversation_id,
                        ConversationMember.member_user_id != uid,
                    )
                )
            )
            if not remaining:
                _delete_conversation(db, conv)
                continue

            # 群主注销:管理员优先,其次按入群时间最早的成员接任
            if conv.owner_id == uid or conv.owner_id is None:
                replacement = sorted(
                    remaining,
                    key=lambda m: (m.role != "admin", m.join_time, m.member_user_id),
                )[0]
                replacement.role = "owner"
                conv.owner_id = replacement.member_user_id
                conv.update_time = now

            db.delete(membership)
            db.execute(
                delete(InboxMessage).where(
                    InboxMessage.user_id == uid,
                    InboxMessage.conversation_id == conv.conversation_id,
                )
            )

        # 群历史保留,但不再关联已注销用户;私聊消息已在上面整体删除
        db.execute(update(Message).where(Message.sender_id == uid).values(sender_id=None))
        db.execute(delete(Friend).where(or_(Friend.user_id == uid, Friend.friend_user_id == uid)))
        db.execute(
            delete(FriendRequest).where(
                or_(FriendRequest.from_user_id == uid, FriendRequest.to_user_id == uid)
            )
        )
        db.execute(delete(ConversationMember).where(ConversationMember.member_user_id == uid))
        db.execute(delete(InboxMessage).where(InboxMessage.user_id == uid))
        db.delete(me)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return ok(None, message="账号已注销")