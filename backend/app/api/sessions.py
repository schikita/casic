from __future__ import annotations

import datetime as dt
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession

from ..core.deps import get_current_user, get_db, require_roles
from ..models.db import ChipOp, ChipPurchase, Seat, Session, Table, User
from ..models.schemas import ChipCreateIn, SeatAssignIn, SeatOut, SessionCreateIn, SessionOut, StaffOut, UndoIn

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _role(user):
    return cast(str, user.role)


def _as_int(v, default=0):
    if v is None:
        return int(default)
    return int(cast(int, v))


def _resolve_table_id(user, table_id):
    role = _role(user)

    if role == "superadmin":
        if table_id is None:
            raise HTTPException(status_code=400, detail="table_id is required for superadmin")
        return int(table_id)

    if role == "dealer":
        # Dealers don't have table_id, they are assigned to sessions
        if table_id is not None:
            raise HTTPException(status_code=400, detail="Dealers cannot specify table_id")
        raise HTTPException(status_code=400, detail="Dealers must be assigned to a session")

    # table_admin and waiter have table_id
    if user.table_id is None:
        raise HTTPException(status_code=403, detail="No table assigned")

    tid = _as_int(user.table_id)
    if table_id is not None and int(table_id) != tid:
        raise HTTPException(status_code=403, detail="Forbidden for this table")
    return tid


def _require_session_access(user, session):
    role = _role(user)

    if role == "superadmin":
        return

    if role == "dealer":
        # Dealers can only access sessions they are assigned to
        if _as_int(user.id) != _as_int(session.dealer_id):
            raise HTTPException(status_code=403, detail="Forbidden for this session")
        return

    # table_admin and waiter access based on table_id
    if user.table_id is None:
        raise HTTPException(status_code=403, detail="No table assigned")
    if _as_int(user.table_id) != _as_int(session.table_id):
        raise HTTPException(status_code=403, detail="Forbidden for this table")


@router.get(
    "/available-dealers",
    response_model=list[StaffOut],
    dependencies=[Depends(require_roles("superadmin", "table_admin"))],
)
def get_available_dealers(
    db: DBSession = Depends(get_db),
):
    """
    Returns dealers not currently assigned to any active (open) session.
    Ensures exclusive assignment: one dealer can only be assigned to one session at a time.
    """
    # Get IDs of dealers currently assigned to open sessions
    assigned_dealer_ids = (
        db.query(Session.dealer_id)
        .filter(Session.status == "open", Session.dealer_id.isnot(None))
        .all()
    )
    assigned_ids = {row[0] for row in assigned_dealer_ids if row[0] is not None}

    # Get all active dealers not in the assigned list
    dealers = (
        db.query(User)
        .filter(
            User.role == "dealer",
            User.is_active == True,
            User.id.notin_(assigned_ids) if assigned_ids else True,
        )
        .order_by(User.username.asc())
        .all()
    )
    return [StaffOut.model_validate(d) for d in dealers]


@router.get(
    "/available-waiters",
    response_model=list[StaffOut],
    dependencies=[Depends(require_roles("superadmin", "table_admin"))],
)
def get_available_waiters(
    db: DBSession = Depends(get_db),
):
    """
    Returns all active waiters.
    Non-exclusive assignment: a waiter can serve multiple concurrent sessions.
    """
    waiters = (
        db.query(User)
        .filter(User.role == "waiter", User.is_active == True)
        .order_by(User.username.asc())
        .all()
    )
    return [StaffOut.model_validate(w) for w in waiters]


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
    role = _role(user)

    if role == "dealer":
        # Dealers get their assigned open session
        s = (
            db.query(Session)
            .filter(Session.dealer_id == user.id, Session.status == "open")
            .order_by(Session.created_at.desc())
            .first()
        )
    else:
        # superadmin and table_admin query by table_id
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
    dependencies=[Depends(require_roles("superadmin", "table_admin"))],
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

    # Validate dealer_id is required
    if payload.dealer_id is None:
        raise HTTPException(status_code=400, detail="Dealer is required to start a session")

    # Validate dealer exists and is active
    dealer = db.query(User).filter(
        User.id == payload.dealer_id,
        User.role == "dealer",
        User.is_active == True,
    ).first()
    if not dealer:
        raise HTTPException(status_code=400, detail="Invalid dealer selected")

    # Validate dealer is not already assigned to an active session (exclusive assignment)
    dealer_assigned = (
        db.query(Session)
        .filter(
            Session.status == "open",
            Session.dealer_id == payload.dealer_id,
        )
        .first()
    )
    if dealer_assigned:
        raise HTTPException(
            status_code=400,
            detail="Dealer is already assigned to another active session"
        )

    # Validate waiter if provided (optional, non-exclusive)
    waiter_id = None
    if payload.waiter_id is not None:
        waiter = db.query(User).filter(
            User.id == payload.waiter_id,
            User.role == "waiter",
            User.is_active == True,
        ).first()
        if not waiter:
            raise HTTPException(status_code=400, detail="Invalid waiter selected")
        waiter_id = payload.waiter_id

    seats_count = int(payload.seats_count) if payload.seats_count is not None else _as_int(table.seats_count)

    s = Session(
        table_id=tid,
        date=date,
        status=cast(Any, "open"),
        dealer_id=cast(Any, payload.dealer_id),
        waiter_id=cast(Any, waiter_id),
        chips_in_play=cast(Any, payload.chips_in_play),
    )
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


@router.get(
    "/{session_id}/non-cash-purchases",
    dependencies=[Depends(require_roles("superadmin", "dealer", "table_admin"))],
)
def get_non_cash_purchases(
    session_id: str,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get credit purchases per player in a session."""
    s = db.query(Session).filter(Session.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    _require_session_access(user, s)

    purchases = (
        db.query(ChipPurchase)
        .filter(
            ChipPurchase.session_id == session_id,
            ChipPurchase.payment_type == "credit",
            ChipPurchase.amount > 0,
        )
        .all()
    )

    # Group credit by seat_no to get per-player credit
    credit_by_seat = {}
    for p in purchases:
        seat_no = int(cast(int, p.seat_no))
        amount = int(cast(int, p.amount))
        credit_by_seat[seat_no] = credit_by_seat.get(seat_no, 0) + amount

    # Get seat info to include player names
    seats = db.query(Seat).filter(Seat.session_id == session_id).all()
    seat_info = {int(cast(int, s.seat_no)): s for s in seats}

    # Build response with player names
    credit_list = []
    total_credit = 0
    for seat_no, amount in sorted(credit_by_seat.items()):
        seat = seat_info.get(seat_no)
        player_name = seat.player_name if seat else None
        credit_list.append({
            "seat_no": seat_no,
            "player_name": player_name,
            "amount": amount
        })
        total_credit += amount

    return {
        "total_credit": total_credit,
        "credit_by_player": credit_list
    }


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

    # Only create ChipPurchase record for positive amounts (buyin)
    # Negative amounts (cashout) are not tracked as purchases
    if delta > 0:
        purchase = ChipPurchase(
            table_id=_as_int(s.table_id),
            session_id=str(cast(str, s.id)),
            seat_no=int(payload.seat_no),
            amount=delta,
            chip_op_id=_as_int(op.id),
            created_by_user_id=_as_int(user.id),
            payment_type=cast(Any, payload.payment_type),
        )
        db.add(purchase)

        # Auto-increment chips_in_play if total chips bought exceed current chips_in_play
        current_chips_in_play = _as_int(s.chips_in_play)
        total_chips_bought = sum(
            int(cast(int, p.amount))
            for p in db.query(ChipPurchase).filter(ChipPurchase.session_id == session_id).all()
        ) + delta  # Include the current purchase

        if total_chips_bought > current_chips_in_play:
            s.chips_in_play = cast(Any, total_chips_bought)

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
    s.closed_at = cast(Any, dt.datetime.utcnow())
    db.commit()
    db.refresh(s)
    return SessionOut.model_validate(s)



