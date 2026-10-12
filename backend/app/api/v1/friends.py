"""好友:列表/删除,好友申请的发起与处理。"""

import time

from fastapi import APIRouter, Depends
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.models import Friend, FriendRequest, User
from app.schemas.common import ApiResponse, ok
from app.schemas.friend import FriendItem, FriendListOut, FriendRequestCreateIn, FriendRequestListOut, FriendRequestOut
from app.schemas.user import UserSummary
from app.services.connection_manager import manager

router = APIRouter(tags=["好友"])


def _friend_item(db: Session, uid: int, rel: Friend) -> FriendItem:
    friend = db.get(User, rel.friend_user_id)
    return FriendItem(
        user_id=rel.friend_user_id,
        name=friend.name if friend else "未知用户",
        avatar=friend.avatar if friend else None,
        remark=rel.remark,
        group_name=rel.group_name,
        online=manager.is_online(rel.friend_user_id),
    )


@router.get("/friends", response_model=ApiResponse[FriendListOut])
async def list_friends(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rels = list(db.scalars(select(Friend).where(Friend.user_id == me.user_id)))
    return ok(FriendListOut(items=[_friend_item(db, me.user_id, r) for r in rels]))


@router.delete("/friends/{friend_user_id}", response_model=ApiResponse)
async def delete_friend(
    friend_user_id: int,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除好友:双向两行一并删除。"""
    rel = db.scalar(select(Friend).where(Friend.user_id == me.user_id, Friend.friend_user_id == friend_user_id))
    if rel is None:
        raise not_found("对方不是你的好友")
    db.execute(
        delete(Friend).where(
            or_(
                (Friend.user_id == me.user_id) & (Friend.friend_user_id == friend_user_id),
                (Friend.user_id == friend_user_id) & (Friend.friend_user_id == me.user_id),
            )
        )
    )
    db.commit()
    return ok(None, message="已删除好友")


@router.post("/friend-requests", response_model=ApiResponse[FriendRequestOut], status_code=201)
async def create_friend_request(
    payload: FriendRequestCreateIn,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_id = payload.target_user_id
    if target_id == me.user_id:
        raise bad_request("不能添加自己为好友")
    target = db.get(User, target_id)
    if target is None:
        raise not_found("用户不存在")
    if db.scalar(select(Friend).where(Friend.user_id == me.user_id, Friend.friend_user_id == target_id)):
        raise conflict(2002, "你们已经是好友了")
    pending = db.scalar(
        select(FriendRequest).where(
            FriendRequest.from_user_id == me.user_id,
            FriendRequest.to_user_id == target_id,
            FriendRequest.status == "pending",
        )
    )
    if pending:
        raise conflict(2002, "已有待处理的好友申请")
    now = int(time.time())
    req = FriendRequest(from_user_id=me.user_id, to_user_id=target_id, status="pending", create_time=now, update_time=now)
    db.add(req)
    db.commit()
    # 在线则实时推送好友申请事件
    await manager.push_to_user(
        target_id,
        {
            "type": "friend.request",
            "data": FriendRequestOut(
                request_id=req.request_id,
                from_user=UserSummary(user_id=me.user_id, name=me.name, avatar=me.avatar, online=True),
                to_user_id=target_id,
                status="pending",
                create_time=now,
            ).model_dump(),
        },
    )
    return ok(
        FriendRequestOut(
            request_id=req.request_id,
            from_user=None,
            to_user_id=target_id,
            status="pending",
            create_time=now,
        ),
        message="好友申请已发送",
    )


@router.get("/friend-requests", response_model=ApiResponse[FriendRequestListOut])
async def list_friend_requests(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """我收到与我发出的好友申请(收到的携带对方摘要信息)。"""
    reqs = list(
        db.scalars(
            select(FriendRequest)
            .where(or_(FriendRequest.from_user_id == me.user_id, FriendRequest.to_user_id == me.user_id))
            .order_by(FriendRequest.request_id.desc())
            .limit(100)
        )
    )
    items = []
    for r in reqs:
        from_user = None
        if r.to_user_id == me.user_id:
            u = db.get(User, r.from_user_id)
            if u is not None:
                from_user = UserSummary(user_id=u.user_id, name=u.name, avatar=u.avatar, online=manager.is_online(u.user_id))
        items.append(
            FriendRequestOut(
                request_id=r.request_id,
                from_user=from_user,
                to_user_id=r.to_user_id,
                status=r.status,
                create_time=r.create_time,
            )
        )
    return ok(FriendRequestListOut(items=items))


@router.post("/friend-requests/{request_id}/accept", response_model=ApiResponse)
async def accept_friend_request(
    request_id: int,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = db.get(FriendRequest, request_id)
    if req is None or req.to_user_id != me.user_id:
        raise not_found("好友申请不存在")
    if req.status != "pending":
        raise conflict(2002, "该申请已处理")
    req.status = "accepted"
    req.update_time = int(time.time())
    now = int(time.time())
    # 双向写入两行好友关系
    db.add(Friend(user_id=me.user_id, friend_user_id=req.from_user_id, update_time=now))
    db.add(Friend(user_id=req.from_user_id, friend_user_id=me.user_id, update_time=now))
    db.commit()
    await manager.push_to_user(req.from_user_id, {"type": "friend.accepted", "data": {"user_id": me.user_id, "name": me.name}})
    return ok(None, message="已同意好友申请")


@router.post("/friend-requests/{request_id}/reject", response_model=ApiResponse)
async def reject_friend_request(
    request_id: int,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = db.get(FriendRequest, request_id)
    if req is None or req.to_user_id != me.user_id:
        raise not_found("好友申请不存在")
    if req.status != "pending":
        raise conflict(2002, "该申请已处理")
    req.status = "rejected"
    req.update_time = int(time.time())
    db.commit()
    return ok(None, message="已拒绝好友申请")