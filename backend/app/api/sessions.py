from __future__ import annotations

import datetime as dt
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession

from ..core.deps import get_current_user, get_db, require_roles
from ..models.db import ChipOp, ChipPurchase, Seat, Session, Table, User
from ..models.schemas import ChipCreateIn, SeatAssignIn, SeatOut, SessionCreateIn, SessionOut, UndoIn

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _role(user):
    return cast(str, user.role)


def _as_int(v, default=0):
    if v is None:
        return int(default)
    return int(cast(int, v))


def _resolve_table_id(user, table_id):
    if _role(user) == "superadmin":
        if table_id is None:
            raise HTTPException(status_code=400, detail="table_id is required for superadmin")
        return int(table_id)

    if user.table_id is None:
        raise HTTPException(status_code=403, detail="No table assigned")

    tid = _as_int(user.table_id)
    if table_id is not None and int(table_id) != tid:
        raise HTTPException(status_code=403, detail="Forbidden for this table")
    return tid


def _require_session_access(user, session):
    if _role(user) == "superadmin":
        return
    if user.table_id is None:
        raise HTTPException(status_code=403, detail="No table assigned")
    if _as_int(user.table_id) != _as_int(session.table_id):
        raise HTTPException(status_code=403, detail="Forbidden for this table")


@router.get(
    "/open",
    response_model=SessionOut | None,
    dependencies=[Depends(require_roles("superadmin", "dealer", "table_admin"))],
)
def get_open_session(
    table_id: int | None = Query(default=None),
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tid = _resolve_table_id(user, table_id)
    s = (
        db.query(Session)
        .filter(Session.table_id == tid, Session.status == "open")
        .order_by(Session.created_at.desc())
        .first()
    )
    return SessionOut.model_validate(s) if s else None


@router.post(
    "",
    response_model=SessionOut,
    dependencies=[Depends(require_roles("superadmin", "dealer", "table_admin"))],
)
def create_session(
    payload: SessionCreateIn,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tid = _resolve_table_id(user, payload.table_id)
    date = payload.date or dt.date.today()

    table = db.query(Table).filter(Table.id == tid).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    existing = (
        db.query(Session)
        .filter(Session.table_id == tid, Session.status == "open")
        .order_by(Session.created_at.desc())
        .first()
    )
    if existing:
        return SessionOut.model_validate(existing)

    seats_count = int(payload.seats_count) if payload.seats_count is not None else _as_int(table.seats_count)

    s = Session(table_id=tid, date=date, status=cast(Any, "open"))
    db.add(s)
    db.flush()

    for seat_no in range(1, seats_count + 1):
        db.add(
            Seat(
                session_id=cast(Any, s.id),
                seat_no=cast(Any, seat_no),
                player_name=cast(Any, None),
                total=cast(Any, 0),
            )
        )

    db.commit()
    db.refresh(s)
    return SessionOut.model_validate(s)


@router.get(
    "/{session_id}/seats",
    response_model=list[SeatOut],
    dependencies=[Depends(require_roles("superadmin", "dealer", "table_admin"))],
)
def list_seats(
    session_id: str,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.query(Session).filter(Session.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    _require_session_access(user, s)

    seats = (
        db.query(Seat)
        .filter(Seat.session_id == session_id)
        .order_by(Seat.seat_no.asc())
        .all()
    )
    return [SeatOut.model_validate(x) for x in seats]


@router.put(
    "/{session_id}/seats/{seat_no}",
    response_model=SeatOut,
    dependencies=[Depends(require_roles("superadmin", "dealer", "table_admin"))],
)
def assign_player(
    session_id: str,
    seat_no: int,
    payload: SeatAssignIn,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.query(Session).filter(Session.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    _require_session_access(user, s)

    seat = (
        db.query(Seat)
        .filter(Seat.session_id == session_id, Seat.seat_no == seat_no)
        .first()
    )
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")

    seat.player_name = cast(Any, payload.player_name)
    db.commit()
    db.refresh(seat)
    return SeatOut.model_validate(seat)


@router.post(
    "/{session_id}/chips",
    response_model=SeatOut,
    dependencies=[Depends(require_roles("superadmin", "dealer", "table_admin"))],
)
def add_chips(
    session_id: str,
    payload: ChipCreateIn,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.query(Session).filter(Session.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    _require_session_access(user, s)

    seat = (
        db.query(Seat)
        .filter(Seat.session_id == session_id, Seat.seat_no == payload.seat_no)
        .first()
    )
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")

    seat_total = _as_int(seat.total)
    delta = int(payload.amount)
    seat.total = cast(Any, seat_total + delta)

    op = ChipOp(
        session_id=cast(Any, session_id),
        seat_no=cast(Any, payload.seat_no),
        amount=cast(Any, delta),
    )
    db.add(op)
    db.flush()

    purchase = ChipPurchase(
        table_id=_as_int(s.table_id),
        session_id=str(cast(str, s.id)),
        seat_no=int(payload.seat_no),
        amount=delta,
        chip_op_id=_as_int(op.id),
        created_by_user_id=_as_int(user.id),
    )
    db.add(purchase)

    db.commit()
    db.refresh(seat)
    return SeatOut.model_validate(seat)


@router.post(
    "/{session_id}/chips/undo",
    response_model=SeatOut,
    dependencies=[Depends(require_roles("superadmin", "dealer", "table_admin"))],
)
def undo_last(
    session_id: str,
    payload: UndoIn,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.query(Session).filter(Session.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    _require_session_access(user, s)

    seat = (
        db.query(Seat)
        .filter(Seat.session_id == session_id, Seat.seat_no == payload.seat_no)
        .first()
    )
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")

    last = (
        db.query(ChipOp)
        .filter(ChipOp.session_id == session_id, ChipOp.seat_no == payload.seat_no)
        .order_by(ChipOp.id.desc())
        .first()
    )
    if not last:
        raise HTTPException(status_code=400, detail="No history")

    seat.total = cast(Any, _as_int(seat.total) - _as_int(last.amount))

    purchase = db.query(ChipPurchase).filter(ChipPurchase.chip_op_id == last.id).first()
    if purchase:
        db.delete(purchase)

    db.delete(last)
    db.commit()
    db.refresh(seat)
    return SeatOut.model_validate(seat)


@router.post(
    "/{session_id}/close",
    response_model=SessionOut,
    dependencies=[Depends(require_roles("superadmin", "dealer", "table_admin"))],
)
def close_session(
    session_id: str,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.query(Session).filter(Session.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    _require_session_access(user, s)

    s.status = cast(Any, "closed")
    db.commit()
    db.refresh(s)
    return SessionOut.model_validate(s)
