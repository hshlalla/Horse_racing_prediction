import base64
import datetime
import hashlib
import os
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "iat": datetime.datetime.now(datetime.UTC)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return int(payload["sub"])
    except JWTError as exc:
        raise ValueError(str(exc)) from exc


def generate_refresh_token() -> tuple[str, str]:
    raw = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
