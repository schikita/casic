from __future__ import annotations

import datetime as dt
import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession, joinedload

logger = logging.getLogger(__name__)

from ..core.datetime_utils import utc_now
from ..core.deps import get_current_user, get_db, require_roles
from ..models.db import ChipOp, ChipPurchase, Seat, Session, SessionDealerAssignment, Table, User
from ..models.schemas import (
    ChipCreateIn,
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


def _build_session_out(session: Session) -> SessionOut:
    """Build SessionOut with dealer assignments."""
    dealer_assignments_out = []
    if session.dealer_assignments:
        for assignment in session.dealer_assignments:
            dealer_assignments_out.append(
                SessionDealerAssignmentOut(
                    id=int(cast(int, assignment.id)),
                    dealer_id=int(cast(int, assignment.dealer_id)),
                    dealer_username=cast(str, assignment.dealer.username) if assignment.dealer else "Unknown",
                    started_at=cast(dt.datetime, assignment.started_at),
                    ended_at=cast(dt.datetime, assignment.ended_at) if assignment.ended_at else None,
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

    return _build_session_out(s) if s else None


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
    return _build_session_out(s)


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

    # Get all chip operations for this session (only positive = buyins)
    chip_ops = db.query(ChipOp).filter(ChipOp.session_id == session_id).all()
    total_buyins = sum(int(cast(int, op.amount)) for op in chip_ops if op.amount > 0)

    # Get total chips currently on table (sum of all seat totals)
    seats = db.query(Seat).filter(Seat.session_id == session_id).all()
    chips_on_table = sum(int(cast(int, seat.total)) for seat in seats)

    # Get total credit (chips bought on credit)
    credit_purchases = (
        db.query(ChipPurchase)
        .filter(
            ChipPurchase.session_id == session_id,
            ChipPurchase.payment_type == "credit",
            ChipPurchase.amount > 0,
        )
        .all()
    )
    total_credit = sum(int(cast(int, p.amount)) for p in credit_purchases)

    # Rake = casino profit = chips sold to players - chips still on table
    # This represents what players have lost
    total_rake = total_buyins - chips_on_table

    return {
        "total_rake": total_rake,
        "total_buyins": total_buyins,
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


def _finalize_session(db: DBSession, session: Session) -> None:
    """
    Finalize session by setting status to closed and recording close time.
    Also ends any active dealer assignments.

    Args:
        db: Database session
        session: Session object
    """
    now = utc_now()
    session.status = cast(Any, "closed")
    session.closed_at = cast(Any, now)

    # End any active dealer assignments
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
        
        # Finalize session
        logger.info(f"Finalizing session {session_id}")
        _finalize_session(db, s)

        logger.info(f"Committing transaction for session {session_id}")
        db.commit()
        db.refresh(s)
        logger.info(f"Session {session_id} closed successfully")
        return _build_session_out(s)

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

    # End current dealer assignment (if any)
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
    return _build_session_out(s)



