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
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Table(Base):
    __tablename__ = "tables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), unique=True, nullable=False)
    seats_count = Column(Integer, nullable=False, default=24)

    sessions = relationship("Session", back_populates="table", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False)  # superadmin | table_admin | dealer
    table_id = Column(Integer, ForeignKey("tables.id"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    table = relationship("Table")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    table_id = Column(Integer, ForeignKey("tables.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    status = Column(String(16), nullable=False, default="open")  # open|closed
    created_at = Column(DateTime, nullable=False, default=lambda: dt.datetime.utcnow())

    table = relationship("Table", back_populates="sessions")
    seats = relationship("Seat", back_populates="session", cascade="all, delete-orphan")
    ops = relationship("ChipOp", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("table_id", "date", "status", name="uq_session_table_date_status"),
    )


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
    )


class ChipOp(Base):
    __tablename__ = "chip_ops"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    seat_no = Column(Integer, nullable=False)
    amount = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: dt.datetime.utcnow())

    session = relationship("Session", back_populates="ops")
    
    
class ChipPurchase(Base):
    __tablename__ = "chip_purchases"

    id = Column(Integer, primary_key=True, autoincrement=True)

    table_id = Column(Integer, ForeignKey("tables.id"), nullable=False, index=True)

    # ВАЖНО: тип должен совпадать с sessions.id
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)

    seat_no = Column(Integer, nullable=False, index=True)
    amount = Column(Integer, nullable=False)

    chip_op_id = Column(Integer, ForeignKey("chip_ops.id"), nullable=False, unique=True, index=True)

    created_at = Column(DateTime, nullable=False, default=dt.datetime.utcnow, index=True)

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    table = relationship("Table")
    session = relationship("Session")
    created_by = relationship("User")
    chip_op = relationship("ChipOp")

    __table_args__ = (
        UniqueConstraint("chip_op_id", name="uq_chip_purchases_chip_op_id"),
    )
