"""消息:发送、会话历史(游标翻页)、撤回、本地删除。

消息生命周期(需求文档):发送(上行)→ 分发(写会话链+用户链)→ 送达(WS 推送/REST 兜底)→ 处理(渲染)。
"""

import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.errors import bad_request, forbidden, not_found
from app.models import InboxMessage, Message, User
from app.schemas.common import ApiResponse, ok
from app.schemas.message import HistoryOut, MessageIn, MessageOut
from app.services import message_service
from app.services.connection_manager import manager

router = APIRouter(prefix="/conversations", tags=["消息"])

RECALL_WINDOW_SECONDS = 120  # 撤回时限(秒)


def _require_member(db: Session, conversation_id: int, user_id: int):
    from app.models import Conversation, ConversationMember

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


@router.post("/{conversation_id}/messages", response_model=ApiResponse[MessageOut], status_code=201)
async def send_message(
    conversation_id: int,
    payload: MessageIn,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发送消息:写会话链 + 写各成员用户链(写扩散),在线成员实时推送。"""
    conv, _ = _require_member(db, conversation_id, me.user_id)
    if payload.reply_to is not None:
        replied = db.get(Message, payload.reply_to)
        if replied is None or replied.conversation_id != conversation_id:
            raise bad_request("被回复的消息不存在")
    events = message_service.send_message(db, conv, me.user_id, payload.body, payload.reply_to)
    # 推送(含发送者自己的其他端,实现多端同步)
    for uid, event in events.items():
        await manager.push_to_user(uid, event)
    data = events.get(me.user_id, {}).get("data")
    if data is None:  # 理论不可达:发送者必为成员
        raise bad_request("消息发送失败")
    return ok(MessageOut(**data), message="发送成功")


@router.get("/{conversation_id}/messages", response_model=ApiResponse[HistoryOut])
async def conversation_history(
    conversation_id: int,
    cursor: int | None = Query(default=None, description="上一页最后一条 msg_id,取更早的消息"),
    limit: int = Query(default=50, ge=1, le=100),
    sender_id: int | None = Query(default=None, description="按发送者过滤"),
    start_time: int | None = Query(default=None, description="起始时间戳(含)"),
    end_time: int | None = Query(default=None, description="结束时间戳(含)"),
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """会话历史:新成员可拉取入群前消息;支持按发送者/时间段过滤。

    每条消息附带 `seq`(它在**我的**用户链上的序号),客户端上报已读时用它作为
    `read_index` —— 不能用 `msg_id`(全局 ID 与我的 seq 不是一回事,见 docs/02 第 6 节)。

    我已经删除的消息不再出现,与 `/sync` 保持同一口径。
    """
    _require_member(db, conversation_id, me.user_id)
    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if cursor is not None:
        stmt = stmt.where(Message.msg_id < cursor)
    if sender_id is not None:
        stmt = stmt.where(Message.sender_id == sender_id)
    if start_time is not None:
        stmt = stmt.where(Message.create_time >= start_time)
    if end_time is not None:
        stmt = stmt.where(Message.create_time <= end_time)
    # 已删除的消息:其用户链记录已被改写成 kind="delete" 墓碑,这里按同一口径排除
    stmt = stmt.where(
        Message.msg_id.not_in(message_service.deleted_msg_ids(me.user_id)),
    )
    # 顺带取出每条消息在「我」的用户链上的 seq(相关标量子查询,走 (user_id, id) 索引)
    my_seq = (
        select(InboxMessage.id)
        .where(
            InboxMessage.user_id == me.user_id,
            InboxMessage.msg_id == Message.msg_id,
        )
        .limit(1)
        .correlate(Message)
        .scalar_subquery()
    )
    rows = list(db.execute(stmt.add_columns(my_seq).order_by(Message.msg_id.desc()).limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        MessageOut(
            msg_id=m.msg_id,
            conversation_id=m.conversation_id,
            sender_id=m.sender_id,
            body=m.body,
            reply_to=m.reply_to,
            create_time=m.create_time,
            seq=seq,
        )
        for m, seq in rows
    ]
    return ok(HistoryOut(items=items, next_cursor=items[-1].msg_id if has_more and items else None))


@router.post("/{conversation_id}/messages/{msg_id}/recall", response_model=ApiResponse)
async def recall_message(
    conversation_id: int,
    msg_id: int,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """撤回消息:仅发送者本人,且在时限内;通过 recall 命令消息多端同步。"""
    conv, _ = _require_member(db, conversation_id, me.user_id)
    msg = db.get(Message, msg_id)
    if msg is None or msg.conversation_id != conversation_id:
        raise not_found("消息不存在")
    if msg.sender_id != me.user_id:
        raise forbidden("只能撤回自己发送的消息")
    if int(time.time()) - msg.create_time > RECALL_WINDOW_SECONDS:
        raise bad_request("超过撤回时限")
    events = message_service.recall_message(db, conv, msg)
    for uid, event in events.items():
        await manager.push_to_user(uid, event)
    return ok(None, message="消息已撤回")


@router.delete("/{conversation_id}/messages/{msg_id}", response_model=ApiResponse)
async def delete_message_for_me(
    conversation_id: int,
    msg_id: int,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """本地删除:只对我生效,不影响其他成员。

    实现为「投递墓碑」而非物理删行:把我用户链上那条记录改写成 `kind="delete"`。
    这样历史查询与 `/sync` 口径一致 —— 删掉的消息既不会在历史里复活,也不会被增量同步
    重新拉回来;离线设备下次补拉时能拿到这条删除标记,从而清掉本地缓存。

    同时向本用户的其他在线端推送 `message.delete`(多端同步)。
    重复删除是幂等的:已删除时直接返回成功,不重复写墓碑、不重复推送。
    """
    _require_member(db, conversation_id, me.user_id)
    msg = db.get(Message, msg_id)
    if msg is None or msg.conversation_id != conversation_id:
        raise not_found("消息不存在")
    event = message_service.delete_message_for_me(db, me.user_id, conversation_id, msg_id)
    if event is not None:
        # 事务已提交后再推送
        await manager.push_to_user(me.user_id, event)
    return ok(None, message="消息已删除")