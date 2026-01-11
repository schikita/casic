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
    password: str | None = Field(default=None, min_length=4, max_length=128)
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
    chips_in_play: int = Field(default=0, ge=0)  # Initial chip count on table (informational)


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
    closed_at: dt.datetime | None = None
    dealer_id: int | None = None
    waiter_id: int | None = None
    dealer: StaffOut | None = None
    waiter: StaffOut | None = None
    chips_in_play: int | None = None

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
    payment_type: str = Field(default="cash", pattern="^(cash|credit)$")  # "cash" or "credit"


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
    payment_type: str = "cash"  # "cash" or "credit"


class CasinoBalanceAdjustmentIn(BaseModel):
    amount: int = Field(..., description="Amount (positive for profit, negative for expense)")
    comment: str = Field(..., min_length=1, max_length=500, description="Comment explaining the adjustment")


class CasinoBalanceAdjustmentOut(BaseModel):
    id: int
    created_at: dt.datetime
    amount: int
    comment: str
    created_by_user_id: int
    created_by_username: str

    class Config:
        from_attributes = True


class ClosedSessionOut(BaseModel):
    id: str
    table_id: int
    table_name: str
    date: dt.date
    created_at: dt.datetime
    closed_at: dt.datetime
    dealer_id: int | None = None
    waiter_id: int | None = None
    dealer_username: str | None = None
    waiter_username: str | None = None
    chips_in_play: int | None = None
    total_rake: int = 0
    total_buyins: int = 0
    total_cashouts: int = 0
    # Credit information per player
    credits: list[dict] = []  # Each dict has: seat_no, player_name, amount

    class Config:
        from_attributes = True


class CloseCreditIn(BaseModel):
    session_id: str
    seat_no: int = Field(..., ge=1, le=60)
    amount: int = Field(..., gt=0, description="Amount of credit to close")


class CloseCreditOut(BaseModel):
    success: bool
    message: str
    adjustment_id: int | None = None
