"""用户表:对应需求文档 user(user_id, name, password, register_time, login_time)。"""

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import IntPK, Base


class User(Base):
    __tablename__ = "user"

    user_id: Mapped[int] = mapped_column(IntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    # bcrypt 加盐哈希(72 字节内),任何接口不得返回此字段
    password: Mapped[str] = mapped_column(String(72), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(255), default=None)
    email: Mapped[str | None] = mapped_column(String(128), default=None)
    phone: Mapped[str | None] = mapped_column(String(32), default=None)
    register_time: Mapped[int] = mapped_column(Integer, nullable=False)
    login_time: Mapped[int | None] = mapped_column(Integer, default=None)