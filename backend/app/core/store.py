from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict
from uuid import UUID

from ..models.entities import SessionEntity, SeatEntity


@dataclass
class InMemoryStore:
    open_session: SessionEntity | None = None
    seats: Dict[int, SeatEntity] = field(default_factory=dict)  # key = seat_no


store = InMemoryStore()
