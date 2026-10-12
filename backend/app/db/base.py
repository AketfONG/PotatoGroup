"""SQLAlchemy 引擎 / 会话 / 模型基类。

通过 DATABASE_URL 切换 SQLite(本地)/ MySQL(生产),见 docs/03-数据库设计.md。
"""

from sqlalchemy import BigInteger, Integer, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# SQLite 仅对 INTEGER PRIMARY KEY 自增,BIGINT 主键需降级为 INTEGER(MySQL 下仍为 BIGINT)
IntPK = BigInteger().with_variant(Integer(), "sqlite")

connect_args = {}
if settings.database_url.startswith("sqlite"):
    # SQLite 需要 allow thread reuse(FastAPI 线程池中访问连接)
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass