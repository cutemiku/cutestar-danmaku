from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

import bcrypt
import jwt

from .config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def generate_participant_token() -> str:
    return token_urlsafe(32)


def generate_screen_key() -> str:
    """生成大屏授权密钥：不可预测的高熵随机串，明文仅申请时返回一次。"""
    return token_urlsafe(32)


def create_admin_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": "admin",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_admin_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    if payload.get("role") != "admin":
        return None
    return str(payload.get("sub") or "")
