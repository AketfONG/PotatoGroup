"""用户链(写扩散):每条消息为每个成员复制一行,kind 同时承载命令消息。

cursor 兜底拉取 / prev_seq 一致性校验均以本表自增 id(即 seq)为准。
"""

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPK


class InboxMessage(Base):
    __tablename__ = "inbox_message"

    # 用户链序号 seq:单用户内递增(全局自增保证递增)
    id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.user_id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("conversation.conversation_id", ondelete="CASCADE"), index=True, nullable=False
    )
    msg_id: Mapped[int | None] = mapped_column(BigInteger, default=None)  # 指向消息本体
    # message / recall / read / delete(命令消息对用户不可见)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="message")
    payload: Mapped[dict | None] = mapped_column(JSON, default=None)  # 命令消息附加数据
    create_time: Mapped[int] = mapped_column(Integer, nullable=False)