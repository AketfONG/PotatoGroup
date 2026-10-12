"""消息表:会话链(会话维度)存储,支撑历史消息拉取(新成员可见入群前历史)。"""

from sqlalchemy import BigInteger, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPK


class Message(Base):
    __tablename__ = "message"

    msg_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("conversation.conversation_id", ondelete="CASCADE"), index=True, nullable=False
    )
    sender_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.user_id", ondelete="SET NULL"), index=True, nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)  # 骨架阶段为纯文本
    reply_to: Mapped[int | None] = mapped_column(BigInteger, default=None)  # 被回复消息 msg_id
    create_time: Mapped[int] = mapped_column(Integer, index=True, nullable=False)