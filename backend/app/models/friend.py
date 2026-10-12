"""好友关系表(双向两行存储)与好友申请表(功能需求扩展)。"""

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPK


class Friend(Base):
    """好友关系:A、B 成为好友时插入 (A,B) 与 (B,A) 两行,拉列表恒为单表单条件查询。"""

    __tablename__ = "friend"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.user_id", ondelete="CASCADE"), primary_key=True
    )
    friend_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.user_id", ondelete="CASCADE"), primary_key=True
    )
    remark: Mapped[str | None] = mapped_column(String(64), default=None)  # 好友备注
    group_name: Mapped[str | None] = mapped_column(String(32), default=None)  # 自定义分组
    update_time: Mapped[int] = mapped_column(Integer, nullable=False)


class FriendRequest(Base):
    """好友申请:申请-同意后写入 friend 两行。"""

    __tablename__ = "friend_request"

    request_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    from_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.user_id", ondelete="CASCADE"), index=True, nullable=False
    )
    to_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.user_id", ondelete="CASCADE"), index=True, nullable=False
    )
    # pending / accepted / rejected
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    create_time: Mapped[int] = mapped_column(Integer, nullable=False)
    update_time: Mapped[int] = mapped_column(Integer, nullable=False)