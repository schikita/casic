from __future__ import annotations

import datetime as dt
import uuid

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

from ..core.datetime_utils import utc_now

Base = declarative_base()


class Table(Base):
    __tablename__ = "tables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), unique=True, nullable=False)
    seats_count = Column(Integer, nullable=False, default=24)

    sessions = relationship("Session", back_populates="table", cascade="all, delete-orphan")

    __table_args__ = (
        # Ensure seats_count is positive
        # Note: Check constraints are not supported in SQLite
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # Nullable for dealer/waiter roles
    role = Column(String(32), nullable=False)  # superadmin | table_admin | dealer | waiter
    table_id = Column(Integer, ForeignKey("tables.id"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    hourly_rate = Column(Integer, nullable=True)  # Hourly rate in chips for dealer/waiter

    table = relationship("Table")

    __table_args__ = (
        # Note: Check constraints for role and hourly_rate are not supported in SQLite
    )


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    table_id = Column(Integer, ForeignKey("tables.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    status = Column(String(16), nullable=False, default="open", index=True)  # open|closed
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    closed_at = Column(DateTime, nullable=True)  # When session was closed

    # Staff assignments
    dealer_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    waiter_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Chips in play tracking (informational only)
    chips_in_play = Column(Integer, nullable=False, default=0)  # Current chip count on table (auto-incremented)

    table = relationship("Table", back_populates="sessions")
    seats = relationship("Seat", back_populates="session", cascade="all, delete-orphan")
    ops = relationship("ChipOp", back_populates="session", cascade="all, delete-orphan")
    dealer = relationship("User", foreign_keys=[dealer_id])
    waiter = relationship("User", foreign_keys=[waiter_id])

    # Note: We don't use a unique constraint on (table_id, date, status) because
    # it would prevent multiple closed sessions for the same table/date.
    # Instead, we enforce "only one open session per table" in application logic.


class Seat(Base):
    __tablename__ = "seats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    seat_no = Column(Integer, nullable=False)
    player_name = Column(String(255), nullable=True)
    total = Column(Integer, nullable=False, default=0)

    session = relationship("Session", back_populates="seats")

    __table_args__ = (
        UniqueConstraint("session_id", "seat_no", name="uq_seat_session_seatno"),
        Index("ix_seat_session_seat", "session_id", "seat_no"),
        # Note: Check constraints for seat_no and total are not supported in SQLite
    )


class ChipOp(Base):
    __tablename__ = "chip_ops"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    seat_no = Column(Integer, nullable=False)
    amount = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    session = relationship("Session", back_populates="ops")
    
    
class ChipPurchase(Base):
    __tablename__ = "chip_purchases"

    id = Column(Integer, primary_key=True, autoincrement=True)

    table_id = Column(Integer, ForeignKey("tables.id"), nullable=False, index=True)

    # IMPORTANT: type must match sessions.id
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)

    seat_no = Column(Integer, nullable=False, index=True)
    amount = Column(Integer, nullable=False)

    chip_op_id = Column(Integer, ForeignKey("chip_ops.id"), nullable=False, unique=True, index=True)

    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Payment type: "cash" or "credit"
    payment_type = Column(String(16), nullable=False, default="cash")

    table = relationship("Table")
    session = relationship("Session")
    created_by = relationship("User")
    chip_op = relationship("ChipOp")

    __table_args__ = (
        UniqueConstraint("chip_op_id", name="uq_chip_purchases_chip_op_id"),
    )


class CasinoBalanceAdjustment(Base):
    __tablename__ = "casino_balance_adjustments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Timestamp of when the adjustment was made
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    
    # Amount (positive for profit, negative for expense)
    amount = Column(Integer, nullable=False)
    
    # Text comment explaining the adjustment
    comment = Column(Text, nullable=False)
    
    # User who made the adjustment
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    created_by = relationship("User")
