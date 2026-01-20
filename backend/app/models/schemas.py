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
    seats_count: int = Field(default=10, ge=1, le=10)


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str | None = Field(default=None, min_length=4, max_length=128)
    role: UserRole
    table_id: int | None = None
    is_active: bool = True
    hourly_rate: int | None = None


class UserUpdateIn(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=64)
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
    seats_count: int = Field(default=10, ge=1, le=10)
    dealer_id: int | None = None  # Required for session start (validated in endpoint)
    waiter_id: int | None = None  # Optional
    chips_in_play: int = Field(default=0, ge=0)  # Initial chip count on table (informational)


class StaffOut(BaseModel):
    id: int
    username: str
    role: UserRole
    hourly_rate: int | None

    class Config:
        from_attributes = True


class DealerRakeEntryOut(BaseModel):
    """Output schema for a single rake entry."""
    id: int
    amount: int
    created_at: dt.datetime
    created_by_username: str | None = None

    class Config:
        from_attributes = True


class SessionDealerAssignmentOut(BaseModel):
    """Output schema for dealer assignment within a session."""
    id: int
    dealer_id: int
    dealer_username: str
    dealer_hourly_rate: int | None = None  # Hourly rate for earnings calculation
    started_at: dt.datetime
    ended_at: dt.datetime | None = None
    rake: int | None = None  # Rake attributed to this dealer during their shift
    rake_entries: list[DealerRakeEntryOut] = []  # Individual rake entries for audit trail

    class Config:
        from_attributes = True


class ReplaceDealerIn(BaseModel):
    """Input schema for replacing a dealer in a session."""
    new_dealer_id: int = Field(..., description="ID of the new dealer to assign")
    outgoing_dealer_rake: int = Field(..., ge=0, description="Rake amount brought by the outgoing dealer during their shift")


class AddDealerIn(BaseModel):
    """Input schema for adding a dealer to a session (concurrent dealers)."""
    dealer_id: int = Field(..., description="ID of the dealer to add")


class RemoveDealerIn(BaseModel):
    """Input schema for removing a dealer from a session."""
    assignment_id: int = Field(..., description="ID of the dealer assignment to end")
    rake: int = Field(..., ge=0, description="Rake amount brought by this dealer during their shift")


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
    # List of all dealer assignments for this session (for salary tracking)
    dealer_assignments: list[SessionDealerAssignmentOut] = []

    class Config:
        from_attributes = True


class SeatOut(BaseModel):
    seat_no: int
    player_name: str | None
    total: int
    cash: int = 0  # Cash portion of total
    credit: int = 0  # Credit portion of total
    total_chips_played: int = 0  # Sum of all chip purchases (cash + credit)

    class Config:
        from_attributes = True


class SeatAssignIn(BaseModel):
    player_name: str | None


class SeatHistoryEntryOut(BaseModel):
    """Single entry in seat history."""
    type: str  # "name_change", "chip_adjustment", or "player_left"
    created_at: dt.datetime
    # For name changes and player_left
    old_name: str | None = None
    new_name: str | None = None
    # For chip adjustments
    amount: int | None = None
    payment_type: str | None = None  # "cash" or "credit"
    created_by_username: str | None = None


class SeatHistoryOut(BaseModel):
    """History for a single seat."""
    seat_no: int
    player_name: str | None
    entries: list[SeatHistoryEntryOut]


class ChipCreateIn(BaseModel):
    seat_no: int = Field(ge=1, le=10)
    amount: int
    payment_type: str = Field(default="cash", pattern="^(cash|credit)$")  # "cash" or "credit"


class UndoIn(BaseModel):
    seat_no: int = Field(ge=1, le=10)


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


class DealerRakeIn(BaseModel):
    """Input schema for dealer rake amount when closing session."""
    assignment_id: int = Field(..., description="ID of the dealer assignment")
    rake: int = Field(..., ge=0, description="Rake amount brought by this dealer during their shift")


class CloseSessionIn(BaseModel):
    """Input schema for closing a session with dealer rake amounts."""
    dealer_rakes: list[DealerRakeIn] = Field(..., description="Rake amounts for each active dealer")


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
    # Dealer assignments with hours worked
    dealer_assignments: list[SessionDealerAssignmentOut] = []

    class Config:
        from_attributes = True


class CloseCreditIn(BaseModel):
    session_id: str
    seat_no: int = Field(..., ge=1, le=10)
    amount: int = Field(..., gt=0, description="Amount of credit to close")


class CloseCreditOut(BaseModel):
    success: bool
    message: str
    adjustment_id: int | None = None
