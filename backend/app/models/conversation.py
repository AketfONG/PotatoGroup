"""会话表与会话成员表:单聊/群聊统一抽象。"""

from sqlalchemy import BigInteger, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPK


class Conversation(Base):
    __tablename__ = "conversation"

    conversation_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    # 群聊为群名;单聊为空,前端显示对方昵称
    name: Mapped[str | None] = mapped_column(String(64), default=None)
    # private / group
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="group")
    avatar: Mapped[str | None] = mapped_column(String(255), default=None)
    owner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.user_id", ondelete="SET NULL"), default=None
    )
    announcement: Mapped[str | None] = mapped_column(Text, default=None)  # 群公告
    create_time: Mapped[int] = mapped_column(Integer, nullable=False)
    # 最近消息/信息变更时间,会话列表排序依据
    update_time: Mapped[int] = mapped_column(Integer, nullable=False)


class ConversationMember(Base):
    """会话成员:read_index 为该成员用户链上最后已读消息的 seq(未读数 = 链上未读计数)。"""

    __tablename__ = "conversation_member"

    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("conversation.conversation_id", ondelete="CASCADE"), primary_key=True
    )
    member_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.user_id", ondelete="CASCADE"), primary_key=True
    )
    # owner / admin / member
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    join_time: Mapped[int] = mapped_column(Integer, nullable=False)
    update_time: Mapped[int] = mapped_column(Integer, nullable=False)
    read_index: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    pinned: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    muted: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)