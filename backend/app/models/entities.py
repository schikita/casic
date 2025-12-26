from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from uuid import UUID


@dataclass
class SeatEntity:
    seat_no: int
    player_name: str | None = None
    total: int = 0
    history: list[dict] = field(default_factory=list)


@dataclass
class SessionEntity:
    id: UUID
    date: date
    status: str = "open"
    created_at: datetime = field(default_factory=datetime.utcnow)
