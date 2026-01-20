from __future__ import annotations

from typing import Any, Callable, cast

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DBSession

from .db import SessionLocal
from .security import decode_token
from ..models.db import User


bearer = HTTPBearer(auto_error=False)


def _as_bool(v: Any) -> bool:
    return bool(cast(bool, v))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    db: DBSession = Depends(get_db),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(creds.credentials)

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # id может быть int или str — нормализуем
    try:
        user_id = int(sub)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not _as_bool(user.is_active):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return user


def require_roles(*roles: str) -> Callable[[User], User]:
    allowed = set(roles)

    def _dep(user: User = Depends(get_current_user)) -> User:
        role = cast(str, user.role)
        if role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _dep


def get_owner_id_for_filter(user: User) -> int | None:
    """
    Get the owner_id to use for filtering queries based on user role.

    - superadmin: returns None (no filtering, sees all data)
    - table_admin: returns their own user.id (they are the owner of their casino)
    - dealer/waiter: returns their owner_id (the table_admin who created them)

    Returns:
        owner_id for filtering, or None for superadmin (no filter needed)
    """
    role = cast(str, user.role)
    if role == "superadmin":
        return None
    if role == "table_admin":
        return int(cast(int, user.id))
    # For dealer/waiter, return their owner_id
    return int(cast(int, user.owner_id)) if user.owner_id is not None else None
