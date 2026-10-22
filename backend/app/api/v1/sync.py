"""兜底拉取:基于用户链 seq 的增量同步。

在线用户优先走 WebSocket 推送;断线/离线/发现 cursor 缺口时调用本接口补拉,
保证消息不丢(需求文档"消息送达可靠性")。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models import InboxMessage, Message, User
from app.schemas.common import ApiResponse, ok
from app.schemas.message import SyncItemOut, SyncOut
from app.services import message_service

router = APIRouter(prefix="/sync", tags=["同步"])


@router.get("", response_model=ApiResponse[SyncOut])
async def sync(
    cursor: int = Query(default=0, ge=0, description="本地已有的最新 seq,拉取其后的消息"),
    limit: int = Query(default=100, ge=1, le=200),
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """增量拉取我的用户链:首次登录 cursor=0 全量;离线补拉 cursor=本地最后 seq。

    条目语义:kind=message 为普通消息;kind=recall/read/delete 为命令消息(前端据此更新本地状态)。

    我已经删除的消息不会再以 kind="message" 回来(与历史查询同一口径);删除本身由
    kind="delete" 命令消息表达,`data` 带 `{msg_id, conversation_id}`。删除后重写的墓碑行
    沿用原 seq,故不会因为过滤而让 cursor 出现空洞。
    """
    rows = list(
        db.scalars(
            select(InboxMessage)
            .where(
                InboxMessage.user_id == me.user_id,
                InboxMessage.id > cursor,
                # 已删除的投递记录不再当作新消息下发(墓碑行会另行返回)
                ~(
                    (InboxMessage.kind == "message")
                    & InboxMessage.msg_id.in_(message_service.deleted_msg_ids(me.user_id))
                ),
            )
            .order_by(InboxMessage.id.asc())
            .limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items: list[SyncItemOut] = []
    for r in rows:
        data = None
        if r.kind == "message" and r.msg_id is not None:
            m = db.get(Message, r.msg_id)
            if m is not None:
                data = {
                    "msg_id": m.msg_id,
                    "conversation_id": m.conversation_id,
                    "sender_id": m.sender_id,
                    "body": m.body,
                    "reply_to": m.reply_to,
                    "create_time": m.create_time,
                }
        else:
            data = r.payload
        items.append(SyncItemOut(seq=r.id, kind=r.kind, conversation_id=r.conversation_id, data=data))
    return ok(SyncOut(items=items, next_cursor=rows[-1].id if has_more and rows else None))