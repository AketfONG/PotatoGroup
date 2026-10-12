"""会话相关模型:单聊/群聊统一抽象。"""

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.message import MessageOut
from app.schemas.user import UserSummary


class MemberOut(BaseModel):
    user: UserSummary
    role: str  # owner / admin / member
    join_time: int


class ConversationOut(BaseModel):
    """会话详情。"""

    conversation_id: int
    name: Optional[str] = None
    type: str  # private / group
    avatar: Optional[str] = None
    owner_id: Optional[int] = None
    announcement: Optional[str] = None
    members: list[MemberOut]
    create_time: int
    update_time: int


class ConversationItemOut(BaseModel):
    """会话列表条目:含未读数/置顶/免打扰/最新一条消息。"""

    conversation_id: int
    name: Optional[str] = None
    type: str
    avatar: Optional[str] = None
    member_count: int
    last_msg: Optional[MessageOut] = None
    unread_count: int
    pinned: bool
    muted: bool
    update_time: int


class ConversationListOut(BaseModel):
    items: list[ConversationItemOut]


class CreateGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    member_ids: list[int] = Field(min_length=1, description="从好友中选择的初始成员")


class CreatePrivateIn(BaseModel):
    target_user_id: int = Field(gt=0, description="必须是好友")


class ConversationUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    announcement: Optional[str] = Field(default=None, max_length=2048)


class MemberAddIn(BaseModel):
    user_ids: list[int] = Field(min_length=1, description="被邀请者需为邀请人的好友")


class MemberSettingsIn(BaseModel):
    pinned: Optional[bool] = None
    muted: Optional[bool] = None