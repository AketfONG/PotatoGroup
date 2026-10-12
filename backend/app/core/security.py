"""安全工具:密码加盐哈希(bcrypt)与 JWT 签发/校验。

课程讲义要求:密码严禁明文存储,使用成熟官方库,禁止手搓加密。
"""

import time

import bcrypt
import jwt

from app.core.config import settings


def hash_password(plain: str) -> str:
    """bcrypt 自动加盐哈希。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": int(time.time()) + settings.jwt_expire_days * 86400,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> int:
    """校验并解析 token,返回 user_id;失败抛出 jwt.InvalidTokenError。"""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return int(payload["sub"])