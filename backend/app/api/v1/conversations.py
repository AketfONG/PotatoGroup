"""会话:列表/创建(单聊与群聊)/详情/群管理/成员操作/已读上报。"""

import time

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.models import Conversation, ConversationMember, Friend, InboxMessage, Message, User
from app.schemas.common import ApiResponse, ok
from app.schemas.conversation import (
    ConversationItemOut,
    ConversationListOut,
    ConversationOut,
    ConversationUpdateIn,
    CreateGroupIn,
    CreatePrivateIn,
    MemberAddIn,
    MemberOut,
    MemberSettingsIn,
)
from app.schemas.message import MessageOut, ReadIn
from app.schemas.user import UserSummary
from app.services import message_service
from app.services.connection_manager import manager

router = APIRouter(prefix="/conversations", tags=["会话"])


def _now() -> int:
    return int(time.time())


def _require_member(db: Session, conversation_id: int, user_id: int) -> tuple[Conversation, ConversationMember]:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise not_found("会话不存在")
    member = db.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.member_user_id == user_id,
        )
    )
    if member is None:
        raise forbidden("你不是该会话的成员")
    return conv, member


def _member_out(db: Session, m: ConversationMember) -> MemberOut:
    u = db.get(User, m.member_user_id)
    return MemberOut(
        user=UserSummary(
            user_id=m.member_user_id,
            name=u.name if u else "未知用户",
            avatar=u.avatar if u else None,
            online=manager.is_online(m.member_user_id),
        ),
        role=m.role,
        join_time=m.join_time,
    )


def _detail(db: Session, conv: Conversation) -> ConversationOut:
    members = list(db.scalars(select(ConversationMember).where(ConversationMember.conversation_id == conv.conversation_id)))
    return ConversationOut(
        conversation_id=conv.conversation_id,
        name=conv.name,
        type=conv.type,
        avatar=conv.avatar,
        owner_id=conv.owner_id,
        announcement=conv.announcement,
        members=[_member_out(db, m) for m in members],
        create_time=conv.create_time,
        update_time=conv.update_time,
    )


async def _broadcast_update(db: Session, conv: Conversation):
    detail = _detail(db, conv).model_dump()
    member_ids = [
        m.member_user_id
        for m in db.scalars(select(ConversationMember).where(ConversationMember.conversation_id == conv.conversation_id))
    ]
    for uid in member_ids:
        await manager.push_to_user(uid, {"type": "conversation.update", "data": detail})


@router.get("", response_model=ApiResponse[ConversationListOut])
async def list_conversations(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """我的会话列表:置顶优先,其余按更新时间倒序;含未读数与最新一条消息。"""
    memberships = list(db.scalars(select(ConversationMember).where(ConversationMember.member_user_id == me.user_id)))
    items: list[ConversationItemOut] = []
    for m in memberships:
        conv = db.get(Conversation, m.conversation_id)
        if conv is None:
            continue
        display_name = conv.name
        if conv.type == "private":
            others = db.scalars(
                select(ConversationMember).where(
                    ConversationMember.conversation_id == conv.conversation_id,
                    ConversationMember.member_user_id != me.user_id,
                )
            )
            other = next(others, None)
            if other is not None:
                u = db.get(User, other.member_user_id)
                display_name = u.name if u else "未知用户"
        last = db.scalar(
            select(Message).where(Message.conversation_id == conv.conversation_id).order_by(Message.msg_id.desc()).limit(1)
        )
        count = len(
            list(
                db.scalars(
                    select(ConversationMember.member_user_id).where(ConversationMember.conversation_id == conv.conversation_id)
                )
            )
        )
        items.append(
            ConversationItemOut(
                conversation_id=conv.conversation_id,
                name=display_name,
                type=conv.type,
                avatar=conv.avatar,
                member_count=count,
                last_msg=(
                    MessageOut(
                        msg_id=last.msg_id,
                        conversation_id=last.conversation_id,
                        sender_id=last.sender_id,
                        body=last.body,
                        reply_to=last.reply_to,
                        create_time=last.create_time,
                    )
                    if last
                    else None
                ),
                unread_count=message_service.unread_count(db, me.user_id, conv.conversation_id, m.read_index),
                pinned=bool(m.pinned),
                muted=bool(m.muted),
                update_time=conv.update_time,
            )
        )
    items.sort(key=lambda x: (not x.pinned, -x.update_time))
    return ok(ConversationListOut(items=items))


@router.post("", response_model=ApiResponse[ConversationOut], status_code=201)
async def create_group(payload: CreateGroupIn, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """创建群聊:初始成员必须是我的好友。"""
    for uid in payload.member_ids:
        if not db.scalar(select(Friend).where(Friend.user_id == me.user_id, Friend.friend_user_id == uid)):
            raise bad_request(f"用户 {uid} 不是你的好友,无法拉群")
    now = _now()
    conv = Conversation(name=payload.name, type="group", owner_id=me.user_id, create_time=now, update_time=now)
    db.add(conv)
    db.flush()
    db.add(ConversationMember(conversation_id=conv.conversation_id, member_user_id=me.user_id, role="owner", join_time=now, update_time=now))
    for uid in dict.fromkeys(payload.member_ids):  # 去重
        db.add(ConversationMember(conversation_id=conv.conversation_id, member_user_id=uid, role="member", join_time=now, update_time=now))
    db.commit()
    await _broadcast_update(db, conv)
    return ok(_detail(db, conv), message="群聊创建成功")


@router.post("/private", response_model=ApiResponse[ConversationOut], status_code=201)
async def create_private(payload: CreatePrivateIn, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """创建/获取与某好友的单聊(幂等:已存在则直接返回)。"""
    target = payload.target_user_id
    if not db.scalar(select(Friend).where(Friend.user_id == me.user_id, Friend.friend_user_id == target)):
        raise bad_request("对方不是你的好友,无法发起单聊")
    # 查找已存在的、由我们两人组成的单聊
    mine = set(db.scalars(select(ConversationMember.conversation_id).where(ConversationMember.member_user_id == me.user_id)))
    theirs = set(db.scalars(select(ConversationMember.conversation_id).where(ConversationMember.member_user_id == target)))
    for cid in mine & theirs:
        conv = db.get(Conversation, cid)
        if conv is not None and conv.type == "private":
            return ok(_detail(db, conv))
    now = _now()
    conv = Conversation(type="private", create_time=now, update_time=now)
    db.add(conv)
    db.flush()
    db.add(ConversationMember(conversation_id=conv.conversation_id, member_user_id=me.user_id, role="member", join_time=now, update_time=now))
    db.add(ConversationMember(conversation_id=conv.conversation_id, member_user_id=target, role="member", join_time=now, update_time=now))
    db.commit()
    await _broadcast_update(db, conv)
    return ok(_detail(db, conv), message="单聊已创建")


@router.get("/{conversation_id}", response_model=ApiResponse[ConversationOut])
async def conversation_detail(
    conversation_id: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    conv, _ = _require_member(db, conversation_id, me.user_id)
    return ok(_detail(db, conv))


@router.patch("/{conversation_id}", response_model=ApiResponse[ConversationOut])
async def update_conversation(
    conversation_id: int,
    payload: ConversationUpdateIn,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改群名/公告:仅群主与管理员。"""
    conv, member = _require_member(db, conversation_id, me.user_id)
    if member.role not in ("owner", "admin"):
        raise forbidden("仅群主或管理员可以修改群信息")
    if payload.name is not None:
        conv.name = payload.name
    if payload.announcement is not None:
        conv.announcement = payload.announcement
    conv.update_time = _now()
    db.commit()
    await _broadcast_update(db, conv)
    return ok(_detail(db, conv))


@router.post("/{conversation_id}/members", response_model=ApiResponse[ConversationOut])
async def add_members(
    conversation_id: int,
    payload: MemberAddIn,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """邀请好友入群(骨架阶段直接加入;群主/管理员审批为扩展项,见 docs/02-API约定.md)。"""
    conv, _ = _require_member(db, conversation_id, me.user_id)
    if conv.type != "group":
        raise bad_request("单聊不能添加成员")
    now = _now()
    for uid in dict.fromkeys(payload.user_ids):
        if not db.scalar(select(Friend).where(Friend.user_id == me.user_id, Friend.friend_user_id == uid)):
            raise bad_request(f"用户 {uid} 不是你的好友,无法邀请")
        existed = db.scalar(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.member_user_id == uid,
            )
        )
        if existed:
            raise conflict(2003, f"用户 {uid} 已在群中")
        db.add(ConversationMember(conversation_id=conversation_id, member_user_id=uid, role="member", join_time=now, update_time=now))
    conv.update_time = now
    db.commit()
    await _broadcast_update(db, conv)
    return ok(_detail(db, conv), message="成员已加入")


@router.delete("/{conversation_id}/members/{user_id}", response_model=ApiResponse)
async def remove_member(
    conversation_id: int,
    user_id: int,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """移出群:群主可移除任何人;管理员可移除普通成员;普通成员仅可移除自己(退群)。"""
    conv, me_member = _require_member(db, conversation_id, me.user_id)
    if conv.type != "group":
        raise bad_request("单聊不能移除成员")
    target = db.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.member_user_id == user_id,
        )
    )
    if target is None:
        raise not_found("该用户不在群中")
    if user_id != me.user_id:
        if me_member.role == "owner":
            pass  # 群主可移除任何人
        elif me_member.role == "admin" and target.role == "member":
            pass  # 管理员可移除普通成员
        else:
            raise forbidden("没有移除该成员的权限")
    if target.role == "owner" and user_id == me.user_id:
        raise bad_request("群主不能移除自己,请先转让群主或解散群聊")
    target_user_inbox = delete(InboxMessage).where(
        InboxMessage.user_id == user_id, InboxMessage.conversation_id == conversation_id
    )
    db.execute(target_user_inbox)
    db.delete(target)
    db.commit()
    await _broadcast_update(db, conv)
    return ok(None, message="成员已移出")


@router.post("/{conversation_id}/members/me", response_model=ApiResponse)
async def leave_group(conversation_id: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """主动退群(群主需先转让,骨架阶段禁止群主退群)。"""
    conv, member = _require_member(db, conversation_id, me.user_id)
    if conv.type != "group":
        raise bad_request("单聊不支持退出")
    if member.role == "owner":
        raise bad_request("群主不能退群,请先转让群主")
    db.execute(delete(InboxMessage).where(InboxMessage.user_id == me.user_id, InboxMessage.conversation_id == conversation_id))
    db.delete(member)
    db.commit()
    await _broadcast_update(db, conv)
    return ok(None, message="已退出群聊")


@router.patch("/{conversation_id}/me", response_model=ApiResponse)
async def update_my_settings(
    conversation_id: int,
    payload: MemberSettingsIn,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """会话置顶 / 免打扰(仅影响自己)。"""
    _, member = _require_member(db, conversation_id, me.user_id)
    if payload.pinned is not None:
        member.pinned = int(payload.pinned)
    if payload.muted is not None:
        member.muted = int(payload.muted)
    member.update_time = _now()
    db.commit()
    return ok(None, message="设置已更新")


@router.post("/{conversation_id}/read", response_model=ApiResponse)
async def mark_read(
    conversation_id: int,
    payload: ReadIn,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上报已读:更新 read_index,并向我的其他在线端推送 read.sync 实现多端同步。"""
    conv, member = _require_member(db, conversation_id, me.user_id)
    message_service.mark_read(db, member, payload.read_index)
    now = _now()
    row = InboxMessage(
        user_id=me.user_id,
        conversation_id=conversation_id,
        kind="read",
        payload={"conversation_id": conversation_id, "read_index": payload.read_index},
        create_time=now,
    )
    db.add(row)
    db.flush()
    await manager.push_to_user(
        me.user_id,
        {
            "type": "read.sync",
            "data": {"conversation_id": conversation_id, "read_index": payload.read_index},
        },
    )
    db.commit()
    return ok(None, message="已上报已读")