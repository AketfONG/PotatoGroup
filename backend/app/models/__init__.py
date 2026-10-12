"""ORM 模型汇总导入;表结构说明见 docs/03-数据库设计.md。"""

from app.db.base import Base
from app.models.user import User
from app.models.friend import Friend, FriendRequest
from app.models.conversation import Conversation, ConversationMember
from app.models.message import Message
from app.models.inbox import InboxMessage

__all__ = [
    "Base",
    "User",
    "Friend",
    "FriendRequest",
    "Conversation",
    "ConversationMember",
    "Message",
    "InboxMessage",
]