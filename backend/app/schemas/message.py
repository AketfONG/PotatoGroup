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
    """用户链条目:kind=message 时 data 为消息本体;kind=recall/read/delete 为命令消息。"""

    seq: int
    kind: str
    conversation_id: int
    data: Optional[dict] = None


class SyncOut(BaseModel):
    items: list[SyncItemOut]
    next_cursor: Optional[int] = None