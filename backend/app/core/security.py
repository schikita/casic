from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from jose import JWTError, ExpiredSignatureError, jwt
from passlib.context import CryptContext

from .config import settings


pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    subject: str,
    role: str,
    table_id: int | None,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=int(settings.JWT_EXPIRES_MINUTES))
    )

    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "table_id": table_id,
        "exp": expire,
    }

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "sub": str(sub),
        "role": payload.get("role"),
        "table_id": payload.get("table_id"),
    }
