from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4, UUID

from ..core.store import store
from ..models.entities import SessionEntity, SeatEntity


class SessionService:
    @staticmethod
    def create_session(seats_count: int, session_date: date | None = None) -> SessionEntity:
        if store.open_session and store.open_session.status == "open":
            return store.open_session

        session_date = session_date or date.today()
        s = SessionEntity(id=uuid4(), date=session_date, status="open", created_at=datetime.utcnow())
        store.open_session = s

        # reset seats
        store.seats = {i: SeatEntity(seat_no=i) for i in range(1, seats_count + 1)}
        return s

    @staticmethod
    def get_open_session() -> SessionEntity | None:
        return store.open_session if store.open_session and store.open_session.status == "open" else None

    @staticmethod
    def require_open_session(session_id: UUID) -> SessionEntity:
        s = store.open_session
        if not s or s.id != session_id or s.status != "open":
            raise ValueError("Session not found or not open")
        return s

    @staticmethod
    def close_session(session_id: UUID) -> SessionEntity:
        s = store.open_session
        if not s or s.id != session_id:
            raise ValueError("Session not found")
        s.status = "closed"
        return s

    @staticmethod
    def list_seats(session_id: UUID) -> list[SeatEntity]:
        SessionService.require_open_session(session_id)
        return [store.seats[i] for i in sorted(store.seats.keys())]

    @staticmethod
    def assign_player(session_id: UUID, seat_no: int, player_name: str | None) -> SeatEntity:
        SessionService.require_open_session(session_id)
        seat = store.seats.get(seat_no)
        if not seat:
            raise ValueError("Invalid seat")
        seat.player_name = (player_name.strip() if player_name else None)
        return seat

    @staticmethod
    def add_chips(session_id: UUID, seat_no: int, amount: int) -> SeatEntity:
        SessionService.require_open_session(session_id)
        seat = store.seats.get(seat_no)
        if not seat:
            raise ValueError("Invalid seat")

        seat.total += amount
        seat.history.append({"amount": amount, "at": datetime.utcnow().isoformat()})
        return seat

    @staticmethod
    def undo_last(session_id: UUID, seat_no: int) -> SeatEntity:
        SessionService.require_open_session(session_id)
        seat = store.seats.get(seat_no)
        if not seat:
            raise ValueError("Invalid seat")

        if not seat.history:
            raise ValueError("No history")

        last = seat.history.pop()
        seat.total -= int(last["amount"])
        return seat
