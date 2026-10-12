"""消息分发服务:写会话链 + 写用户链(写扩散)+ 推送。

对应需求文档消息生命周期:消息发送 → 消息分发 → 消息送达 → 消息处理。
"""

import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, ConversationMember, InboxMessage, Message


def _now() -> int:
    return int(time.time())


def get_members(db: Session, conversation_id: int) -> list[ConversationMember]:
    return list(db.scalars(select(ConversationMember).where(ConversationMember.conversation_id == conversation_id)))


def last_seq_of_user(db: Session, user_id: int) -> int:
    """用户链上最新 seq(无消息则为 0)。"""
    seq = db.scalar(select(func.max(InboxMessage.id)).where(InboxMessage.user_id == user_id))
    return seq or 0


def _message_dict(msg: Message) -> dict[str, Any]:
    return {
        "msg_id": msg.msg_id,
        "conversation_id": msg.conversation_id,
        "sender_id": msg.sender_id,
        "body": msg.body,
        "reply_to": msg.reply_to,
        "create_time": msg.create_time,
    }


def send_message(
    db: Session,
    conversation: Conversation,
    sender_id: int,
    body: str,
    reply_to: int | None,
) -> dict[int, dict[str, Any]]:
    """发送消息:写会话链,为每个成员写用户链,返回 {user_id: 推送事件}。

    事件格式:{"type": "message.new", "seq": 本端新 seq, "prev_seq": 上一条 seq, "data": Message}
    客户端比对 prev_seq 与本地 cursor,不一致即调用 GET /api/v1/sync 补拉。
    """
    now = _now()
    msg = Message(conversation_id=conversation.conversation_id, sender_id=sender_id, body=body, reply_to=reply_to, create_time=now)
    db.add(msg)
    db.flush()  # 取得 msg_id

    events: dict[int, dict[str, Any]] = {}
    for member in get_members(db, conversation.conversation_id):
        prev_seq = last_seq_of_user(db, member.member_user_id)
        row = InboxMessage(
            user_id=member.member_user_id,
            conversation_id=conversation.conversation_id,
            msg_id=msg.msg_id,
            kind="message",
            payload=None,
            create_time=now,
        )
        db.add(row)
        db.flush()  # 取得自增 seq
        events[member.member_user_id] = {
            "type": "message.new",
            "seq": row.id,
            "prev_seq": prev_seq,
            "data": _message_dict(msg),
        }
        # 发送者自己的已读位置推进到最新
        if member.member_user_id == sender_id:
            member.read_index = row.id

    conversation.update_time = now
    db.commit()
    return events


def recall_message(db: Session, conversation: Conversation, msg: Message) -> dict[int, dict[str, Any]]:
    """撤回:写扩散投递 recall 命令消息,历史中 body 置为占位文本。"""
    now = _now()
    msg.body = "[消息已撤回]"
    events: dict[int, dict[str, Any]] = {}
    for member in get_members(db, conversation.conversation_id):
        prev_seq = last_seq_of_user(db, member.member_user_id)
        row = InboxMessage(
            user_id=member.member_user_id,
            conversation_id=conversation.conversation_id,
            msg_id=msg.msg_id,
            kind="recall",
            payload={"msg_id": msg.msg_id, "conversation_id": conversation.conversation_id},
            create_time=now,
        )
        db.add(row)
        db.flush()
        events[member.member_user_id] = {
            "type": "message.recall",
            "seq": row.id,
            "prev_seq": prev_seq,
            "data": {"msg_id": msg.msg_id, "conversation_id": conversation.conversation_id},
        }
    db.commit()
    return events


def mark_read(db: Session, member: ConversationMember, read_index: int) -> None:
    """上报已读:更新 read_index(多端同步通过 read.sync 事件推送)。"""
    member.read_index = read_index
    member.update_time = _now()
    db.commit()


def unread_count(db: Session, user_id: int, conversation_id: int, read_index: int) -> int:
    """未读数 = 用户链上该会话中 seq > read_index 的普通消息条数。"""
    return int(
        db.scalar(
            select(func.count(InboxMessage.id)).where(
                InboxMessage.user_id == user_id,
                InboxMessage.conversation_id == conversation_id,
                InboxMessage.id > read_index,
                InboxMessage.kind == "message",
            )
        )
        or 0
    )