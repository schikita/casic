from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, get_db
from ..core.security import create_access_token, verify_password
from ..models.db import User
from ..models.schemas import LoginIn, LoginOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _as_str(v: Any) -> str:
    return cast(str, v)


def _as_bool(v: Any) -> bool:
    return bool(cast(bool, v))


def _as_int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    return int(cast(int, v))


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> LoginOut:
    user = db.query(User).filter(User.username == payload.username.strip()).first()

    # user.is_active для Pylance = Column[bool], поэтому приводим к bool
    if (user is None) or (not _as_bool(user.is_active)):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Prevent dealer and waiter from logging in
    user_role = _as_str(user.role)
    if user_role in ("dealer", "waiter"):
        raise HTTPException(status_code=403, detail="Dealer and waiter accounts cannot log in to the app")

    password_hash = _as_str(user.password_hash)
    if not verify_password(payload.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(
        subject=str(_as_int_or_none(user.id) or 0),
        role=user_role,
        table_id=_as_int_or_none(user.table_id),
    )
    return LoginOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
