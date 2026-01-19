from __future__ import annotations

import datetime as dt
import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession, joinedload

logger = logging.getLogger(__name__)

from ..core.datetime_utils import to_utc, utc_now
from ..core.deps import get_current_user, get_db, require_roles
from ..models.db import ChipOp, ChipPurchase, Seat, Session, SessionDealerAssignment, Table, User
from ..models.schemas import (
    AddDealerIn,
    ChipCreateIn,
    CloseSessionIn,
    RemoveDealerIn,
    ReplaceDealerIn,
    SeatAssignIn,
    SeatOut,
    SessionCreateIn,
    SessionDealerAssignmentOut,
    SessionOut,
    StaffOut,
    UndoIn,
)
from ..services.credit_service import CreditService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _get_seat_credit(db: DBSession, session_id: str, seat_no: int) -> int:
    """Get total credit for a specific seat (sum of all credit purchases, including payoffs)."""
    credit_purchases = (
        db.query(ChipPurchase)
        .filter(
            ChipPurchase.session_id == session_id,
            ChipPurchase.seat_no == seat_no,
            ChipPurchase.payment_type == "credit",
        )
        .all()
    )
    return sum(int(cast(int, p.amount)) for p in credit_purchases)


def _build_seat_out(seat: Seat, db: DBSession, session_id: str) -> SeatOut:
    """Build SeatOut response with cash/credit breakdown."""
    seat_no = int(cast(int, seat.seat_no))
    total = int(cast(int, seat.total))
    credit = _get_seat_credit(db, session_id, seat_no)
    cash = max(0, total - credit)

    return SeatOut(
        seat_no=seat_no,
        player_name=seat.player_name,
        total=total,
        cash=cash,
        credit=credit,
    )


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


def _compute_dealer_rake_by_assignment(
    db: DBSession,
    session_id: str,
    assignments: list[SessionDealerAssignment],
    session_closed_at: dt.datetime | None,
) -> dict[int, int]:
    """
    Compute casino profit (rake) attributed to each dealer assignment.

    We attribute negative chip ops that are NOT linked to a ChipPurchase (i.e. not a buyin/cashout)
    to the dealer assignment active at that moment.

    If assignments overlap, each op is attributed to the assignment with the latest started_at
    that still covers the op timestamp (prevents double-counting).
    """

    if not assignments:
        return {}

    now = utc_now()
    session_end = session_closed_at or now

    purchase_op_rows = (
        db.query(ChipPurchase.chip_op_id)
        .filter(ChipPurchase.session_id == session_id)
        .all()
    )
    purchase_op_ids = {int(cast(int, r[0])) for r in purchase_op_rows if r and r[0] is not None}

    loss_ops = (
        db.query(ChipOp)
        .filter(ChipOp.session_id == session_id, ChipOp.amount < 0)
        .all()
    )

    rake_by_assignment: dict[int, int] = {int(cast(int, a.id)): 0 for a in assignments if a.id is not None}

    for op in loss_ops:
        op_id = int(cast(int, op.id))
        if op_id in purchase_op_ids:
            continue

        op_time = to_utc(cast(dt.datetime, op.created_at))
        best: SessionDealerAssignment | None = None
        best_start: dt.datetime | None = None

        for a in assignments:
            if a.id is None or a.started_at is None:
                continue
            start = to_utc(cast(dt.datetime, a.started_at))
            end = to_utc(cast(dt.datetime, a.ended_at)) if a.ended_at else session_end

            # Ensure all datetimes are timezone-aware for comparison
            if start.tzinfo is None:
                start = start.replace(tzinfo=dt.timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=dt.timezone.utc)

            if start <= op_time <= end:
                if best is None or (best_start is not None and start > best_start) or best_start is None:
                    best = a
                    best_start = start

        if best is None or best.id is None:
            continue

        rake_by_assignment[int(cast(int, best.id))] += abs(int(cast(int, op.amount)))

    return rake_by_assignment


def _build_session_out(session: Session, db: DBSession) -> SessionOut:
    """Build SessionOut with dealer assignments (including computed rake per assignment)."""

    assignments = list(session.dealer_assignments or [])
    rake_by_assignment = _compute_dealer_rake_by_assignment(
        db=db,
        session_id=str(cast(str, session.id)),
        assignments=assignments,
        session_closed_at=cast(dt.datetime, session.closed_at) if session.closed_at else None,
    )

    dealer_assignments_out: list[SessionDealerAssignmentOut] = []
    for assignment in assignments:
        dealer_hourly_rate = None
        if assignment.dealer:
            dealer_hourly_rate = int(cast(int, assignment.dealer.hourly_rate)) if assignment.dealer.hourly_rate else None

        assignment_id = int(cast(int, assignment.id))
        dealer_assignments_out.append(
            SessionDealerAssignmentOut(
                id=assignment_id,
                dealer_id=int(cast(int, assignment.dealer_id)),
                dealer_username=cast(str, assignment.dealer.username) if assignment.dealer else "Unknown",
                dealer_hourly_rate=dealer_hourly_rate,
                started_at=cast(dt.datetime, assignment.started_at),
                ended_at=cast(dt.datetime, assignment.ended_at) if assignment.ended_at else None,
                rake=rake_by_assignment.get(assignment_id, 0),
            )
        )

    return SessionOut(
        id=str(cast(str, session.id)),
        table_id=int(cast(int, session.table_id)),
        date=cast(dt.date, session.date),
        status=cast(str, session.status),
        created_at=cast(dt.datetime, session.created_at),
        closed_at=cast(dt.datetime, session.closed_at) if session.closed_at else None,
        dealer_id=int(cast(int, session.dealer_id)) if session.dealer_id else None,
        waiter_id=int(cast(int, session.waiter_id)) if session.waiter_id else None,
        dealer=StaffOut.model_validate(session.dealer) if session.dealer else None,
        waiter=StaffOut.model_validate(session.waiter) if session.waiter else None,
        chips_in_play=int(cast(int, session.chips_in_play)) if session.chips_in_play is not None else None,
        dealer_assignments=dealer_assignments_out,
    )


@router.get(
    "/available-dealers",
    response_model=list[StaffOut],
    dependencies=[Depends(require_roles("superadmin", "table_admin"))],
)
def get_available_dealers(
    session_id: str | None = Query(default=None),
    db: DBSession = Depends(get_db),
):
    """
    Returns dealers not currently assigned to any active (open) session.
    If session_id is provided, returns dealers available to ADD to that specific session
    (excludes dealers already in that session, but allows dealers not in any session).
    """
    if session_id:
        # Get dealers already actively assigned to this specific session
        dealers_in_session = (
            db.query(SessionDealerAssignment.dealer_id)
            .filter(
                SessionDealerAssignment.session_id == session_id,
                SessionDealerAssignment.ended_at.is_(None),
            )
            .all()
        )
        dealers_in_session_ids = {row[0] for row in dealers_in_session if row[0] is not None}

        # Get dealers actively assigned to OTHER open sessions
        dealers_in_other_sessions = (
            db.query(SessionDealerAssignment.dealer_id)
            .join(Session, SessionDealerAssignment.session_id == Session.id)
            .filter(
                Session.status == "open",
                SessionDealerAssignment.ended_at.is_(None),
                Session.id != session_id,
            )
            .all()
        )
        dealers_in_other_sessions_ids = {row[0] for row in dealers_in_other_sessions if row[0] is not None}

        # Exclude dealers in this session OR in other sessions
        excluded_ids = dealers_in_session_ids | dealers_in_other_sessions_ids

        dealers = (
            db.query(User)
            .filter(
                User.role == "dealer",
                User.is_active == True,
                User.id.notin_(excluded_ids) if excluded_ids else True,
            )
            .order_by(User.username.asc())
            .all()
        )
    else:
        # Original behavior: Get IDs of dealers currently assigned to open sessions
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
            .options(
                joinedload(Session.dealer),
                joinedload(Session.waiter),
                joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
            )
            .filter(Session.dealer_id == user.id, Session.status == "open")
            .order_by(Session.created_at.desc())
            .first()
        )
    else:
        # superadmin and table_admin query by table_id
        tid = _resolve_table_id(user, table_id)
        s = (
            db.query(Session)
            .options(
                joinedload(Session.dealer),
                joinedload(Session.waiter),
                joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
            )
            .filter(Session.table_id == tid, Session.status == "open")
            .order_by(Session.created_at.desc())
            .first()
        )

    return _build_session_out(s, db) if s else None


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
        return _build_session_out(existing, db)

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

    # Create initial dealer assignment
    dealer_assignment = SessionDealerAssignment(
        session_id=cast(Any, s.id),
        dealer_id=cast(Any, payload.dealer_id),
        started_at=s.created_at,
        ended_at=None,
    )
    db.add(dealer_assignment)

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
    return _build_session_out(s, db)


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

    return [_build_seat_out(seat, db, session_id) for seat in seats]


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
    return _build_seat_out(seat, db, session_id)


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


@router.get(
    "/{session_id}/rake",
    dependencies=[Depends(require_roles("superadmin", "dealer", "table_admin"))],
)
def get_session_rake(
    session_id: str,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get current rake (casino profit) for a session."""
    s = db.query(Session).filter(Session.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    _require_session_access(user, s)

    # Buyins/cashouts are money movements tracked via ChipPurchase
    purchases = db.query(ChipPurchase).filter(ChipPurchase.session_id == session_id).all()
    total_buyins = sum(int(cast(int, p.amount)) for p in purchases if p.amount > 0)
    total_cashouts = sum(int(cast(int, p.amount)) for p in purchases if p.amount < 0)

    # Get total chips currently on table (sum of all seat totals)
    seats = db.query(Seat).filter(Seat.session_id == session_id).all()
    chips_on_table = sum(int(cast(int, seat.total)) for seat in seats)

    # Get total credit (sum of all credit purchases, including payoffs)
    total_credit = sum(
        int(cast(int, p.amount))
        for p in purchases
        if p.payment_type == "credit"
    )

    # Gross rake (casino profit) = buyins - cashouts - chips still on table
    # cashouts are negative amounts, so: buyins + cashouts - chips_on_table
    total_rake = total_buyins + total_cashouts - chips_on_table

    return {
        "total_rake": total_rake,
        "total_buyins": total_buyins,
        "total_cashouts": total_cashouts,
        "chips_on_table": chips_on_table,
        "total_credit": total_credit,
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

    # When buying chips for cash while having credit, first pay off credit
    if delta > 0 and payload.payment_type == "cash":
        current_credit = _get_seat_credit(db, session_id, payload.seat_no)

        if current_credit > 0:
            # Amount used to pay off credit
            credit_payoff = min(delta, current_credit)
            # Remaining amount for actual chip purchase
            chips_to_add = delta - credit_payoff

            # Create ChipOp for credit payoff (0 amount - no chips added)
            if credit_payoff > 0:
                payoff_op = ChipOp(
                    session_id=cast(Any, session_id),
                    seat_no=cast(Any, payload.seat_no),
                    amount=cast(Any, 0),  # No chips added for credit payoff
                )
                db.add(payoff_op)
                db.flush()

                credit_payoff_purchase = ChipPurchase(
                    table_id=_as_int(s.table_id),
                    session_id=str(cast(str, s.id)),
                    seat_no=int(payload.seat_no),
                    amount=-credit_payoff,  # Negative to reduce credit
                    chip_op_id=_as_int(payoff_op.id),
                    created_by_user_id=_as_int(user.id),
                    payment_type=cast(Any, "credit"),
                )
                db.add(credit_payoff_purchase)

            # Create ChipOp and cash purchase for remaining amount (if any)
            if chips_to_add > 0:
                cash_op = ChipOp(
                    session_id=cast(Any, session_id),
                    seat_no=cast(Any, payload.seat_no),
                    amount=cast(Any, chips_to_add),
                )
                db.add(cash_op)
                db.flush()

                cash_purchase = ChipPurchase(
                    table_id=_as_int(s.table_id),
                    session_id=str(cast(str, s.id)),
                    seat_no=int(payload.seat_no),
                    amount=chips_to_add,
                    chip_op_id=_as_int(cash_op.id),
                    created_by_user_id=_as_int(user.id),
                    payment_type=cast(Any, "cash"),
                )
                db.add(cash_purchase)

            seat.total = cast(Any, seat_total + chips_to_add)
        else:
            # No credit, normal cash purchase
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
                payment_type=cast(Any, payload.payment_type),
            )
            db.add(purchase)
    else:
        # Credit purchase or negative amount (cashout)
        seat.total = cast(Any, seat_total + delta)

        op = ChipOp(
            session_id=cast(Any, session_id),
            seat_no=cast(Any, payload.seat_no),
            amount=cast(Any, delta),
        )
        db.add(op)
        db.flush()

        # Only create ChipPurchase record for positive amounts (buyin)
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
    if delta > 0:
        current_chips_in_play = _as_int(s.chips_in_play)
        total_chips_bought = sum(
            int(cast(int, p.amount))
            for p in db.query(ChipPurchase).filter(ChipPurchase.session_id == session_id).all()
        )

        if total_chips_bought > current_chips_in_play:
            s.chips_in_play = cast(Any, total_chips_bought)

    db.commit()
    db.refresh(seat)
    return _build_seat_out(seat, db, session_id)


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
    return _build_seat_out(seat, db, session_id)


def _validate_and_get_session(db: DBSession, session_id: str, user: User) -> Session:
    """
    Validate session exists and user has access to it.

    Args:
        db: Database session
        session_id: Session ID to validate
        user: Current user

    Returns:
        Session object

    Raises:
        HTTPException: If session not found or user doesn't have access
    """
    logger.info(f"Querying session {session_id} with dealer and waiter loaded")
    s = db.query(Session).options(joinedload(Session.dealer), joinedload(Session.waiter)).filter(Session.id == session_id).first()
    if not s:
        logger.warning(f"Session {session_id} not found")
        raise HTTPException(status_code=404, detail="Session not found")
    _require_session_access(user, s)
    logger.info(f"Session {session_id} access validated for user {user.username}")
    return s


def _get_session_seats(db: DBSession, session_id: str) -> list[Seat]:
    """
    Get all seats for a session.
    
    Args:
        db: Database session
        session_id: Session ID
        
    Returns:
        List of seats
    """
    return db.query(Seat).filter(Seat.session_id == session_id).all()


def _cashout_seat_chips(
    db: DBSession,
    session: Session,
    seat: Seat,
    chips_to_cashout: int,
    user: User,
) -> None:
    """
    Cash out chips for a seat.
    
    Args:
        db: Database session
        session: Session object
        seat: Seat object
        chips_to_cashout: Number of chips to cash out (positive number)
        user: Current user
    """
    if chips_to_cashout <= 0:
        return
    
    # Create chip operation for cashout
    op = ChipOp(
        session_id=cast(Any, session.id),
        seat_no=cast(Any, seat.seat_no),
        amount=cast(Any, -chips_to_cashout),  # Negative for cashout
    )
    db.add(op)
    db.flush()
    
    # Create ChipPurchase record for cashout (negative amount = expense)
    purchase = ChipPurchase(
        table_id=_as_int(session.table_id),
        session_id=str(cast(str, session.id)),
        seat_no=int(seat.seat_no),
        amount=-chips_to_cashout,  # Negative for cashout
        chip_op_id=_as_int(op.id),
        created_by_user_id=_as_int(user.id),
        payment_type=cast(Any, "cash"),  # Cashouts are always cash
    )
    db.add(purchase)


def _finalize_session(db: DBSession, session: Session, dealer_rakes: dict[int, int] | None = None) -> None:
    """
    Finalize session by setting status to closed and recording close time.
    Also ends any active dealer assignments and saves their rake amounts.

    Args:
        db: Database session
        session: Session object
        dealer_rakes: Dict mapping assignment_id to rake amount (optional)
    """
    now = utc_now()
    session.status = cast(Any, "closed")
    session.closed_at = cast(Any, now)

    # End any active dealer assignments and save their rake amounts
    active_assignments = (
        db.query(SessionDealerAssignment)
        .filter(
            SessionDealerAssignment.session_id == session.id,
            SessionDealerAssignment.ended_at.is_(None),
        )
        .all()
    )
    for assignment in active_assignments:
        assignment.ended_at = cast(Any, now)
        if dealer_rakes and int(cast(int, assignment.id)) in dealer_rakes:
            assignment.rake = cast(Any, dealer_rakes[int(cast(int, assignment.id))])


@router.post(
    "/{session_id}/close",
    response_model=SessionOut,
    dependencies=[Depends(require_roles("superadmin", "dealer", "table_admin"))],
)
def close_session(
    session_id: str,
    payload: CloseSessionIn,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(f"Attempting to close session {session_id} by user {user.username}")

    try:
        # Validate session and user access
        logger.info(f"Validating session {session_id}")
        s = _validate_and_get_session(db, session_id, user)
        logger.info(f"Session validated: status={s.status}, table_id={s.table_id}")

        # Get all seats for this session
        logger.info(f"Getting seats for session {session_id}")
        seats = _get_session_seats(db, session_id)
        logger.info(f"Found {len(seats)} seats")

        # Cash out all player chips
        # NOTE: We do NOT auto-close credit when closing a session.
        # Credit must be manually closed via the /api/admin/close-credit endpoint.
        # This ensures credit repayment is tracked on the day it actually happens.
        for seat in seats:
            seat_total = _as_int(seat.total)
            logger.info(f"Processing seat {seat.seat_no}: total={seat_total}")
            if seat_total > 0:
                # Cash out all chips (including those bought on credit)
                _cashout_seat_chips(db, s, seat, seat_total, user)

                # Set seat total to 0 after cashing out
                seat.total = cast(Any, 0)

        # Build dealer rakes dict from payload
        dealer_rakes = {dr.assignment_id: dr.rake for dr in payload.dealer_rakes}

        # Finalize session with dealer rake amounts
        logger.info(f"Finalizing session {session_id} with dealer rakes: {dealer_rakes}")
        _finalize_session(db, s, dealer_rakes)

        logger.info(f"Committing transaction for session {session_id}")
        db.commit()
        db.refresh(s)
        logger.info(f"Session {session_id} closed successfully")
        return _build_session_out(s, db)

    except Exception as e:
        logger.error(f"Error closing session {session_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        db.rollback()
        raise


@router.post(
    "/{session_id}/replace-dealer",
    response_model=SessionOut,
    dependencies=[Depends(require_roles("superadmin", "table_admin"))],
)
def replace_dealer(
    session_id: str,
    payload: ReplaceDealerIn,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Replace the current dealer in an open session with a new dealer.
    Only table_admin and superadmin can perform this action.
    The current dealer's assignment is ended and a new assignment begins.
    """
    # Get the session with eager loading
    s = (
        db.query(Session)
        .options(
            joinedload(Session.dealer),
            joinedload(Session.waiter),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
        )
        .filter(Session.id == session_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    if s.status != "open":
        raise HTTPException(status_code=400, detail="Can only replace dealer in open sessions")

    _require_session_access(user, s)

    # Validate new dealer exists and is active
    new_dealer = db.query(User).filter(
        User.id == payload.new_dealer_id,
        User.role == "dealer",
        User.is_active == True,
    ).first()
    if not new_dealer:
        raise HTTPException(status_code=400, detail="Invalid dealer selected")

    # Check new dealer is not already assigned to another open session
    dealer_assigned = (
        db.query(Session)
        .filter(
            Session.status == "open",
            Session.dealer_id == payload.new_dealer_id,
            Session.id != session_id,  # Exclude current session
        )
        .first()
    )
    if dealer_assigned:
        raise HTTPException(
            status_code=400,
            detail="Dealer is already assigned to another active session"
        )

    now = utc_now()

    # End current dealer assignment (if any) and save rake for outgoing dealer
    current_assignment = (
        db.query(SessionDealerAssignment)
        .filter(
            SessionDealerAssignment.session_id == session_id,
            SessionDealerAssignment.ended_at.is_(None),
        )
        .first()
    )
    if current_assignment:
        current_assignment.ended_at = cast(Any, now)
        current_assignment.rake = cast(Any, payload.outgoing_dealer_rake)

    # Create new dealer assignment
    new_assignment = SessionDealerAssignment(
        session_id=cast(Any, session_id),
        dealer_id=cast(Any, payload.new_dealer_id),
        started_at=now,
        ended_at=None,
    )
    db.add(new_assignment)

    # Update session's current dealer
    s.dealer_id = cast(Any, payload.new_dealer_id)

    db.commit()

    # Reload session with all relationships
    s = (
        db.query(Session)
        .options(
            joinedload(Session.dealer),
            joinedload(Session.waiter),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
        )
        .filter(Session.id == session_id)
        .first()
    )

    logger.info(f"Dealer replaced in session {session_id}: new dealer {new_dealer.username}")
    return _build_session_out(s, db)


@router.post(
    "/{session_id}/add-dealer",
    response_model=SessionOut,
    dependencies=[Depends(require_roles("superadmin", "table_admin"))],
)
def add_dealer(
    session_id: str,
    payload: AddDealerIn,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Add a dealer to an open session to work concurrently with existing dealer(s).
    Only table_admin and superadmin can perform this action.
    This does NOT end any existing dealer assignments - multiple dealers can work simultaneously.
    """
    # Get the session with eager loading
    s = (
        db.query(Session)
        .options(
            joinedload(Session.dealer),
            joinedload(Session.waiter),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
        )
        .filter(Session.id == session_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    if s.status != "open":
        raise HTTPException(status_code=400, detail="Can only add dealer to open sessions")

    _require_session_access(user, s)

    # Validate dealer exists and is active
    new_dealer = db.query(User).filter(
        User.id == payload.dealer_id,
        User.role == "dealer",
        User.is_active == True,
    ).first()
    if not new_dealer:
        raise HTTPException(status_code=400, detail="Invalid dealer selected")

    # Check if dealer is already actively assigned to this session
    existing_assignment = (
        db.query(SessionDealerAssignment)
        .filter(
            SessionDealerAssignment.session_id == session_id,
            SessionDealerAssignment.dealer_id == payload.dealer_id,
            SessionDealerAssignment.ended_at.is_(None),
        )
        .first()
    )
    if existing_assignment:
        raise HTTPException(
            status_code=400,
            detail="Dealer is already assigned to this session"
        )

    # Check dealer is not assigned to another open session
    dealer_assigned = (
        db.query(SessionDealerAssignment)
        .join(Session, SessionDealerAssignment.session_id == Session.id)
        .filter(
            Session.status == "open",
            SessionDealerAssignment.dealer_id == payload.dealer_id,
            SessionDealerAssignment.ended_at.is_(None),
            Session.id != session_id,
        )
        .first()
    )
    if dealer_assigned:
        raise HTTPException(
            status_code=400,
            detail="Dealer is already assigned to another active session"
        )

    now = utc_now()

    # Create new dealer assignment (concurrent with existing ones)
    new_assignment = SessionDealerAssignment(
        session_id=cast(Any, session_id),
        dealer_id=cast(Any, payload.dealer_id),
        started_at=now,
        ended_at=None,
    )
    db.add(new_assignment)

    db.commit()

    # Reload session with all relationships
    s = (
        db.query(Session)
        .options(
            joinedload(Session.dealer),
            joinedload(Session.waiter),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
        )
        .filter(Session.id == session_id)
        .first()
    )

    logger.info(f"Dealer added to session {session_id}: {new_dealer.username}")
    return _build_session_out(s, db)


@router.post(
    "/{session_id}/remove-dealer",
    response_model=SessionOut,
    dependencies=[Depends(require_roles("superadmin", "table_admin"))],
)
def remove_dealer(
    session_id: str,
    payload: RemoveDealerIn,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    End a specific dealer's assignment in an open session.
    Only table_admin and superadmin can perform this action.
    This is used when multiple dealers are working concurrently and one needs to be removed.
    """
    # Get the session with eager loading
    s = (
        db.query(Session)
        .options(
            joinedload(Session.dealer),
            joinedload(Session.waiter),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
        )
        .filter(Session.id == session_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    if s.status != "open":
        raise HTTPException(status_code=400, detail="Can only remove dealer from open sessions")

    _require_session_access(user, s)

    # Find the dealer assignment
    assignment = (
        db.query(SessionDealerAssignment)
        .filter(
            SessionDealerAssignment.id == payload.assignment_id,
            SessionDealerAssignment.session_id == session_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Dealer assignment not found")

    if assignment.ended_at is not None:
        raise HTTPException(status_code=400, detail="Dealer assignment already ended")

    # Get all active assignments for this session
    active_assignments = (
        db.query(SessionDealerAssignment)
        .filter(
            SessionDealerAssignment.session_id == session_id,
            SessionDealerAssignment.ended_at.is_(None),
        )
        .all()
    )

    # Prevent removing the last dealer
    if len(active_assignments) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot remove the last dealer from a session. Close the session instead."
        )

    now = utc_now()

    # End the dealer assignment and save the rake amount
    assignment.ended_at = cast(Any, now)
    assignment.rake = cast(Any, payload.rake)

    # If this was the primary dealer (session.dealer_id), update to another active dealer
    if s.dealer_id == assignment.dealer_id:
        # Find another active dealer to set as primary
        other_assignment = next(
            (a for a in active_assignments if a.id != assignment.id),
            None
        )
        if other_assignment:
            s.dealer_id = cast(Any, other_assignment.dealer_id)

    db.commit()

    # Reload session with all relationships
    s = (
        db.query(Session)
        .options(
            joinedload(Session.dealer),
            joinedload(Session.waiter),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
        )
        .filter(Session.id == session_id)
        .first()
    )

    logger.info(f"Dealer assignment {payload.assignment_id} ended in session {session_id}")
    return _build_session_out(s, db)


