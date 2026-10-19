"""仓库级 pytest 引导。

这里做两件事,顺序很重要:

1. 把 backend/ 加入 sys.path,使 `app` 包可被导入 —— 这样测试可以从**仓库根目录**
   运行,覆盖率报告里的路径才会是 `backend/app/...` 这种相对仓库根的路径。
   SonarQube 扫描源码时用的也是相对仓库根的路径,两边必须一致,否则覆盖率显示为 0。

2. 隔离数据库。必须在导入任何 app 模块之前完成:应用在 `app.db.base` 导入时
   就用 settings.database_url 建好了 engine。若不隔离,测试会读写开发用的
   backend/potato.db。
"""

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# ---- 1. 让 app 包可导入(先于任何 app 导入) ----
_BACKEND = str(REPO_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# ---- 2. 隔离数据库(先于任何 app 导入) ----
# 用绝对路径的临时文件而非内存库:SQLite 内存库在跨连接/跨线程时不共享,
# 而 TestClient 会在线程池中访问连接(check_same_thread=False)。
_TMP_DB_FD, _TMP_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="potato-test-")
os.close(_TMP_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB_PATH}"
os.environ.setdefault("APP_ENV", "test")
# 长度需 >= 32 字节,否则 PyJWT 会给出 InsecureKeyLengthWarning
os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest-0123456789abcdef")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    """会话结束后清理临时库文件。"""
    try:
        engine.dispose()
    except Exception:
        pass
    if os.path.exists(_TMP_DB_PATH):
        try:
            os.remove(_TMP_DB_PATH)
        except OSError:
            pass


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    """整个测试会话共用一套表结构(与生产一致的 create_all 行为)。"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client() -> TestClient:
    """FastAPI 测试客户端,走真实的依赖注入与异常处理。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_database():
    """每个用例结束后清空所有表。

    否则用例之间会因残留账号/会话互相污染
    (例如 register 重复名用例会让后续同名注册失败)。
    先删子表再删主表,避免外键约束问题。
    """
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
