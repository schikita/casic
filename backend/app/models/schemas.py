from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


UserRole = Literal["superadmin", "table_admin", "dealer", "waiter"]


class UserOut(BaseModel):
    id: int
    username: str
    role: UserRole
    table_id: int | None
    is_active: bool
    hourly_rate: int | None

    class Config:
        from_attributes = True


class TableOut(BaseModel):
    id: int
    name: str
    seats_count: int

    class Config:
        from_attributes = True


class TableCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    seats_count: int = Field(default=24, ge=1, le=60)


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=4, max_length=128)
    role: UserRole
    table_id: int | None = None
    is_active: bool = True
    hourly_rate: int | None = None


class UserUpdateIn(BaseModel):
    password: str | None = Field(default=None, min_length=4, max_length=128)
    role: UserRole | None = None
    table_id: int | None = None
    is_active: bool | None = None
    hourly_rate: int | None = None


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SessionCreateIn(BaseModel):
    table_id: int | None = None
    date: dt.date | None = None
    seats_count: int = Field(default=24, ge=1, le=60)
    dealer_id: int | None = None  # Required for session start (validated in endpoint)
    waiter_id: int | None = None  # Optional


class StaffOut(BaseModel):
    id: int
    username: str
    role: UserRole

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    id: str
    table_id: int
    date: dt.date
    status: str
    created_at: dt.datetime
    dealer_id: int | None = None
    waiter_id: int | None = None
    dealer: StaffOut | None = None
    waiter: StaffOut | None = None

    class Config:
        from_attributes = True


class SeatOut(BaseModel):
    seat_no: int
    player_name: str | None
    total: int

    class Config:
        from_attributes = True


class SeatAssignIn(BaseModel):
    player_name: str | None


class ChipCreateIn(BaseModel):
    seat_no: int = Field(ge=1, le=60)
    amount: int


class UndoIn(BaseModel):
    seat_no: int = Field(ge=1, le=60)


class ChipPurchaseOut(BaseModel):
    id: int
    table_id: int
    table_name: str
    session_id: str | None
    seat_no: int
    amount: int
    created_at: dt.datetime
    created_by_user_id: int | None
    created_by_username: str | None
