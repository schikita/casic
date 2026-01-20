from __future__ import annotations

import datetime as dt
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession, joinedload

from typing import Any, cast

from ..core.deps import get_current_user, get_db, get_owner_id_for_filter, require_roles
from ..core.exceptions import ErrorMessages
from ..core.security import get_password_hash
from ..models.db import CasinoBalanceAdjustment, ChipOp, ChipPurchase, DealerRakeEntry, Seat, Session, SessionDealerAssignment, Table, User
from ..models.schemas import (
    CasinoBalanceAdjustmentIn,
    CasinoBalanceAdjustmentOut,
    ChipPurchaseOut,
    CloseCreditIn,
    CloseCreditOut,
    ClosedSessionOut,
    DealerRakeEntryOut,
    SessionDealerAssignmentOut,
    TableCreateIn,
    TableOut,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)
from ..services.credit_service import CreditService

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _normalize_username(v: str) -> str:
    return v.strip()


def _normalize_table_name(v: str) -> str:
    return v.strip()


def _resolve_table_id_for_user(user: User, table_id: int | None, db: DBSession) -> int | None:
    """
    Resolve the table_id to use based on user role and permissions (multi-tenancy aware).

    Args:
        user: Current user
        table_id: Optional table_id from request
        db: Database session for checking table ownership

    Returns:
        Resolved table_id, or None for superadmin viewing all tables

    Raises:
        HTTPException: If table_id cannot be resolved or access is forbidden
    """
    role = cast(str, user.role)

    if role == "superadmin":
        # Superadmin can view all tables if no table_id is provided
        return int(table_id) if table_id is not None else None

    if role not in ("table_admin", "waiter"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Multi-tenancy: table_admin must specify a table_id and it must be owned by them
    if table_id is None:
        raise HTTPException(status_code=400, detail="table_id is required")

    owner_id = get_owner_id_for_filter(user)
    table = db.query(Table).filter(Table.id == table_id, Table.owner_id == owner_id).first()
    if not table:
        raise HTTPException(status_code=403, detail=ErrorMessages.FORBIDDEN_FOR_TABLE)

    return int(table_id)


@router.get("/tables", response_model=list[TableOut])
def list_tables(
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    role = cast(str, user.role)

    if role == "superadmin":
        # Superadmin sees all tables
        tables = db.query(Table).order_by(Table.id.asc()).all()
        return [TableOut.model_validate(t) for t in tables]

    # table_admin sees only tables they own
    owner_id = get_owner_id_for_filter(user)
    if owner_id is None:
        return []

    tables = db.query(Table).filter(Table.owner_id == owner_id).order_by(Table.id.asc()).all()
    return [TableOut.model_validate(t) for t in tables]


@router.post("/tables", response_model=TableOut, dependencies=[Depends(require_roles("table_admin"))])
def create_table(
    payload: TableCreateIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TableOut:
    name = _normalize_table_name(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="Table name is required")

    # Get owner_id for multi-tenancy
    owner_id = get_owner_id_for_filter(current_user)

    # Check for duplicate table name within this owner's tables
    existing = db.query(Table).filter(Table.name == name, Table.owner_id == owner_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Table name already exists")

    t = Table(name=name, seats_count=payload.seats_count, owner_id=owner_id)
    db.add(t)
    db.commit()
    db.refresh(t)
    return TableOut.model_validate(t)


@router.put("/tables/{table_id}", response_model=TableOut, dependencies=[Depends(require_roles("table_admin"))])
def update_table(
    table_id: int,
    payload: TableCreateIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TableOut:
    """Update a table by ID."""
    owner_id = get_owner_id_for_filter(current_user)

    # Query with owner filter for multi-tenancy
    table = db.query(Table).filter(Table.id == table_id, Table.owner_id == owner_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    name = _normalize_table_name(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="Table name is required")

    # Check if name is being changed and if new name already exists (within same owner)
    if name != table.name:
        existing = db.query(Table).filter(Table.name == name, Table.owner_id == owner_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Table name already exists")

    table.name = name
    table.seats_count = payload.seats_count
    db.commit()
    db.refresh(table)
    return TableOut.model_validate(table)


@router.delete("/tables/{table_id}", dependencies=[Depends(require_roles("table_admin"))])
def delete_table(
    table_id: int,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a table by ID, including all related sessions and their data."""
    from ..models.db import SeatNameChange

    owner_id = get_owner_id_for_filter(current_user)

    # Query with owner filter for multi-tenancy
    table = db.query(Table).filter(Table.id == table_id, Table.owner_id == owner_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    # Get all sessions for this table
    sessions = db.query(Session).filter(Session.table_id == table_id).all()
    session_ids = [s.id for s in sessions]

    if session_ids:
        # Delete all related data for these sessions

        # 1. Delete DealerRakeEntries (linked via assignment_id)
        assignment_ids = [
            a.id for a in db.query(SessionDealerAssignment)
            .filter(SessionDealerAssignment.session_id.in_(session_ids))
            .all()
        ]
        if assignment_ids:
            db.query(DealerRakeEntry).filter(DealerRakeEntry.assignment_id.in_(assignment_ids)).delete(synchronize_session=False)

        # 2. Delete SessionDealerAssignments
        db.query(SessionDealerAssignment).filter(SessionDealerAssignment.session_id.in_(session_ids)).delete(synchronize_session=False)

        # 3. Delete ChipPurchases (linked via session_id)
        db.query(ChipPurchase).filter(ChipPurchase.session_id.in_(session_ids)).delete(synchronize_session=False)

        # 4. Delete ChipOps
        db.query(ChipOp).filter(ChipOp.session_id.in_(session_ids)).delete(synchronize_session=False)

        # 5. Delete SeatNameChanges
        db.query(SeatNameChange).filter(SeatNameChange.session_id.in_(session_ids)).delete(synchronize_session=False)

        # 6. Delete Seats
        db.query(Seat).filter(Seat.session_id.in_(session_ids)).delete(synchronize_session=False)

        # 7. Delete Sessions
        db.query(Session).filter(Session.table_id == table_id).delete(synchronize_session=False)

    # Finally delete the table itself
    db.delete(table)
    db.commit()
    return {"message": "Table deleted successfully"}


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_roles("superadmin", "table_admin"))])
def list_users(db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[UserOut]:
    """
    List users based on role:
    - superadmin: sees all users except their own account
    - table_admin: sees only dealer and waiter users that they own (multi-tenancy)
    """
    role = cast(str, current_user.role)

    if role == "superadmin":
        # Superadmin sees only table_admin users (not themselves, not dealers/waiters)
        users = db.query(User).filter(
            User.id != current_user.id,
            User.role == "table_admin"
        ).order_by(User.id.asc()).all()
    else:
        # Table admin only sees dealer and waiter users that they own (multi-tenancy)
        owner_id = get_owner_id_for_filter(current_user)
        users = db.query(User).filter(
            User.role.in_(["dealer", "waiter"]),
            User.owner_id == owner_id,
        ).order_by(User.id.asc()).all()

    return [UserOut.model_validate(u) for u in users]


def _replace_existing_table_admin(db: DBSession, table_id: int, exclude_user_id: int | None = None):
    """Remove table assignment from existing table_admin and assign to new user."""
    q = db.query(User).filter(User.role == "table_admin", User.table_id == table_id)
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    existing_admin = q.first()
    if existing_admin:
        # Remove table assignment from existing table_admin
        existing_admin.table_id = None


@router.post("/users", response_model=UserOut, dependencies=[Depends(require_roles("superadmin", "table_admin"))])
def create_user(payload: UserCreateIn, db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user)) -> UserOut:
    """
    Create user based on role:
    - superadmin: can only create table_admin users (owner_id = NULL)
    - table_admin: can only create dealer and waiter users (owner_id = current_user.id)
    """
    username = _normalize_username(payload.username)
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    current_role = cast(str, current_user.role)
    owner_id: int | None = None  # Multi-tenancy: owner of the new user

    # Validate role permissions based on current user's role
    if current_role == "superadmin":
        # Superadmin can only create table_admin users
        if payload.role != "table_admin":
            raise HTTPException(status_code=403, detail="Superadmin can only create table_admin users")

        # table_admin does not need table_id anymore (they create their own tables)
        # Password is required for table_admin
        if not payload.password or len(payload.password) < 4:
            raise HTTPException(status_code=400, detail="Password is required for table_admin role (minimum 4 characters)")

        # hourly_rate is not applicable for table_admin
        hourly_rate = None

        # table_id is not applicable for table_admin (they create their own tables)
        table_id = None

        # owner_id is NULL for table_admin (they are owners themselves)
        owner_id = None

    elif current_role == "table_admin":
        # Table admin can only create dealer and waiter users
        if payload.role not in ("dealer", "waiter"):
            raise HTTPException(status_code=403, detail="Table admin can only create dealer and waiter users")

        # Password is optional for dealer/waiter
        if payload.password is not None and len(payload.password) < 4:
            raise HTTPException(status_code=400, detail="Password must be at least 4 characters if provided")

        # hourly_rate is required for dealer/waiter
        if payload.hourly_rate is None:
            raise HTTPException(status_code=400, detail="hourly_rate is required for dealer and waiter roles")

        hourly_rate = payload.hourly_rate

        # table_id is not applicable for dealer/waiter
        table_id = None

        # owner_id is current user's id (multi-tenancy: dealer/waiter belongs to this table_admin's casino)
        owner_id = int(cast(int, current_user.id))

    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    u = User(
        username=username,
        password_hash=get_password_hash(payload.password) if payload.password else None,
        role=payload.role,
        table_id=table_id,
        is_active=payload.is_active,
        hourly_rate=hourly_rate,
        owner_id=owner_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return UserOut.model_validate(u)


@router.put("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_roles("superadmin", "table_admin"))])
def update_user(user_id: int, payload: UserUpdateIn, db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user)) -> UserOut:
    """
    Update user based on role:
    - superadmin: can only update table_admin users
    - table_admin: can only update dealer and waiter users (that they own)
    """
    current_role = cast(str, current_user.role)

    # Build query based on role for multi-tenancy
    if current_role == "superadmin":
        u = db.query(User).filter(User.id == user_id).first()
    else:
        # table_admin can only update users they own
        owner_id = get_owner_id_for_filter(current_user)
        u = db.query(User).filter(User.id == user_id, User.owner_id == owner_id).first()

    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    user_role = cast(str, u.role)

    # Validate permissions based on current user's role
    if current_role == "superadmin":
        # Superadmin can only update table_admin users
        if user_role != "table_admin":
            raise HTTPException(status_code=403, detail="Superadmin can only update table_admin users")
    elif current_role == "table_admin":
        # Table admin can only update dealer and waiter users
        if user_role not in ("dealer", "waiter"):
            raise HTTPException(status_code=403, detail="Table admin can only update dealer and waiter users")
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Update username if provided (superadmin only can update table_admin usernames)
    if payload.username is not None:
        new_username = _normalize_username(payload.username)
        if new_username != u.username:
            # Check if username is already taken
            existing = db.query(User).filter(User.username == new_username, User.id != user_id).first()
            if existing:
                raise HTTPException(status_code=400, detail="Имя пользователя уже занято")
            u.username = cast(Any, new_username)

    # Update role if provided
    if payload.role is not None:
        # Validate role change permissions
        if current_role == "superadmin" and payload.role != "table_admin":
            raise HTTPException(status_code=403, detail="Superadmin can only create/update table_admin users")
        if current_role == "table_admin" and payload.role not in ("dealer", "waiter"):
            raise HTTPException(status_code=403, detail="Table admin can only create/update dealer and waiter users")
        u.role = cast(Any, str(payload.role))

    # Update is_active if provided
    if payload.is_active is not None:
        u.is_active = cast(Any, payload.is_active)

    # Update password if provided
    if payload.password is not None:
        # For table_admin, password is required and cannot be empty
        if user_role == "table_admin":
            if len(payload.password) < 4:
                raise HTTPException(status_code=400, detail="Password must be at least 4 characters for table_admin")
            u.password_hash = cast(Any, get_password_hash(payload.password))
        else:
            # For dealer/waiter, password is optional
            if len(payload.password) >= 4:
                u.password_hash = cast(Any, get_password_hash(payload.password))

    # Update hourly_rate if provided
    if payload.hourly_rate is not None:
        u.hourly_rate = cast(Any, payload.hourly_rate)

    # Get the current role after potential changes
    u_role = cast(str, u.role)

    # Validate role-specific constraints
    if u_role == "superadmin":
        u.hourly_rate = cast(Any, None)  # hourly_rate not applicable for superadmin
    elif u_role == "dealer":
        # dealer is not associated with tables, will be assigned to sessions
        pass
    elif u_role == "table_admin":
        u.hourly_rate = cast(Any, None)  # hourly_rate not applicable for table_admin
    elif u_role == "waiter":
        # waiter has no special constraints
        pass

    db.commit()
    db.refresh(u)
    return UserOut.model_validate(u)


@router.get(
    "/chip-purchases",
    response_model=list[ChipPurchaseOut],
    dependencies=[Depends(require_roles("superadmin"))],
)
def list_chip_purchases(
    limit: int = Query(default=100, ge=1, le=500),
    db: DBSession = Depends(get_db),
):
    rows = (
        db.query(ChipPurchase)
        .options(joinedload(ChipPurchase.table), joinedload(ChipPurchase.created_by))
        .order_by(ChipPurchase.id.desc())
        .limit(limit)
        .all()
    )

    out: list[ChipPurchaseOut] = []
    for p in rows:
        table_name = ""
        if p.table is not None:
            table_name = cast(str, p.table.name)

        created_by_username = None
        if p.created_by is not None:
            created_by_username = cast(str, p.created_by.username)

        out.append(
            ChipPurchaseOut(
                id=int(cast(int, p.id)),
                table_id=int(cast(int, p.table_id)),
                table_name=table_name,
                session_id=str(cast(str, p.session_id)) if p.session_id is not None else None,
                seat_no=int(cast(int, p.seat_no)),
                amount=int(cast(int, p.amount)),
                created_at=cast(dt.datetime, p.created_at),
                created_by_user_id=int(cast(int, p.created_by_user_id)) if p.created_by_user_id is not None else None,
                created_by_username=created_by_username,
            )
        )

    return out


@router.post(
    "/balance-adjustments",
    response_model=CasinoBalanceAdjustmentOut,
    dependencies=[Depends(require_roles("superadmin", "table_admin"))],
)
def create_balance_adjustment(
    payload: CasinoBalanceAdjustmentIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CasinoBalanceAdjustmentOut:
    """Create a new casino balance adjustment (profit or expense)."""
    if payload.amount == 0:
        raise HTTPException(status_code=400, detail="Amount cannot be zero")

    # Multi-tenancy: set owner_id
    owner_id = get_owner_id_for_filter(current_user)

    adjustment = CasinoBalanceAdjustment(
        amount=payload.amount,
        comment=payload.comment.strip(),
        created_by_user_id=current_user.id,
        owner_id=owner_id,
    )
    db.add(adjustment)
    db.commit()
    db.refresh(adjustment)

    return CasinoBalanceAdjustmentOut(
        id=int(cast(int, adjustment.id)),
        created_at=cast(dt.datetime, adjustment.created_at),
        amount=int(cast(int, adjustment.amount)),
        comment=cast(str, adjustment.comment),
        created_by_user_id=int(cast(int, adjustment.created_by_user_id)),
        created_by_username=current_user.username,
    )


@router.get(
    "/balance-adjustments",
    response_model=list[CasinoBalanceAdjustmentOut],
    dependencies=[Depends(require_roles("superadmin", "table_admin"))],
)
def list_balance_adjustments(
    limit: int = Query(default=50, ge=1, le=200),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List recent balance adjustments (filtered by owner for multi-tenancy)."""
    owner_id = get_owner_id_for_filter(current_user)

    query = db.query(CasinoBalanceAdjustment).options(joinedload(CasinoBalanceAdjustment.created_by))

    # Filter by owner_id for non-superadmin users (multi-tenancy)
    if owner_id is not None:
        query = query.filter(CasinoBalanceAdjustment.owner_id == owner_id)

    adjustments = query.order_by(CasinoBalanceAdjustment.created_at.desc()).limit(limit).all()

    out: list[CasinoBalanceAdjustmentOut] = []
    for adj in adjustments:
        created_by_username = None
        if adj.created_by is not None:
            created_by_username = cast(str, adj.created_by.username)

        out.append(
            CasinoBalanceAdjustmentOut(
                id=int(cast(int, adj.id)),
                created_at=cast(dt.datetime, adj.created_at),
                amount=int(cast(int, adj.amount)),
                comment=cast(str, adj.comment),
                created_by_user_id=int(cast(int, adj.created_by_user_id)),
                created_by_username=created_by_username,
            )
        )

    return out


def _get_working_day_boundaries(date: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """
    Get working day boundaries for a given calendar date.
    Working day: 20:00 (8 PM) to 18:00 (6 PM) of next day.

    Args:
        date: Calendar date (YYYY-MM-DD)

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC
    """
    start = dt.datetime.combine(date, dt.time(20, 0, 0))
    end = dt.datetime.combine(date + dt.timedelta(days=1), dt.time(18, 0, 0))
    return start, end


@router.get(
    "/closed-sessions",
    response_model=list[ClosedSessionOut],
    dependencies=[Depends(require_roles("superadmin", "table_admin"))],
)
def list_closed_sessions(
    table_id: int | None = Query(default=None),
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get closed sessions with credit information per player.
    For table_admin: returns sessions for their assigned table only.
    For superadmin: returns sessions for specified table_id.
    """
    tid = _resolve_table_id_for_user(user, table_id, db)
    
    # Verify table exists
    table = db.query(Table).filter(Table.id == tid).first()
    if not table:
        raise HTTPException(status_code=404, detail=ErrorMessages.TABLE_NOT_FOUND)
    
    # Get closed sessions, sorted by created_at descending
    sessions = (
        db.query(Session)
        .options(
            joinedload(Session.dealer),
            joinedload(Session.waiter),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.rake_entries).joinedload(DealerRakeEntry.created_by),
        )
        .filter(Session.table_id == tid, Session.status == "closed")
        .order_by(Session.created_at.desc())
        .all()
    )
    
    if not sessions:
        return []
    
    # Batch load all related data to avoid N+1 queries
    session_ids = [s.id for s in sessions]
    
    # Load all seats for all sessions at once
    all_seats = (
        db.query(Seat)
        .filter(Seat.session_id.in_(session_ids))
        .all()
    )
    seats_by_session: dict[str, dict[int, Seat]] = {}
    for seat in all_seats:
        sid = cast(str, seat.session_id)
        if sid not in seats_by_session:
            seats_by_session[sid] = {}
        seats_by_session[sid][int(cast(int, seat.seat_no))] = seat
    
    # Load all chip purchases for all sessions at once
    all_chip_purchases = (
        db.query(ChipPurchase)
        .filter(ChipPurchase.session_id.in_(session_ids))
        .all()
    )

    # Group by session for credit display and cashout calculations
    credit_by_session: dict[str, dict[int, int]] = {}
    purchases_by_session: dict[str, list[ChipPurchase]] = {}
    for cp in all_chip_purchases:
        sid = cast(str, cp.session_id)

        # Track all purchases by session for cashout calculation
        if sid not in purchases_by_session:
            purchases_by_session[sid] = []
        purchases_by_session[sid].append(cp)

        # Track credit purchases for credit display (including payoffs)
        if cp.payment_type == "credit":
            seat_no = int(cast(int, cp.seat_no))
            amount = int(cast(int, cp.amount))
            if sid not in credit_by_session:
                credit_by_session[sid] = {}
            credit_by_session[sid][seat_no] = credit_by_session[sid].get(seat_no, 0) + amount

    # Load all chip ops for all sessions at once
    all_chip_ops = (
        db.query(ChipOp)
        .filter(ChipOp.session_id.in_(session_ids))
        .all()
    )
    chip_ops_by_session: dict[str, list[ChipOp]] = {}
    for op in all_chip_ops:
        sid = cast(str, op.session_id)
        if sid not in chip_ops_by_session:
            chip_ops_by_session[sid] = []
        chip_ops_by_session[sid].append(op)

    # Build set of ChipOp IDs that have corresponding ChipPurchases
    # These are actual money transactions (buyins/cashouts), not player losses
    chip_op_ids_with_purchases: set[int] = set()
    for cp in all_chip_purchases:
        chip_op_ids_with_purchases.add(int(cast(int, cp.chip_op_id)))
    
    # Build response
    out: list[ClosedSessionOut] = []
    for s in sessions:
        # Get dealer and waiter usernames
        dealer_username = None
        if s.dealer is not None:
            dealer_username = cast(str, s.dealer.username)
        
        waiter_username = None
        if s.waiter is not None:
            waiter_username = cast(str, s.waiter.username)
        
        # Get seats for this session
        seat_info = seats_by_session.get(cast(str, s.id), {})
        
        # Build credits list with player names
        credits = []
        credit_by_seat = credit_by_session.get(cast(str, s.id), {})
        for seat_no, amount in sorted(credit_by_seat.items()):
            seat = seat_info.get(seat_no)
            player_name = seat.player_name if seat and seat.player_name else None
            credits.append({
                "seat_no": seat_no,
                "player_name": player_name,
                "amount": amount
            })
        
        # Calculate totals
        # Buyins: positive ChipOps (player bought chips)
        chip_ops = chip_ops_by_session.get(cast(str, s.id), [])
        total_buyins = sum(int(cast(int, op.amount)) for op in chip_ops if op.amount > 0)

        # Cashouts: negative ChipPurchases (cash returned to player, e.g., forced cashout at session close)
        session_purchases = purchases_by_session.get(cast(str, s.id), [])
        total_cashouts = sum(int(cast(int, cp.amount)) for cp in session_purchases if cp.amount < 0)

        # Rake = buyins + cashouts (cashouts are negative, so this gives profit)
        total_rake = total_buyins + total_cashouts
        
        # Build dealer assignments list with rake per dealer
        dealer_assignments_out = []
        if s.dealer_assignments:
            # Calculate rake per dealer by counting player losses during each shift
            # Rake = chips lost by players (negative ChipOps WITHOUT corresponding ChipPurchase)
            # ChipOps WITH ChipPurchase are actual cashouts (money returned to player), not rake
            for assignment in s.dealer_assignments:
                assignment_start = cast(dt.datetime, assignment.started_at)
                was_replaced = assignment.ended_at is not None
                assignment_end = cast(dt.datetime, assignment.ended_at) if assignment.ended_at else cast(dt.datetime, s.closed_at) if s.closed_at else dt.datetime.utcnow()

                # Rake = sum of player losses (negative ChipOps without ChipPurchase)
                dealer_rake = 0
                for op in chip_ops:
                    op_id = int(cast(int, op.id))
                    # Skip if this ChipOp has a ChipPurchase (it's a real money transaction, not a loss)
                    if op_id in chip_op_ids_with_purchases:
                        continue

                    op_time = cast(dt.datetime, op.created_at)
                    amount = int(cast(int, op.amount))
                    if amount < 0:  # Player loss = casino gain
                        # Use exclusive end (<) for replaced dealers to avoid double-counting
                        # Use inclusive end (<=) for last dealer (session close)
                        if was_replaced:
                            if assignment_start <= op_time < assignment_end:
                                dealer_rake += abs(amount)
                        else:
                            if assignment_start <= op_time <= assignment_end:
                                dealer_rake += abs(amount)

                dealer_hourly_rate = None
                if assignment.dealer:
                    dealer_hourly_rate = int(cast(int, assignment.dealer.hourly_rate)) if assignment.dealer.hourly_rate else None

                # Build rake entries list
                rake_entries_out = []
                for entry in (assignment.rake_entries or []):
                    rake_entries_out.append(
                        DealerRakeEntryOut(
                            id=int(cast(int, entry.id)),
                            amount=int(cast(int, entry.amount)),
                            created_at=cast(dt.datetime, entry.created_at),
                            created_by_username=cast(str, entry.created_by.username) if entry.created_by else None,
                        )
                    )

                dealer_assignments_out.append(
                    SessionDealerAssignmentOut(
                        id=int(cast(int, assignment.id)),
                        dealer_id=int(cast(int, assignment.dealer_id)),
                        dealer_username=cast(str, assignment.dealer.username) if assignment.dealer else "Unknown",
                        dealer_hourly_rate=dealer_hourly_rate,
                        started_at=cast(dt.datetime, assignment.started_at),
                        ended_at=cast(dt.datetime, assignment.ended_at) if assignment.ended_at else None,
                        rake=dealer_rake,
                        rake_entries=rake_entries_out,
                    )
                )

        out.append(
            ClosedSessionOut(
                id=str(cast(str, s.id)),
                table_id=int(cast(int, s.table_id)),
                table_name=cast(str, table.name),
                date=cast(dt.date, s.date),
                created_at=cast(dt.datetime, s.created_at),
                closed_at=cast(dt.datetime, s.closed_at) if s.closed_at else cast(dt.datetime, s.created_at),
                dealer_id=int(cast(int, s.dealer_id)) if s.dealer_id else None,
                waiter_id=int(cast(int, s.waiter_id)) if s.waiter_id else None,
                dealer_username=dealer_username,
                waiter_username=waiter_username,
                chips_in_play=int(cast(int, s.chips_in_play)) if s.chips_in_play else None,
                total_rake=total_rake,
                total_buyins=total_buyins,
                total_cashouts=total_cashouts,
                credits=credits,
                dealer_assignments=dealer_assignments_out,
            )
        )
    
    return out


@router.post(
    "/close-credit",
    response_model=CloseCreditOut,
    dependencies=[Depends(require_roles("superadmin", "table_admin"))],
)
def close_player_credit(
    payload: CloseCreditIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Close player credit by creating a balance adjustment and removing the credit from the session.
    """
    # Verify session exists and is closed
    session = db.query(Session).filter(Session.id == payload.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.status != "closed":
        raise HTTPException(status_code=400, detail="Can only close credit for closed sessions")
    
    # Check table access
    role = cast(str, current_user.role)
    if role == "table_admin":
        # table_admin owns tables via owner_id, check if they own this session's table
        table = db.query(Table).filter(Table.id == session.table_id).first()
        if not table or int(cast(int, table.owner_id)) != int(cast(int, current_user.id)):
            raise HTTPException(status_code=403, detail="Forbidden for this table")
    
    # Verify seat exists
    seat = (
        db.query(Seat)
        .filter(Seat.session_id == payload.session_id, Seat.seat_no == payload.seat_no)
        .first()
    )
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")
    
    # Get player name for the comment
    player_name = seat.player_name if seat.player_name else f"Seat {payload.seat_no}"
    
    # Calculate total credit for this seat
    credit_purchases = CreditService.get_credit_purchases_for_seat(
        db, payload.session_id, payload.seat_no
    )
    total_credit = CreditService.calculate_total_credit(credit_purchases)
    
    if total_credit == 0:
        raise HTTPException(status_code=400, detail="No credit found for this player")
    
    if payload.amount > total_credit:
        raise HTTPException(
            status_code=400,
            detail=f"Amount exceeds available credit. Available: {total_credit}, Requested: {payload.amount}"
        )
    
    # Close the credit using the service
    CreditService.close_credit(db, session, seat, payload.amount, current_user)
    
    # Get the adjustment that was just created
    table = db.query(Table).filter(Table.id == session.table_id).first()
    table_name = table.name if table else "Unknown"
    session_date = session.date.strftime("%d.%m.%Y") if session.date else ""
    
    adjustment = (
        db.query(CasinoBalanceAdjustment)
        .filter(
            CasinoBalanceAdjustment.comment == f"Долг ({player_name}) - {table_name} - {session_date}",
            CasinoBalanceAdjustment.amount == payload.amount,
            CasinoBalanceAdjustment.created_by_user_id == current_user.id,
        )
        .order_by(CasinoBalanceAdjustment.id.desc())
        .first()
    )
    
    db.commit()
    
    return CloseCreditOut(
        success=True,
        message=f"Successfully closed {payload.amount} credit for {player_name}",
        adjustment_id=int(cast(int, adjustment.id)) if adjustment else None,
    )
