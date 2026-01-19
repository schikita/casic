"""
Comprehensive XLSX report export for superadmin.
Includes:
- Table states (per-seat totals)
- Chip purchase chronology
- Staff working hours and salary calculations
- Profit/expense summary
"""
from __future__ import annotations

import datetime as dt
import io
from typing import Any, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session as DBSession, joinedload
from sqlalchemy import func

from ..core.deps import get_current_user, get_db, require_roles
from ..models.db import CasinoBalanceAdjustment, ChipPurchase, Seat, Session, SessionDealerAssignment, Table, User, ChipOp
from .admin import _resolve_table_id_for_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


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


@router.get("/day-summary/preselected-date")
def get_preselected_date(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(require_roles("superadmin", "table_admin")),
):
    """
    Get the preselected date for the daily summary page.
    
    Returns the starting day of:
    1. Current working day if it's not yet finished (has open sessions)
    2. Most recent working day if current one is finished but next hasn't started
    
    Working day: 20:00 (8 PM) to 18:00 (6 PM) of next day.
    
    For table_admin: only considers sessions for their assigned table.
    For superadmin: considers all sessions.
    """
    # Resolve table_id for the user
    table_id = _resolve_table_id_for_user(current_user)
    
    now = dt.datetime.utcnow()
    
    # Determine current working day
    # Working day starts at 20:00 and ends at 18:00 next day
    # So if current time is before 18:00, we're in the working day that started yesterday
    # If current time is 18:00 or later, we're in the working day that started today
    if now.hour < 18:
        # Before 18:00 - we're in the working day that started yesterday
        working_day_start = now.date() - dt.timedelta(days=1)
    else:
        # 18:00 or later - we're in the working day that started today
        working_day_start = now.date()
    
    # Get working day boundaries
    start_time, end_time = _get_working_day_boundaries(working_day_start)
    
    # Check for open sessions in current working day
    query = (
        db.query(Session)
        .filter(Session.created_at >= start_time, Session.created_at < end_time)
        .filter(Session.table_id == table_id)
    )
    open_sessions = query.filter(Session.status == "open").first()
    
    if open_sessions:
        # Current working day is not finished
        return {"date": working_day_start.isoformat()}
    
    # Check if current working day has any sessions at all
    any_sessions = query.first()
    
    if any_sessions:
        # Current working day is finished (all sessions closed)
        return {"date": working_day_start.isoformat()}
    
    # No sessions in current working day - find most recent working day with sessions
    # Look back up to 7 days
    for days_back in range(1, 8):
        prev_day = working_day_start - dt.timedelta(days=days_back)
        prev_start, prev_end = _get_working_day_boundaries(prev_day)
        
        prev_sessions = (
            db.query(Session)
            .filter(Session.created_at >= prev_start, Session.created_at < prev_end)
            .filter(Session.table_id == table_id)
            .first()
        )
        
        if prev_sessions:
            return {"date": prev_day.isoformat()}
    
    # No sessions found in the last 7 days, return current working day
    return {"date": working_day_start.isoformat()}


@router.get("/day-summary")
def get_day_summary(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    table_id: int | None = Query(default=None, description="Optional table_id for superadmin to specify a table"),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(require_roles("superadmin", "table_admin")),
):
    """Get day summary data (profit/loss) as JSON for mobile display.
    
    For table_admin: only shows data for their assigned table, excludes salaries and balance adjustments.
    For superadmin: if table_id is provided, shows data for that table; otherwise shows all tables.
    """
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # DIAGNOSTIC LOGGING: Initialize logger
    import logging
    logger = logging.getLogger(__name__)

    # Resolve table_id for the user
    resolved_table_id = _resolve_table_id_for_user(current_user, table_id)

    # Determine if user is table_admin
    is_table_admin = cast(str, current_user.role) == "table_admin"

    # DIAGNOSTIC LOGGING: User role and table admin status
    logger.info(f"=== DAY SUMMARY DIAGNOSTICS FOR {date} ===")
    logger.info(f"--- USER ROLE DIAGNOSTICS ---")
    logger.info(f"current_user.role: {current_user.role}")
    logger.info(f"is_table_admin: {is_table_admin}")
    logger.info(f"resolved_table_id: {resolved_table_id}")

    # Get working day boundaries (20:00 to 18:00 next day)
    start_time, end_time = _get_working_day_boundaries(d)
    
    # DIAGNOSTIC LOGGING
    logger.info(f"Working day boundaries: {start_time.isoformat()} to {end_time.isoformat()}")

    # Fetch sessions for the working day
    sessions_query = (
        db.query(Session)
        .options(
            joinedload(Session.dealer),
            joinedload(Session.waiter),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
        )
        .filter(Session.created_at >= start_time, Session.created_at < end_time)
    )
    
    # Filter by table_id if provided
    if resolved_table_id is not None:
        sessions_query = sessions_query.filter(Session.table_id == resolved_table_id)
    
    sessions = sessions_query.order_by(Session.table_id.asc(), Session.created_at.asc()).all()

    session_ids = [cast(str, s.id) for s in sessions]

    # Fetch seats for all sessions
    seats_by_session: dict[str, list[Seat]] = {}
    if session_ids:
        seats = (
            db.query(Seat)
            .filter(Seat.session_id.in_(session_ids))
            .all()
        )
        for seat in seats:
            sid = cast(str, seat.session_id)
            seats_by_session.setdefault(sid, []).append(seat)

    # Fetch all chip purchases for the date
    purchases = (
        db.query(ChipPurchase)
        .filter(ChipPurchase.session_id.in_(session_ids))
        .all()
    ) if session_ids else []

    # Fetch balance adjustments for the working day
    # Balance adjustments are now shown to both superadmin and table_admin
    balance_adjustments = (
        db.query(CasinoBalanceAdjustment)
        .options(joinedload(CasinoBalanceAdjustment.created_by))
        .filter(CasinoBalanceAdjustment.created_at >= start_time, CasinoBalanceAdjustment.created_at < end_time)
        .order_by(CasinoBalanceAdjustment.created_at.asc())
        .all()
    )

    # DIAGNOSTIC LOGGING: Balance adjustments
    logger.info(f"--- BALANCE ADJUSTMENTS DIAGNOSTICS ---")
    logger.info(f"balance_adjustments length: {len(balance_adjustments)}")
    logger.info(f"is_table_admin: {is_table_admin}")

    # Fetch staff who worked on sessions in this working day
    # For table_admin: only staff who worked on their table's sessions
    # For superadmin: all staff (or filtered by table_id if provided)
    if is_table_admin:
        # Get unique dealer and waiter IDs from the sessions
        dealer_ids = set()
        waiter_ids = set()
        for s in sessions:
            # Get all dealers from dealer_assignments
            for assignment in s.dealer_assignments:
                if assignment.dealer_id:
                    dealer_ids.add(int(cast(int, assignment.dealer_id)))
            # Get waiter from session
            if s.waiter_id:
                waiter_ids.add(int(cast(int, s.waiter_id)))

        staff_ids = dealer_ids | waiter_ids
        staff = db.query(User).filter(User.id.in_(staff_ids)).all() if staff_ids else []
    else:
        # Superadmin: get all staff
        staff = db.query(User).filter(User.role.in_(["dealer", "waiter"])).all()

    # DIAGNOSTIC LOGGING: Staff
    logger.info(f"--- STAFF DIAGNOSTICS ---")
    logger.info(f"staff length: {len(staff)}")
    logger.info(f"is_table_admin: {is_table_admin}")

    # Calculate totals
    total_chip_income_cash = 0  # Cash buyins (positive only)
    total_chip_cashout = 0  # Cash cashouts (absolute value, negative amounts)
    total_chip_income_credit = 0  # Credit buyins (credit part of income)
    total_balance_adjustments_profit = 0  # Positive adjustments
    total_balance_adjustments_expense = 0  # Negative adjustments (absolute value)

    for p in purchases:
        amount = int(cast(int, p.amount))
        if amount > 0:  # Buyin
            if p.payment_type == "credit":
                total_chip_income_credit += amount
            else:
                total_chip_income_cash += amount
        elif amount < 0:  # Cashout (negative amount = expense)
            # Cashouts are always cash payments back to players
            total_chip_cashout += abs(amount)  # Track cashouts separately

    # Process balance adjustments
    balance_adjustments_list = []
    for adj in balance_adjustments:
        amount = int(cast(int, adj.amount))
        created_by_username = cast(str, adj.created_by.username) if adj.created_by else "—"
        
        adjustment_data = {
            "id": int(cast(int, adj.id)),
            "created_at": cast(dt.datetime, adj.created_at).isoformat(),
            "amount": amount,
            "comment": cast(str, adj.comment),
            "created_by_username": created_by_username,
        }
        balance_adjustments_list.append(adjustment_data)
        
        if amount > 0:
            total_balance_adjustments_profit += amount
        else:
            total_balance_adjustments_expense += abs(amount)

    # Calculate staff salary for both superadmin and table_admin
    # For table_admin: only staff who worked on their table
    # For superadmin: all staff (or filtered by table_id if provided)
    total_salary = 0
    staff_details = []
    for person in staff:
        role = cast(str, person.role)
        hourly_rate = int(cast(int, person.hourly_rate)) if person.hourly_rate else 0

        if role == "dealer":
            hours = _calculate_dealer_hours(sessions, int(cast(int, person.id)))
        else:
            hours = _calculate_waiter_hours(sessions, int(cast(int, person.id)))

        salary = round(hours * hourly_rate)
        if hours > 0:
            staff_details.append({
                "name": person.username,
                "role": role,
                "hours": round(hours, 2),
                "hourly_rate": hourly_rate,
                "salary": salary,
            })
        total_salary += salary

    # DIAGNOSTIC LOGGING: Total salary
    logger.info(f"--- SALARY DIAGNOSTICS ---")
    logger.info(f"total_salary: {total_salary}")
    logger.info(f"is_table_admin: {is_table_admin}")

    # Calculate net per-seat totals
    total_player_balance = 0
    for sid, seats in seats_by_session.items():
        for seat in seats:
            total_player_balance += int(cast(int, seat.total))

    # Gross rake ("грязный") = table result BEFORE out-of-table expenses
    # (salaries, negative balance adjustments). It includes credit as part of income.
    gross_rake = (total_chip_income_cash + total_chip_income_credit) - total_chip_cashout - total_player_balance

    # Net result for the day = gross_rake - salaries + balance_adjustments_profit - balance_adjustments_expense
    # Note: credit is NOT subtracted here; it's shown as a "credit part" inside gross_rake.
    net_result = gross_rake - total_salary + total_balance_adjustments_profit - total_balance_adjustments_expense
    
    # DIAGNOSTIC LOGGING
    logger.info(f"--- CALCULATION COMPONENTS ---")
    logger.info(f"total_chip_income_cash (cash buyins): {total_chip_income_cash}")
    logger.info(f"total_chip_cashout (cashouts to players): {total_chip_cashout}")
    logger.info(f"total_player_balance (chips players have): {total_player_balance}")
    logger.info(f"total_salary: {total_salary}")
    logger.info(f"total_chip_income_credit (credit buyins): {total_chip_income_credit}")
    logger.info(f"total_balance_adjustments_profit: {total_balance_adjustments_profit}")
    logger.info(f"total_balance_adjustments_expense: {total_balance_adjustments_expense}")
    logger.info(f"--- FORMULAS ---")
    logger.info(
        f"gross_rake = ({total_chip_income_cash} + {total_chip_income_credit}) - {total_chip_cashout} - {total_player_balance} = {gross_rake}"
    )
    logger.info(
        f"net_result = {gross_rake} - {total_salary} + {total_balance_adjustments_profit} - {total_balance_adjustments_expense} = {net_result}"
    )
    logger.info(f"--- BALANCE ADJUSTMENTS DETAIL ---")
    for adj in balance_adjustments_list:
        logger.info(f"  ID {adj['id']}: {adj['comment']} = {adj['amount']} ₪ (by {adj['created_by_username']})")
    logger.info(f"--- SESSIONS DETAIL ---")
    for s in sessions:
        sid = cast(str, s.id)
        seats = seats_by_session.get(sid, [])
        session_balance = sum(int(cast(int, seat.total)) for seat in seats)
        logger.info(f"  Session {sid} (Table {s.table_id}, {s.status}): player_balance = {session_balance}")
    logger.info(f"=== END DIAGNOSTICS ===")

    open_sessions = len([s for s in sessions if s.status == "open"])

    # DIAGNOSTIC LOGGING: Complete response structure
    # Build response - both superadmin and table_admin now see all fields
    # For table_admin: data is filtered to their table only
    # For superadmin: data is casino-wide or filtered by table_id if provided
    response_data = {
        "date": date,
        "working_day_start": start_time.isoformat(),
        "working_day_end": end_time.isoformat(),
        "income": {
            "gross_rake": gross_rake,
            "credit_part": total_chip_income_credit,
            "balance_adjustments": total_balance_adjustments_profit,
        },
        "expenses": {
            "salaries": total_salary,
            "balance_adjustments": total_balance_adjustments_expense,
        },
        "result": net_result,
        "info": {
            "buyin_cash": total_chip_income_cash,
            "buyin_credit": total_chip_income_credit,
            "cashout": total_chip_cashout,
            "player_balance": total_player_balance,
            "total_sessions": len(sessions),
            "open_sessions": open_sessions,
        },
        "staff": staff_details,
        "balance_adjustments": balance_adjustments_list,
    }
    logger.info(f"=== COMPLETE RESPONSE STRUCTURE ===")
    logger.info(f"Response: {response_data}")
    logger.info(f"=== END RESPONSE DIAGNOSTICS ===")

    return response_data


# Style constants
HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
MONEY_POSITIVE_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
MONEY_NEGATIVE_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
# Dark shades for payment types
CASH_DARK_FILL = PatternFill(start_color="006400", end_color="006400", fill_type="solid")  # Dark green
CREDIT_DARK_FILL = PatternFill(start_color="8B0000", end_color="8B0000", fill_type="solid")  # Dark red
THIN_BORDER = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)


def _style_header(ws, row: int, cols: int):
    """Apply header styling to a row."""
    for col in range(1, cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER


def _auto_width(ws):
    """Auto-adjust column widths with better minimum width for readability."""
    from openpyxl.cell.cell import MergedCell

    for column_cells in ws.columns:
        max_length = 0
        column = None

        # Find the first non-merged cell to get the column letter
        for cell in column_cells:
            if not isinstance(cell, MergedCell):
                column = cell.column_letter
                break

        if column is None:
            continue  # Skip if all cells in column are merged

        for cell in column_cells:
            try:
                if not isinstance(cell, MergedCell) and cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        # Increased minimum width from (max_length + 2) to (max_length + 4) for better fit
        # Also increased maximum from 50 to 60 for longer text fields
        adjusted_width = min(max_length + 4, 60)
        # Ensure minimum width of 12 for very short columns
        adjusted_width = max(adjusted_width, 12)
        ws.column_dimensions[column].width = adjusted_width


def _apply_session_border(ws, start_row: int, end_row: int, max_col: int = 5):
    """Apply a border around a session block to visually separate it."""
    thin_border_side = Side(style='thin', color='808080')

    for row in range(start_row, end_row + 1):
        for col in range(1, max_col + 1):
            cell = ws.cell(row=row, column=col)

            # Determine which borders to apply
            top = thin_border_side if row == start_row else None
            bottom = thin_border_side if row == end_row else None
            left = thin_border_side if col == 1 else None
            right = thin_border_side if col == max_col else None

            # Only update border if we need to add one
            if top or bottom or left or right:
                current_border = cell.border
                cell.border = Border(
                    left=left or current_border.left,
                    right=right or current_border.right,
                    top=top or current_border.top,
                    bottom=bottom or current_border.bottom
                )


def _calculate_waiter_hours(
    sessions: list[Session],
    waiter_id: int,
) -> float:
    """
    Calculate waiter working hours accounting for overlapping sessions.
    Waiters can work on multiple sessions at a time, so we need to merge
    overlapping time intervals.
    """
    intervals: list[tuple[dt.datetime, dt.datetime]] = []

    for s in sessions:
        if s.waiter_id != waiter_id:
            continue
        start = cast(dt.datetime, s.created_at)
        end = cast(dt.datetime, s.closed_at) if s.closed_at else dt.datetime.utcnow()
        intervals.append((start, end))

    if not intervals:
        return 0.0

    # Sort by start time
    intervals.sort(key=lambda x: x[0])

    # Merge overlapping intervals
    merged: list[tuple[dt.datetime, dt.datetime]] = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            # Overlapping, extend the end if needed
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    # Sum total hours
    total_seconds = sum((end - start).total_seconds() for start, end in merged)
    return total_seconds / 3600.0


def _calculate_dealer_hours(
    sessions: list[Session],
    dealer_id: int,
) -> float:
    """
    Calculate dealer working hours using SessionDealerAssignment records.
    This accounts for dealer changes within a session.

    If a session has dealer_assignments, use those for accurate time tracking.
    Otherwise, fall back to the legacy dealer_id field for backward compatibility.
    """
    total_seconds = 0.0
    now = dt.datetime.utcnow()

    for s in sessions:
        # Check if session has dealer assignments (new method)
        if s.dealer_assignments:
            for assignment in s.dealer_assignments:
                if int(cast(int, assignment.dealer_id)) != dealer_id:
                    continue
                start = cast(dt.datetime, assignment.started_at)
                end = cast(dt.datetime, assignment.ended_at) if assignment.ended_at else now
                total_seconds += (end - start).total_seconds()
        else:
            # Fallback to legacy method for sessions without dealer_assignments
            if s.dealer_id != dealer_id:
                continue
            start = cast(dt.datetime, s.created_at)
            end = cast(dt.datetime, s.closed_at) if s.closed_at else now
            total_seconds += (end - start).total_seconds()

    return total_seconds / 3600.0


def _calculate_session_dealer_earnings(
    session: Session,
    db,
) -> list[dict]:
    """
    Calculate earnings for all dealers who worked on this session.
    Returns list of dicts with dealer info, hours worked, and salary.
    """
    from ..models.db import SessionDealerAssignment, User

    earnings = []
    now = dt.datetime.utcnow()

    # Get all dealer assignments for this session
    if session.dealer_assignments:
        # Use dealer assignments (new method)
        for assignment in session.dealer_assignments:
            dealer = assignment.dealer
            if not dealer:
                continue

            start = cast(dt.datetime, assignment.started_at)
            end = cast(dt.datetime, assignment.ended_at) if assignment.ended_at else (
                cast(dt.datetime, session.closed_at) if session.closed_at else now
            )
            hours = (end - start).total_seconds() / 3600.0
            hourly_rate = int(cast(int, dealer.hourly_rate)) if dealer.hourly_rate else 0
            salary = round(hours * hourly_rate)

            earnings.append({
                "dealer_name": cast(str, dealer.username),
                "hours": hours,
                "hourly_rate": hourly_rate,
                "salary": salary,
            })
    elif session.dealer_id:
        # Fallback to legacy method for sessions without dealer_assignments
        dealer = db.query(User).filter(User.id == session.dealer_id).first()
        if dealer:
            start = cast(dt.datetime, session.created_at)
            end = cast(dt.datetime, session.closed_at) if session.closed_at else now
            hours = (end - start).total_seconds() / 3600.0
            hourly_rate = int(cast(int, dealer.hourly_rate)) if dealer.hourly_rate else 0
            salary = round(hours * hourly_rate)

            earnings.append({
                "dealer_name": cast(str, dealer.username),
                "hours": hours,
                "hourly_rate": hourly_rate,
                "salary": salary,
            })

    return earnings


def _calculate_session_waiter_earnings(
    session: Session,
    db,
) -> dict | None:
    """
    Calculate earnings for the waiter who worked on this session.
    Returns dict with waiter info, hours worked, and salary, or None if no waiter.
    """
    from ..models.db import User

    if not session.waiter_id:
        return None

    waiter = db.query(User).filter(User.id == session.waiter_id).first()
    if not waiter:
        return None

    now = dt.datetime.utcnow()
    start = cast(dt.datetime, session.created_at)
    end = cast(dt.datetime, session.closed_at) if session.closed_at else now
    hours = (end - start).total_seconds() / 3600.0
    hourly_rate = int(cast(int, waiter.hourly_rate)) if waiter.hourly_rate else 0
    salary = round(hours * hourly_rate)

    return {
        "waiter_name": cast(str, waiter.username),
        "hours": hours,
        "hourly_rate": hourly_rate,
        "salary": salary,
    }


@router.get("/export-report")
def export_report(
    date: str = Query(..., description="YYYY-MM-DD"),
    table_id: int | None = Query(default=None, description="Optional table_id for superadmin to specify a table"),
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate comprehensive XLSX report for a specific date.
    
    For table_admin: only includes data for their assigned table, excludes salaries and balance adjustments.
    For superadmin: if table_id is provided, includes data for that table; otherwise includes all tables.
    """
    # Check user role
    role = cast(str, user.role)
    if role not in ("superadmin", "table_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # Determine if user is table_admin
    is_table_admin = role == "table_admin"
    
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (expected YYYY-MM-DD)")

    # Resolve table_id for the user
    resolved_table_id = _resolve_table_id_for_user(user, table_id)

    # Get working day boundaries (20:00 to 18:00 next day)
    start_time, end_time = _get_working_day_boundaries(d)

    # Fetch all data for the working day
    tables = db.query(Table).order_by(Table.id.asc()).all()
    sessions_query = (
        db.query(Session)
        .options(
            joinedload(Session.dealer),
            joinedload(Session.waiter),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
        )
        .filter(Session.created_at >= start_time, Session.created_at < end_time)
    )
    
    # Filter by table_id if provided
    if resolved_table_id is not None:
        sessions_query = sessions_query.filter(Session.table_id == resolved_table_id)
    
    sessions = sessions_query.order_by(Session.table_id.asc(), Session.created_at.asc()).all()

    session_ids = [cast(str, s.id) for s in sessions]

    # Fetch seats for all sessions
    seats_by_session: dict[str, list[Seat]] = {}
    if session_ids:
        seats = (
            db.query(Seat)
            .filter(Seat.session_id.in_(session_ids))
            .order_by(Seat.session_id.asc(), Seat.seat_no.asc())
            .all()
        )
        for seat in seats:
            sid = cast(str, seat.session_id)
            seats_by_session.setdefault(sid, []).append(seat)

    # Fetch all chip purchases for the date
    purchases = (
        db.query(ChipPurchase)
        .options(joinedload(ChipPurchase.created_by))
        .filter(ChipPurchase.session_id.in_(session_ids))
        .order_by(ChipPurchase.created_at.asc())
        .all()
    ) if session_ids else []

    # Fetch balance adjustments for the working day
    # Note: Balance adjustments are global (not associated with any table/session),
    # so they are shown to all users regardless of table filtering
    # However, table_admins should not see balance adjustments
    balance_adjustments = (
        db.query(CasinoBalanceAdjustment)
        .options(joinedload(CasinoBalanceAdjustment.created_by))
        .filter(CasinoBalanceAdjustment.created_at >= start_time, CasinoBalanceAdjustment.created_at < end_time)
        .order_by(CasinoBalanceAdjustment.created_at.asc())
        .all()
    ) if not is_table_admin else []

    # Fetch all staff (dealers and waiters) - only for superadmin
    staff = db.query(User).filter(User.role.in_(["dealer", "waiter"])).all() if not is_table_admin else []

    # Create workbook
    wb = Workbook()
    wb.remove(wb.active)  # Remove default sheet

    # Sheet 1: Table States (per-seat summary for each table)
    _create_table_states_sheet(wb, tables, sessions, seats_by_session, db)

    # Sheet 2: Chip Purchase Chronology
    _create_purchases_sheet(wb, purchases, tables, db)

    # Sheet 3: Staff Salaries (only for superadmin)
    if not is_table_admin:
        _create_staff_sheet(wb, sessions, staff, d)

    # Sheet 4: Balance Adjustments (only for superadmin)
    if not is_table_admin:
        _create_balance_adjustments_sheet(wb, balance_adjustments, d)

    # Sheet 5: Summary (Profit/Expense)
    _create_summary_sheet(wb, sessions, seats_by_session, purchases, staff, balance_adjustments, d, is_table_admin)

    # Generate file
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"casino_report_{date}.xlsx"

    headers = {
        "Content-Disposition": (
            f'attachment; filename="{filename}"; '
            f"filename*=UTF-8''{quote(filename)}"
        )
    }

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )



def _create_table_states_sheet(
    wb: Workbook,
    tables: list[Table],
    sessions: list[Session],
    seats_by_session: dict[str, list[Seat]],
    db,
):
    """Create sheet with table states - seats, players, totals, and staff earnings."""
    ws = wb.create_sheet(title="Состояние столов")

    if not sessions:
        ws.cell(row=1, column=1, value="Нет данных за выбранную дату")
        ws.cell(row=1, column=1).font = Font(italic=True)
        return

    # Define visual styles for tables and sessions
    table_header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")  # Blue
    session_header_fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")  # Light gray
    thick_border = Border(
        left=Side(style='thick'),
        right=Side(style='thick'),
        top=Side(style='thick'),
        bottom=Side(style='thick')
    )
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    row = 1
    for table in tables:
        table_sessions = [s for s in sessions if s.table_id == table.id]
        if not table_sessions:
            continue

        # Table header with blue background and thick border
        table_header_cell = ws.cell(row=row, column=1, value=f"Стол: {table.name}")
        table_header_cell.font = Font(bold=True, size=14, color="FFFFFF")
        table_header_cell.fill = table_header_fill
        table_header_cell.border = thick_border
        # Merge cells for table header to span across columns
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
        for col in range(1, 6):
            ws.cell(row=row, column=col).fill = table_header_fill
            ws.cell(row=row, column=col).border = thick_border
        row += 1

        for session in table_sessions:
            session_start_row = row  # Track where this session starts
            sid = cast(str, session.id)
            seats = seats_by_session.get(sid, [])

            # Session info with gray background and thin border
            start_time = cast(dt.datetime, session.created_at).strftime("%H:%M")
            if session.closed_at:
                end_time = cast(dt.datetime, session.closed_at).strftime("%H:%M")
            elif session.status == "closed":
                end_time = "закрыта"
            else:
                end_time = "открыта"

            # Show all dealers if there are multiple concurrent dealers
            if session.dealer_assignments and len(session.dealer_assignments) > 0:
                active_dealers = [a for a in session.dealer_assignments if not a.ended_at]
                if len(active_dealers) > 1:
                    dealer_names = ", ".join([a.dealer.username if a.dealer else "—" for a in active_dealers])
                    dealer_name = f"{dealer_names} (несколько)"
                elif len(active_dealers) == 1:
                    dealer_name = active_dealers[0].dealer.username if active_dealers[0].dealer else "—"
                else:
                    # All dealers ended, show the last one
                    dealer_name = session.dealer.username if session.dealer else "—"
            else:
                dealer_name = session.dealer.username if session.dealer else "—"

            waiter_name = session.waiter.username if session.waiter else "—"
            status_text = "закрыта" if session.status == "closed" else "открыта"
            chips_in_play = int(cast(int, session.chips_in_play))

            # Session header row with light gray background
            session_cells = [
                (1, f"Сессия: {start_time} - {end_time}"),
                (2, f"Дилер: {dealer_name}"),
                (3, f"Официант: {waiter_name}"),
                (4, f"Статус: {status_text}")
            ]
            for col, value in session_cells:
                cell = ws.cell(row=row, column=col, value=value)
                cell.fill = session_header_fill
                cell.border = thin_border
                cell.font = Font(bold=True)
            row += 1

            # Chips in play info
            ws.cell(row=row, column=1, value=f"Фишек на столе: {chips_in_play}")
            row += 1

            # Seats header
            headers = ["Место", "Игрок", "Итого фишек"]
            for col, h in enumerate(headers, 1):
                ws.cell(row=row, column=col, value=h)
            _style_header(ws, row, len(headers))
            row += 1

            # Seat data - only show seats with players or non-zero totals
            session_total = 0
            for seat in seats:
                total = int(cast(int, seat.total))
                player = cast(str, seat.player_name) if seat.player_name else ""

                # Show all seats that have activity
                if player or total != 0:
                    ws.cell(row=row, column=1, value=int(cast(int, seat.seat_no)))
                    ws.cell(row=row, column=2, value=player)
                    cell = ws.cell(row=row, column=3, value=total)
                    if total > 0:
                        cell.fill = MONEY_POSITIVE_FILL
                    elif total < 0:
                        cell.fill = MONEY_NEGATIVE_FILL
                    row += 1
                session_total += total

            # Session total
            ws.cell(row=row, column=2, value="ИТОГО сессии:")
            ws.cell(row=row, column=2).font = Font(bold=True)
            cell = ws.cell(row=row, column=3, value=session_total)
            cell.font = Font(bold=True)
            if session_total > 0:
                cell.fill = MONEY_POSITIVE_FILL
            elif session_total < 0:
                cell.fill = MONEY_NEGATIVE_FILL
            row += 1

            # Staff earnings section
            dealer_earnings = _calculate_session_dealer_earnings(session, db)
            waiter_earnings = _calculate_session_waiter_earnings(session, db)

            if dealer_earnings or waiter_earnings:
                row += 1  # Add spacing
                ws.cell(row=row, column=1, value="Зарплаты персонала:")
                ws.cell(row=row, column=1).font = Font(bold=True, italic=True)
                row += 1

                # Dealer earnings header
                if dealer_earnings:
                    staff_headers = ["Сотрудник", "Роль", "Часов", "Ставка/час", "Зарплата"]
                    for col, h in enumerate(staff_headers, 1):
                        ws.cell(row=row, column=col, value=h)
                    _style_header(ws, row, len(staff_headers))
                    row += 1

                    # Display each dealer's earnings
                    total_dealer_salary = 0
                    for earning in dealer_earnings:
                        ws.cell(row=row, column=1, value=earning["dealer_name"])
                        ws.cell(row=row, column=2, value="Дилер")
                        ws.cell(row=row, column=3, value=round(earning["hours"], 2))
                        ws.cell(row=row, column=4, value=earning["hourly_rate"])
                        salary_cell = ws.cell(row=row, column=5, value=earning["salary"])
                        salary_cell.fill = MONEY_NEGATIVE_FILL  # Salary is an expense
                        total_dealer_salary += earning["salary"]
                        row += 1

                    # Show total if multiple dealers
                    if len(dealer_earnings) > 1:
                        ws.cell(row=row, column=4, value="Итого дилеры:")
                        ws.cell(row=row, column=4).font = Font(bold=True)
                        total_cell = ws.cell(row=row, column=5, value=total_dealer_salary)
                        total_cell.font = Font(bold=True)
                        total_cell.fill = MONEY_NEGATIVE_FILL
                        row += 1

                # Waiter earnings
                if waiter_earnings:
                    # Add header if not already added
                    if not dealer_earnings:
                        staff_headers = ["Сотрудник", "Роль", "Часов", "Ставка/час", "Зарплата"]
                        for col, h in enumerate(staff_headers, 1):
                            ws.cell(row=row, column=col, value=h)
                        _style_header(ws, row, len(staff_headers))
                        row += 1

                    ws.cell(row=row, column=1, value=waiter_earnings["waiter_name"])
                    ws.cell(row=row, column=2, value="Официант")
                    ws.cell(row=row, column=3, value=round(waiter_earnings["hours"], 2))
                    ws.cell(row=row, column=4, value=waiter_earnings["hourly_rate"])
                    salary_cell = ws.cell(row=row, column=5, value=waiter_earnings["salary"])
                    salary_cell.fill = MONEY_NEGATIVE_FILL  # Salary is an expense
                    row += 1

            # Apply border around the entire session block
            session_end_row = row - 1
            _apply_session_border(ws, session_start_row, session_end_row, max_col=5)

            row += 1  # Extra space after session

        row += 1  # Extra space between tables

    _auto_width(ws)


def _create_purchases_sheet(
    wb: Workbook,
    purchases: list[ChipPurchase],
    tables: list[Table],
    db: DBSession,
):
    """Create sheet with chip purchase chronology."""
    ws = wb.create_sheet(title="Хронология покупок")

    # Headers
    headers = ["Время", "Стол", "Место", "Сумма", "Тип оплаты", "Выдал"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    _style_header(ws, 1, len(headers))

    if not purchases:
        ws.cell(row=2, column=1, value="Нет покупок за выбранную дату")
        ws.cell(row=2, column=1).font = Font(italic=True)
        _auto_width(ws)
        return

    tables_by_id = {t.id: t for t in tables}

    row = 2
    for p in purchases:
        time_str = cast(dt.datetime, p.created_at).strftime("%H:%M:%S")
        table = tables_by_id.get(int(cast(int, p.table_id)))
        table_name = cast(str, table.name) if table else f"ID {p.table_id}"

        ws.cell(row=row, column=1, value=time_str)
        ws.cell(row=row, column=2, value=table_name)
        ws.cell(row=row, column=3, value=int(cast(int, p.seat_no)))

        amount = int(cast(int, p.amount))
        cell = ws.cell(row=row, column=4, value=amount)
        # For cashouts (negative), show as expense (red)
        # For buyins (positive), show as income (green)
        if amount > 0:
            cell.fill = MONEY_POSITIVE_FILL
        elif amount < 0:
            cell.fill = MONEY_NEGATIVE_FILL

        # Payment type column
        # For cashouts, show "выдача" (payout) instead of payment type
        if amount < 0:
            payment_text = "выдача"
            payment_cell = ws.cell(row=row, column=5, value=payment_text)
            payment_cell.fill = MONEY_NEGATIVE_FILL
            payment_cell.font = Font(bold=True)
        else:
            payment_type = cast(str, p.payment_type) if p.payment_type else "cash"
            payment_text = "наличные" if payment_type == "cash" else "кредит"
            payment_cell = ws.cell(row=row, column=5, value=payment_text)
            # Apply dark color coding for payment type
            if payment_type == "cash":
                payment_cell.fill = CASH_DARK_FILL
                payment_cell.font = Font(color="FFFFFF", bold=True)
            else:  # credit
                payment_cell.fill = CREDIT_DARK_FILL
                payment_cell.font = Font(color="FFFFFF", bold=True)

        username = cast(str, p.created_by.username) if p.created_by else "—"
        ws.cell(row=row, column=6, value=username)

        row += 1

    _auto_width(ws)



def _create_staff_sheet(
    wb: Workbook,
    sessions: list[Session],
    staff: list[User],
    report_date: dt.date,
):
    """Create sheet with staff working hours and salary calculations."""
    ws = wb.create_sheet(title="Зарплаты персонала")

    # Headers
    headers = ["Сотрудник", "Роль", "Часов", "Ставка/час", "Зарплата"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    _style_header(ws, 1, len(headers))

    row = 2
    total_salary = 0

    for person in staff:
        username = cast(str, person.username)
        role = cast(str, person.role)
        hourly_rate = int(cast(int, person.hourly_rate)) if person.hourly_rate else 0

        # Calculate hours based on role
        if role == "dealer":
            hours = _calculate_dealer_hours(sessions, int(cast(int, person.id)))
        else:  # waiter
            hours = _calculate_waiter_hours(sessions, int(cast(int, person.id)))

        if hours == 0:
            continue  # Skip staff with no hours

        salary = round(hours * hourly_rate)
        total_salary += salary

        ws.cell(row=row, column=1, value=username)
        ws.cell(row=row, column=2, value="Дилер" if role == "dealer" else "Официант")
        ws.cell(row=row, column=3, value=round(hours, 2))
        ws.cell(row=row, column=4, value=hourly_rate)
        ws.cell(row=row, column=5, value=salary)

        row += 1

    # Total row
    row += 1
    ws.cell(row=row, column=4, value="ИТОГО:")
    ws.cell(row=row, column=4).font = Font(bold=True)
    ws.cell(row=row, column=5, value=total_salary)
    ws.cell(row=row, column=5).font = Font(bold=True)
    ws.cell(row=row, column=5).fill = MONEY_NEGATIVE_FILL  # Salary is an expense

    _auto_width(ws)


def _create_balance_adjustments_sheet(
    wb: Workbook,
    balance_adjustments: list[CasinoBalanceAdjustment],
    report_date: dt.date,
):
    """Create sheet with balance adjustments for the working day."""
    ws = wb.create_sheet(title="Корректировки баланса")

    # Headers
    headers = ["Время", "Тип", "Сумма", "Комментарий", "Создал"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    _style_header(ws, 1, len(headers))

    if not balance_adjustments:
        ws.cell(row=2, column=1, value="Нет корректировок за выбранную дату")
        ws.cell(row=2, column=1).font = Font(italic=True)
        _auto_width(ws)
        return

    row = 2
    total_profit = 0
    total_expense = 0

    for adj in balance_adjustments:
        time_str = cast(dt.datetime, adj.created_at).strftime("%H:%M:%S")
        amount = int(cast(int, adj.amount))
        
        # Determine type (income/expense)
        adj_type = "Доход" if amount > 0 else "Расход"
        
        ws.cell(row=row, column=1, value=time_str)
        ws.cell(row=row, column=2, value=adj_type)
        
        amount_cell = ws.cell(row=row, column=3, value=amount)
        if amount > 0:
            amount_cell.fill = MONEY_POSITIVE_FILL
            total_profit += amount
        else:
            amount_cell.fill = MONEY_NEGATIVE_FILL
            total_expense += abs(amount)
        
        ws.cell(row=row, column=4, value=cast(str, adj.comment))
        
        username = cast(str, adj.created_by.username) if adj.created_by else "—"
        ws.cell(row=row, column=5, value=username)
        
        row += 1

    # Totals row
    row += 1
    ws.cell(row=row, column=4, value="ИТОГО доходы:")
    ws.cell(row=row, column=4).font = Font(bold=True)
    ws.cell(row=row, column=5, value=total_profit)
    ws.cell(row=row, column=5).font = Font(bold=True)
    ws.cell(row=row, column=5).fill = MONEY_POSITIVE_FILL
    row += 1
    
    ws.cell(row=row, column=4, value="ИТОГО расходы:")
    ws.cell(row=row, column=4).font = Font(bold=True)
    ws.cell(row=row, column=5, value=total_expense)
    ws.cell(row=row, column=5).font = Font(bold=True)
    ws.cell(row=row, column=5).fill = MONEY_NEGATIVE_FILL

    _auto_width(ws)


def _create_summary_sheet(
    wb: Workbook,
    sessions: list[Session],
    seats_by_session: dict[str, list[Seat]],
    purchases: list[ChipPurchase],
    staff: list[User],
    balance_adjustments: list[CasinoBalanceAdjustment],
    report_date: dt.date,
    is_table_admin: bool = False,
):
    """Create summary sheet with profit/expense overview."""
    ws = wb.create_sheet(title="Итоги дня")

    # Calculate totals
    total_chip_income_cash = 0  # Cash buyins (positive only)
    total_chip_cashout = 0  # Cash cashouts (absolute value, negative amounts)
    total_chip_income_credit = 0  # Credit buyins (credit part of income)
    
    for p in purchases:
        amount = int(cast(int, p.amount))
        if amount > 0:  # Buyin
            if p.payment_type == "credit":
                total_chip_income_credit += amount
            else:
                total_chip_income_cash += amount
        elif amount < 0:  # Cashout (negative amount = expense)
            # Cashouts are always cash payments back to players
            total_chip_cashout += abs(amount)  # Track cashouts separately

    # Calculate balance adjustments (only if not table_admin)
    total_balance_adjustments_profit = 0
    total_balance_adjustments_expense = 0
    if not is_table_admin:
        for adj in balance_adjustments:
            amount = int(cast(int, adj.amount))
            if amount > 0:
                total_balance_adjustments_profit += amount
            else:
                total_balance_adjustments_expense += abs(amount)

    # Calculate staff salary (only if not table_admin)
    total_salary = 0
    if not is_table_admin:
        for person in staff:
            role = cast(str, person.role)
            hourly_rate = int(cast(int, person.hourly_rate)) if person.hourly_rate else 0

            if role == "dealer":
                hours = _calculate_dealer_hours(sessions, int(cast(int, person.id)))
            else:
                hours = _calculate_waiter_hours(sessions, int(cast(int, person.id)))

            total_salary += round(hours * hourly_rate)

    # Calculate net per-seat totals (what players ended with)
    total_player_balance = 0
    for sid, seats in seats_by_session.items():
        for seat in seats:
            total_player_balance += int(cast(int, seat.total))

    # Gross rake ("грязный") = (cash buyins + credit buyins) - cashouts - players' ending balance
    gross_rake = (total_chip_income_cash + total_chip_income_credit) - total_chip_cashout - total_player_balance

    # Net result = gross rake - salaries + balance adjustments (profit/expense)
    net_result = gross_rake - total_salary + total_balance_adjustments_profit - total_balance_adjustments_expense

    # Write summary
    row = 1

    ws.cell(row=row, column=1, value=f"Отчёт за {report_date.isoformat()}")
    ws.cell(row=row, column=1).font = Font(bold=True, size=14)
    row += 2

    # Income section
    ws.cell(row=row, column=1, value="ДОХОДЫ")
    ws.cell(row=row, column=1).font = Font(bold=True)
    ws.cell(row=row, column=1).fill = MONEY_POSITIVE_FILL
    row += 1

    ws.cell(row=row, column=1, value="Рейк (грязный):")
    ws.cell(row=row, column=2, value=gross_rake)
    ws.cell(row=row, column=2).fill = MONEY_POSITIVE_FILL
    credit_cell = ws.cell(row=row, column=3, value=f"(кредит {total_chip_income_credit})")
    credit_cell.font = Font(color="FF0000", bold=True)
    row += 1

    ws.cell(row=row, column=1, value="Покупка фишек (наличные):")
    ws.cell(row=row, column=2, value=total_chip_income_cash)
    ws.cell(row=row, column=2).fill = MONEY_POSITIVE_FILL
    row += 1

    # Only show balance adjustments income for superadmin
    if not is_table_admin:
        ws.cell(row=row, column=1, value="Корректировки баланса (доход):")
        ws.cell(row=row, column=2, value=total_balance_adjustments_profit)
        ws.cell(row=row, column=2).fill = MONEY_POSITIVE_FILL
        row += 1
    row += 1

    # Expense section
    ws.cell(row=row, column=1, value="РАСХОДЫ")
    ws.cell(row=row, column=1).font = Font(bold=True)
    ws.cell(row=row, column=1).fill = MONEY_NEGATIVE_FILL
    row += 1

    # Only show salaries for superadmin
    if not is_table_admin:
        ws.cell(row=row, column=1, value="Зарплаты персонала:")
        ws.cell(row=row, column=2, value=total_salary)
        ws.cell(row=row, column=2).fill = MONEY_NEGATIVE_FILL
        row += 1

    # Only show balance adjustments expense for superadmin
    if not is_table_admin:
        ws.cell(row=row, column=1, value="Корректировки баланса (расход):")
        ws.cell(row=row, column=2, value=total_balance_adjustments_expense)
        ws.cell(row=row, column=2).fill = MONEY_NEGATIVE_FILL
        row += 1
    row += 1

    ws.cell(row=row, column=1, value="ИТОГО ЗА ДЕНЬ:")
    ws.cell(row=row, column=1).font = Font(bold=True, size=12)
    cell = ws.cell(row=row, column=2, value=net_result)
    cell.font = Font(bold=True, size=12)
    if net_result >= 0:
        cell.fill = MONEY_POSITIVE_FILL
    else:
        cell.fill = MONEY_NEGATIVE_FILL
    row += 2

    # Additional info
    ws.cell(row=row, column=1, value="Справочно:")
    ws.cell(row=row, column=1).font = Font(bold=True)
    row += 1

    ws.cell(row=row, column=1, value="Баланс игроков (остаток фишек):")
    ws.cell(row=row, column=2, value=total_player_balance)
    row += 1

    ws.cell(row=row, column=1, value="Выдано в кредит:")
    ws.cell(row=row, column=2, value=total_chip_income_credit)
    ws.cell(row=row, column=2).fill = CREDIT_DARK_FILL
    ws.cell(row=row, column=2).font = Font(color="FFFFFF", bold=True)
    row += 1
    
    # Add cashout line
    ws.cell(row=row, column=1, value="Выдано игрокам (кэшаут):")
    ws.cell(row=row, column=2, value=total_chip_cashout)
    ws.cell(row=row, column=2).fill = MONEY_NEGATIVE_FILL
    ws.cell(row=row, column=2).font = Font(bold=True)
    row += 1

    ws.cell(row=row, column=1, value="Количество сессий:")
    ws.cell(row=row, column=2, value=len(sessions))
    row += 1

    open_sessions = len([s for s in sessions if s.status == "open"])
    ws.cell(row=row, column=1, value="Открытых сессий:")
    ws.cell(row=row, column=2, value=open_sessions)

    _auto_width(ws)