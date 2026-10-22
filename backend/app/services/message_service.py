"""消息分发服务:写会话链 + 写用户链(写扩散)+ 推送。

对应需求文档消息生命周期:消息发送 → 消息分发 → 消息送达 → 消息处理。
"""

import time
from typing import Any, NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import bad_request
from app.models import Conversation, ConversationMember, InboxMessage, Message


def _now() -> int:
    return int(time.time())


def get_members(db: Session, conversation_id: int) -> list[ConversationMember]:
    return list(db.scalars(select(ConversationMember).where(ConversationMember.conversation_id == conversation_id)))


def last_seq_of_user(db: Session, user_id: int) -> int:
    """用户链上最新 seq(无消息则为 0)。"""
    seq = db.scalar(select(func.max(InboxMessage.id)).where(InboxMessage.user_id == user_id))
    return seq or 0


class ReadSyncEvent(NamedTuple):
    """一次成功的已读上报所对应的用户链条目信息(供路由推送 read.sync)。"""

    seq: int
    prev_seq: int
    conversation_id: int
    read_index: int


def deleted_msg_ids(user_id: int):
    """我删除过的消息 msg_id 子查询。

    删除标记复用用户链里既有的 `kind="delete"` 行 —— 该行本身就是一条「投递墓碑」,
    因此不必给 `inbox_message` 加列,也就不需要数据库迁移(见 docs/03-数据库设计.md)。
    历史查询、`/sync` 与未读数三处共用这一个子查询,保证口径一致。
    """
    return select(InboxMessage.msg_id).where(
        InboxMessage.user_id == user_id,
        InboxMessage.kind == "delete",
        InboxMessage.msg_id.is_not(None),
    )


def _delete_payload(conversation_id: int, msg_id: int) -> dict[str, int]:
    """删除墓碑载荷:`msg_id` 供历史与同步过滤,`conversation_id` 供多端定位。"""
    return {"msg_id": msg_id, "conversation_id": conversation_id}


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
        # prev_seq 取该成员此刻的链尾:行插入后链尾才变成本条,故必须在插入前取
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
        # 同 send_message:prev_seq 必须在插入前取
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


def mark_read(db: Session, member: ConversationMember, read_index: int) -> ReadSyncEvent | None:
    """上报已读:推进 `read_index`,并向本用户的其他端推送 read.sync。

    两条约束:

    1. **单调**:新值小于当前值时视为旧请求乱序到达,不改动、也不推送;
    2. **有上限**:`read_index` 的语义是「我已读到我的用户链第几条」,而调用方(客户端)
       只能读到确实投递给它的条目,因此超过 `last_seq_of_user()` 的值必然是伪造或客户端
       状态异常 —— 直接拒绝,而不是截断(截断等于照旧把未读清零,反而掩盖客户端 bug)。

    成功时除更新 `read_index` 外,还向用户链写入一条 `kind="read"` 命令消息,使其占用一个
    seq。返回的 `seq` 即该条目的 seq、`prev_seq` 为其前一条,让客户端能用与 `message.new`
    相同的连续性规则校验 read.sync,发现缺口立即调 `/sync` 补拉。
    重复上报同一个值不写链、不推送,避免无意义的链增长。
    """
    upper = last_seq_of_user(db, member.member_user_id)
    if read_index > upper:
        raise bad_request("已读位置超过该用户收到的最新消息序号")
    if read_index <= member.read_index:
        return None

    now = _now()
    prev_seq = upper  # 此刻的链尾,插入后链尾变为本次 read 条目的 seq
    member.read_index = read_index
    member.update_time = now

    row = InboxMessage(
        user_id=member.member_user_id,
        conversation_id=member.conversation_id,
        kind="read",
        payload={"conversation_id": member.conversation_id, "read_index": read_index},
        create_time=now,
    )
    db.add(row)
    db.flush()  # 取得自增 seq
    db.commit()
    return ReadSyncEvent(
        seq=row.id,
        prev_seq=prev_seq,
        conversation_id=member.conversation_id,
        read_index=read_index,
    )


def delete_message_for_me(
    db: Session,
    user_id: int,
    conversation_id: int,
    msg_id: int,
) -> dict[str, Any]:
    """本地删除:只对我生效,历史上不再出现,其他成员不受影响。

    实现为「投递墓碑」:把用户链上那条 `kind="message"` 的记录改写成 `kind="delete"`,
    并带上 `payload={"msg_id", "conversation_id"}`。这样:

    - 会话历史(`message` 表)靠 tombstone 子查询过滤掉它;
    - `/sync`(用户链)把该条以 `kind="delete"` 返回,客户端据此从本地移除,
      离线端下次补拉同样能拿到这个删除,**不会再出现「历史里复活」**;
    - 未读数不计入已删消息。

    若我此前没有投递过这条消息(例如它是入群前的历史消息),则补写一条墓碑,
    保证历史与同步两处口径一致。

    返回 `prev_seq`/`seq`/`data`,供路由向本用户其他端推送 `message.delete`(多端同步)。
    """
    now = _now()
    prev_seq = last_seq_of_user(db, user_id)
    row = db.scalar(
        select(InboxMessage).where(
            InboxMessage.user_id == user_id,
            InboxMessage.msg_id == msg_id,
            InboxMessage.kind.in_(("message", "delete")),
        )
    )
    if row is None:
        # 该消息没有我的投递记录(入群前历史等):补写墓碑,payload 兼作判定依据
        row = InboxMessage(
            user_id=user_id,
            conversation_id=conversation_id,
            msg_id=msg_id,
            kind="delete",
            payload=_delete_payload(conversation_id, msg_id),
            create_time=now,
        )
        db.add(row)
    else:
        row.kind = "delete"
        row.payload = _delete_payload(conversation_id, msg_id)
    db.flush()  # 必须先取到 row.id:新建墓碑时它此刻还是 None,不能拿去和 read_index 比较

    # 已读位置可能落在这条之后。留着它会让单调约束把客户端后续的合法上报判为「回退」,
    # 所以把已读位置压到被删消息之前(不会增加未读数:被删消息本身已不计入)。
    member = db.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.member_user_id == user_id,
        )
    )
    if member is not None and row.id is not None and member.read_index > row.id:
        member.read_index = row.id
        member.update_time = now

    event = {
        "type": "message.delete",
        "seq": row.id,
        "prev_seq": prev_seq,
        "data": _delete_payload(conversation_id, msg_id),
    }
    db.commit()
    return event


def unread_count(db: Session, user_id: int, conversation_id: int, read_index: int) -> int:
    """未读数 = 用户链上该会话中 seq > read_index、且未被我删除的普通消息条数。

    已删除的消息用 `kind="delete"` 墓碑标记,这里必须一起排除,否则会出现
    「历史里已经看不到、未读数却还算着它」的口径矛盾。
    """
    return int(
        db.scalar(
            select(func.count(InboxMessage.id)).where(
                InboxMessage.user_id == user_id,
                InboxMessage.conversation_id == conversation_id,
                InboxMessage.id > read_index,
                InboxMessage.kind == "message",
                InboxMessage.msg_id.not_in(deleted_msg_ids(user_id)),
            )
        )
        or 0
    )
