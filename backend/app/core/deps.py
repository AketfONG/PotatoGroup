"""通用依赖:数据库会话与当前登录用户。"""

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import unauthorized
from app.db.base import SessionLocal
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """REST 鉴权依赖:校验 JWT 并加载用户。"""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized("缺少 Bearer token")
    try:
        user_id = security.decode_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise unauthorized("token 无效或已过期")
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized("用户不存在")
    return user