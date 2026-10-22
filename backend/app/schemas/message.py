"""消息与同步相关模型。"""

from typing import Optional

from pydantic import BaseModel, Field


class MessageOut(BaseModel):
    msg_id: int
    conversation_id: int
    sender_id: Optional[int] = None
    body: str
    reply_to: Optional[int] = None
    create_time: int
    # 该消息在**当前用户**用户链上的序号(仅历史查询会带)。
    # 客户端上报已读时必须用它,而不是全局的 msg_id(见 docs/02 第 6 节)。
    seq: Optional[int] = None


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4096, description="纯文本消息")
    reply_to: Optional[int] = Field(default=None, description="被回复消息 msg_id")


class HistoryOut(BaseModel):
    """会话历史(游标翻页):next_cursor 为空表示没有更早消息。"""

    items: list[MessageOut]
    next_cursor: Optional[int] = None


class ReadIn(BaseModel):
    read_index: int = Field(ge=0, description="我的用户链上最后已读消息的 seq")


class SyncItemOut(BaseModel):
    """用户链条目:kind=message 时 data 为消息本体;kind=recall/read/delete 为命令消息。

    `kind="delete"` 表示「我在某设备删除的这条消息」,data 带 `{msg_id, conversation_id}`,
    客户端据此从本地列表移除;这样离线端补拉时也能拿到删除,不会出现历史里复活。
    """

    seq: int
    kind: str
    conversation_id: int
    data: Optional[dict] = None


class SyncOut(BaseModel):
    items: list[SyncItemOut]
    next_cursor: Optional[int] = None