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
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session as DBSession, joinedload
from sqlalchemy import func

from ..core.deps import get_current_user, get_db, get_owner_id_for_filter, require_roles
from ..models.db import CasinoBalanceAdjustment, ChipPurchase, DealerRakeEntry, Seat, SeatNameChange, Session, SessionDealerAssignment, Table, User, ChipOp

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _get_working_day_boundaries(date: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """
    Get working day boundaries for a given calendar date.
    Working day: 18:00 (6 PM) to 18:00 (6 PM) of next day.

    This is a full 24-hour window that covers:
    - 18:00-20:00: Pre-session prep time
    - 20:00-18:00 next day: Active playing time

    Args:
        date: Calendar date (YYYY-MM-DD)

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC
    """
    start = dt.datetime.combine(date, dt.time(18, 0, 0))
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

    Working day: 18:00 (6 PM) to 18:00 (6 PM) of next day.

    For table_admin: only considers sessions for tables they own.
    For superadmin: considers all sessions.
    """
    # Multi-tenancy: get owner_id for filtering
    owner_id = get_owner_id_for_filter(current_user)

    now = dt.datetime.utcnow()

    # Determine current working day
    # Working day starts at 18:00 and ends at 18:00 next day
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
    # Multi-tenancy: filter sessions by tables owned by this user
    if owner_id is not None:
        # table_admin: filter by sessions on tables they own
        owned_table_ids = db.query(Table.id).filter(Table.owner_id == owner_id).subquery()
        query = (
            db.query(Session)
            .filter(Session.created_at >= start_time, Session.created_at < end_time)
            .filter(Session.table_id.in_(owned_table_ids))
        )
    else:
        # superadmin: all sessions
        query = (
            db.query(Session)
            .filter(Session.created_at >= start_time, Session.created_at < end_time)
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

        # Multi-tenancy: filter sessions by tables owned by this user
        if owner_id is not None:
            prev_sessions = (
                db.query(Session)
                .filter(Session.created_at >= prev_start, Session.created_at < prev_end)
                .filter(Session.table_id.in_(owned_table_ids))
                .first()
            )
        else:
            prev_sessions = (
                db.query(Session)
                .filter(Session.created_at >= prev_start, Session.created_at < prev_end)
                .first()
            )

        if prev_sessions:
            return {"date": prev_day.isoformat()}

    # No sessions found in the last 7 days, return current working day
    return {"date": working_day_start.isoformat()}


@router.get("/day-summary")
def get_day_summary(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    table_id: int | None = Query(default=None, description="Optional table_id to filter by specific table"),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(require_roles("superadmin", "table_admin")),
):
    """Get day summary data (profit/loss) as JSON for mobile display.

    Multi-tenancy aware:
    - table_admin: shows data for tables they own, staff they own, balance adjustments they own
    - superadmin: shows all data (or filtered by table_id if provided)
    """
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # DIAGNOSTIC LOGGING: Initialize logger
    import logging
    logger = logging.getLogger(__name__)

    # Multi-tenancy: get owner_id for filtering
    owner_id = get_owner_id_for_filter(current_user)
    is_table_admin = owner_id is not None

    # DIAGNOSTIC LOGGING: User role and multi-tenancy
    logger.info(f"=== DAY SUMMARY DIAGNOSTICS FOR {date} ===")
    logger.info(f"--- USER ROLE DIAGNOSTICS ---")
    logger.info(f"current_user.role: {current_user.role}")
    logger.info(f"owner_id: {owner_id}")
    logger.info(f"is_table_admin: {is_table_admin}")

    # Get working day boundaries (18:00 to 18:00 next day)
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
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.rake_entries),
        )
        .filter(Session.created_at >= start_time, Session.created_at < end_time)
    )

    # Multi-tenancy: filter by tables owned by user
    if owner_id is not None:
        owned_table_ids = db.query(Table.id).filter(Table.owner_id == owner_id).subquery()
        sessions_query = sessions_query.filter(Session.table_id.in_(owned_table_ids))

    # Additional filter by specific table_id if provided
    if table_id is not None:
        # Verify table ownership for table_admin
        if owner_id is not None:
            table = db.query(Table).filter(Table.id == table_id, Table.owner_id == owner_id).first()
            if not table:
                raise HTTPException(status_code=403, detail="Forbidden for this table")
        sessions_query = sessions_query.filter(Session.table_id == table_id)

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

    # Fetch balance adjustments for the working day (multi-tenancy filtered)
    balance_query = (
        db.query(CasinoBalanceAdjustment)
        .options(joinedload(CasinoBalanceAdjustment.created_by))
        .filter(CasinoBalanceAdjustment.created_at >= start_time, CasinoBalanceAdjustment.created_at < end_time)
    )
    if owner_id is not None:
        balance_query = balance_query.filter(CasinoBalanceAdjustment.owner_id == owner_id)
    balance_adjustments = balance_query.order_by(CasinoBalanceAdjustment.created_at.asc()).all()

    # DIAGNOSTIC LOGGING: Balance adjustments
    logger.info(f"--- BALANCE ADJUSTMENTS DIAGNOSTICS ---")
    logger.info(f"balance_adjustments length: {len(balance_adjustments)}")
    logger.info(f"is_table_admin: {is_table_admin}")

    # Fetch staff (multi-tenancy filtered)
    # For table_admin: only staff they own
    # For superadmin: all staff
    staff_query = db.query(User).filter(User.role.in_(["dealer", "waiter"]))
    if owner_id is not None:
        staff_query = staff_query.filter(User.owner_id == owner_id)
    staff = staff_query.all()

    # DIAGNOSTIC LOGGING: Staff
    logger.info(f"--- STAFF DIAGNOSTICS ---")
    logger.info(f"staff length: {len(staff)}")
    logger.info(f"is_table_admin: {is_table_admin}")

    # Calculate totals
    total_chip_income_cash = 0  # Cash buyins (positive only)
    total_chip_cashout = 0  # Cash cashouts (absolute value, negative amounts)
    total_chip_income_credit = 0  # Credit buyins (informational only, NOT in rake calculation)
    total_balance_adjustments_profit = 0  # Positive adjustments
    total_balance_adjustments_expense = 0  # Negative adjustments (absolute value)

    for p in purchases:
        amount = int(cast(int, p.amount))
        if amount > 0:  # Buyin
            if p.payment_type == "credit":
                total_chip_income_credit += amount  # Track for info only
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

    # Gross rake ("грязный") = sum of manually entered rake entries from all dealer assignments
    # Rake entries are added by table admin during the session via the "Update Rake" feature
    gross_rake = 0
    for s in sessions:
        for assignment in s.dealer_assignments:
            for entry in (assignment.rake_entries or []):
                gross_rake += int(cast(int, entry.amount))

    # Net result for the day = gross_rake - salaries + balance_adjustments_profit - balance_adjustments_expense
    net_result = gross_rake - total_salary + total_balance_adjustments_profit - total_balance_adjustments_expense

    # DIAGNOSTIC LOGGING
    logger.info(f"--- CALCULATION COMPONENTS ---")
    logger.info(f"total_chip_income_cash (cash buyins): {total_chip_income_cash}")
    logger.info(f"total_chip_cashout (cashouts to players): {total_chip_cashout}")
    logger.info(f"total_player_balance (chips players have): {total_player_balance}")
    logger.info(f"total_salary: {total_salary}")
    logger.info(f"total_chip_income_credit (credit buyins - info only): {total_chip_income_credit}")
    logger.info(f"total_balance_adjustments_profit: {total_balance_adjustments_profit}")
    logger.info(f"total_balance_adjustments_expense: {total_balance_adjustments_expense}")
    logger.info(f"--- FORMULAS ---")
    logger.info(f"gross_rake = sum of dealer assignment rakes = {gross_rake}")
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
        session_rake = sum(int(cast(int, a.rake)) for a in s.dealer_assignments if a.rake is not None)
        logger.info(f"  Session {sid} (Table {s.table_id}, {s.status}): player_balance = {session_balance}, rake = {session_rake}")
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
            "balance_adjustments": total_balance_adjustments_profit,
        },
        "expenses": {
            "salaries": total_salary,
            "balance_adjustments": total_balance_adjustments_expense,
        },
        "result": net_result,
        "info": {
            "buyin_cash": total_chip_income_cash,
            "buyin_credit": total_chip_income_credit,  # Informational only
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


def _get_waiter_time_range(
    sessions: list[Session],
    waiter_id: int,
) -> tuple[dt.datetime | None, dt.datetime | None]:
    """
    Get the overall time range for a waiter's work period.
    Returns (earliest_start, latest_end) or (None, None) if no sessions.
    """
    intervals: list[tuple[dt.datetime, dt.datetime]] = []

    for s in sessions:
        if s.waiter_id != waiter_id:
            continue
        start = cast(dt.datetime, s.created_at)
        end = cast(dt.datetime, s.closed_at) if s.closed_at else dt.datetime.utcnow()
        intervals.append((start, end))

    if not intervals:
        return None, None

    earliest_start = min(start for start, _ in intervals)
    latest_end = max(end for _, end in intervals)
    return earliest_start, latest_end


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

            # Sum rake entries for this assignment
            rake = sum(int(cast(int, entry.amount)) for entry in (assignment.rake_entries or []))

            earnings.append({
                "dealer_name": cast(str, dealer.username),
                "hours": hours,
                "hourly_rate": hourly_rate,
                "salary": salary,
                "rake": rake,
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
                "rake": 0,  # Legacy sessions don't have per-dealer rake
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
    table_id: int | None = Query(default=None, description="Optional table_id to filter by specific table"),
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate comprehensive XLSX report for a specific date.

    Multi-tenancy aware:
    - table_admin: includes data for tables/staff/balance adjustments they own
    - superadmin: includes all data (or filtered by table_id if provided)
    """
    # Check user role
    role = cast(str, user.role)
    if role not in ("superadmin", "table_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Multi-tenancy: get owner_id for filtering
    owner_id = get_owner_id_for_filter(user)
    is_table_admin = owner_id is not None

    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (expected YYYY-MM-DD)")

    # Get working day boundaries (18:00 to 18:00 next day)
    start_time, end_time = _get_working_day_boundaries(d)

    # Fetch tables (multi-tenancy filtered)
    tables_query = db.query(Table)
    if owner_id is not None:
        tables_query = tables_query.filter(Table.owner_id == owner_id)
    tables = tables_query.order_by(Table.id.asc()).all()

    # Fetch sessions for the working day
    sessions_query = (
        db.query(Session)
        .options(
            joinedload(Session.dealer),
            joinedload(Session.waiter),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.dealer),
            joinedload(Session.dealer_assignments).joinedload(SessionDealerAssignment.rake_entries),
        )
        .filter(Session.created_at >= start_time, Session.created_at < end_time)
    )

    # Multi-tenancy: filter by tables owned by user
    if owner_id is not None:
        owned_table_ids = db.query(Table.id).filter(Table.owner_id == owner_id).subquery()
        sessions_query = sessions_query.filter(Session.table_id.in_(owned_table_ids))

    # Additional filter by specific table_id if provided
    if table_id is not None:
        # Verify table ownership for table_admin
        if owner_id is not None:
            table = db.query(Table).filter(Table.id == table_id, Table.owner_id == owner_id).first()
            if not table:
                raise HTTPException(status_code=403, detail="Forbidden for this table")
        sessions_query = sessions_query.filter(Session.table_id == table_id)

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

    # Fetch balance adjustments for the working day (multi-tenancy filtered)
    balance_query = (
        db.query(CasinoBalanceAdjustment)
        .options(joinedload(CasinoBalanceAdjustment.created_by))
        .filter(CasinoBalanceAdjustment.created_at >= start_time, CasinoBalanceAdjustment.created_at < end_time)
    )
    if owner_id is not None:
        balance_query = balance_query.filter(CasinoBalanceAdjustment.owner_id == owner_id)
    balance_adjustments = balance_query.order_by(CasinoBalanceAdjustment.created_at.asc()).all()

    # Fetch staff (multi-tenancy filtered)
    staff_query = db.query(User).filter(User.role.in_(["dealer", "waiter"]))
    if owner_id is not None:
        staff_query = staff_query.filter(User.owner_id == owner_id)
    staff = staff_query.all()

    # Load template.xlsx and fill it with data
    import os
    template_path = os.path.join(os.path.dirname(__file__), "..", "..", "template.xlsx")
    if not os.path.exists(template_path):
        # Fallback for Docker container
        template_path = "/app/template.xlsx"

    wb = load_workbook(template_path)
    ws = wb.active

    # Fill template with data
    _fill_template_with_data(ws, sessions, seats_by_session, purchases, balance_adjustments, staff, d, db)

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


def _fill_template_with_data(
    ws,
    sessions: list[Session],
    seats_by_session: dict[str, list[Seat]],
    purchases: list[ChipPurchase],
    balance_adjustments: list[CasinoBalanceAdjustment],
    staff: list[User],
    report_date: dt.date,
    db: DBSession,
):
    """
    Fill the template.xlsx with actual data.

    Template structure (dynamic rows for seats):
    - Row 1: Seat number headers (we fill № 1 through № 10 in columns C,E,G,I,K,M,O,Q,S,U)
    - Rows 2-N: Player names + chip purchases (dynamically sized based on data)
    - Rows N+1 to N+6: Summary rows (Жетоны(-), Жетоны(+), Результат, etc.)

    After seat section, staff section follows with adjusted row numbers.
    """
    if not sessions:
        return  # Leave template as-is if no data

    from openpyxl.styles import PatternFill
    import re

    no_fill = PatternFill(fill_type=None)
    MAX_SEATS = 10
    TEMPLATE_DATA_ROWS = 14  # Template has rows 2-15 for data (14 rows)
    TEMPLATE_SUMMARY_START_ROW = 16  # Original summary rows in template

    # --- Step 1: Collect all data for each seat ---
    # For each seat, we need to interleave player names (including changes) and chip purchases

    # Get all session IDs for the report
    session_ids = [cast(str, s.id) for s in sessions]

    # Query all SeatNameChange records for these sessions
    name_changes = db.query(SeatNameChange).filter(
        SeatNameChange.session_id.in_(session_ids)
    ).all()

    # Group name changes by seat
    name_changes_by_seat: dict[int, list[SeatNameChange]] = {}
    for nc in name_changes:
        seat_no = int(cast(int, nc.seat_no))
        if seat_no not in name_changes_by_seat:
            name_changes_by_seat[seat_no] = []
        name_changes_by_seat[seat_no].append(nc)

    # Sort name changes by time
    for seat_no in name_changes_by_seat:
        name_changes_by_seat[seat_no].sort(key=lambda nc: cast(dt.datetime, nc.created_at))

    # Collect all chip purchases grouped by seat
    purchases_by_seat: dict[int, list[ChipPurchase]] = {}
    for p in purchases:
        seat_no = int(cast(int, p.seat_no))
        if seat_no not in purchases_by_seat:
            purchases_by_seat[seat_no] = []
        purchases_by_seat[seat_no].append(p)

    # Sort purchases by time
    for seat_no in purchases_by_seat:
        purchases_by_seat[seat_no].sort(key=lambda p: cast(dt.datetime, p.created_at))

    # Get initial player names by seat (from Seat records)
    initial_player_by_seat: dict[int, tuple[str, dt.datetime]] = {}
    for session in sessions:
        session_id = cast(str, session.id)
        session_created = cast(dt.datetime, session.created_at)
        seats = seats_by_session.get(session_id, [])
        for seat in seats:
            seat_no = int(cast(int, seat.seat_no))
            # We need to find the initial player name (first name before any changes)
            # If there are name changes, the first change's old_name is the initial
            seat_name_changes = name_changes_by_seat.get(seat_no, [])
            if seat_name_changes:
                initial_name = seat_name_changes[0].old_name
            else:
                # No changes, use current name
                initial_name = seat.player_name
            if initial_name and seat_no not in initial_player_by_seat:
                initial_player_by_seat[seat_no] = (cast(str, initial_name), session_created)

    # Build timeline of events for each seat: list of (timestamp, type, data)
    # type: "player" for player name, "purchase" for chip purchase
    seat_events: dict[int, list[tuple[dt.datetime, str, Any]]] = {}
    for seat_no in range(1, MAX_SEATS + 1):
        events: list[tuple[dt.datetime, str, Any]] = []

        # Add initial player name if exists
        if seat_no in initial_player_by_seat:
            name, ts = initial_player_by_seat[seat_no]
            events.append((ts, "player", name))

        # Add name changes (new player names)
        for nc in name_changes_by_seat.get(seat_no, []):
            ts = cast(dt.datetime, nc.created_at)
            change_type = nc.change_type or "name_change"
            if change_type == "player_left":
                # Player left - we could show this as "(left)" or skip
                events.append((ts, "player_left", nc.old_name))
            elif nc.new_name:
                # New player took the seat
                events.append((ts, "player", nc.new_name))

        # Add chip purchases
        for p in purchases_by_seat.get(seat_no, []):
            ts = cast(dt.datetime, p.created_at)
            events.append((ts, "purchase", p))

        # Sort all events by timestamp
        events.sort(key=lambda e: e[0])
        seat_events[seat_no] = events

    # --- Step 2: Calculate max data rows needed ---
    max_data_rows = 0
    for seat_no in range(1, MAX_SEATS + 1):
        events = seat_events.get(seat_no, [])
        max_data_rows = max(max_data_rows, len(events))

    # Ensure at least TEMPLATE_DATA_ROWS (for when there's little data)
    max_data_rows = max(max_data_rows, TEMPLATE_DATA_ROWS)

    # --- Step 3: Insert rows if needed ---
    rows_to_insert = max_data_rows - TEMPLATE_DATA_ROWS
    if rows_to_insert > 0:
        # Insert rows before the summary section (before row 16)
        ws.insert_rows(TEMPLATE_SUMMARY_START_ROW, rows_to_insert)

    # Calculate new summary row positions
    summary_start_row = TEMPLATE_SUMMARY_START_ROW + rows_to_insert  # 16 + inserted rows
    data_end_row = summary_start_row - 1  # Last data row

    # --- Step 4: Fill seat headers and data ---
    for seat_no in range(1, MAX_SEATS + 1):
        col_value = 2 + (seat_no - 1) * 2  # B=2, D=4, F=6, H=8, J=10, L=12, N=14, P=16, R=18, T=20
        col_time = col_value + 1            # C=3, E=5, G=7, I=9, K=11, M=13, O=15, Q=17, S=19, U=21

        # Update seat header in row 1
        ws.cell(row=1, column=col_time, value=f"№ {seat_no}")

        # Fill events for this seat
        events = seat_events.get(seat_no, [])
        for i, (ts, event_type, data) in enumerate(events):
            row = 2 + i  # Data starts at row 2

            if event_type == "player":
                # Player name
                ws.cell(row=row, column=col_value, value=data)
                ws.cell(row=row, column=col_time, value=ts.strftime("%H:%M"))
            elif event_type == "player_left":
                # Player left marker
                ws.cell(row=row, column=col_value, value=f"({data} left)")
                ws.cell(row=row, column=col_time, value=ts.strftime("%H:%M"))
            elif event_type == "purchase":
                # Chip purchase
                # In DB: positive = player bought chips (player pays), negative = player cashout (casino pays)
                # In XLS: show as-is (positive for player buying, negative for player cashing out)
                p = data
                amount = int(cast(int, p.amount))
                ws.cell(row=row, column=col_value, value=amount)
                ws.cell(row=row, column=col_time, value=ts.strftime("%H:%M"))

    # --- Step 5: Clear unused seat columns (seats 11-12 in template) ---
    for seat_no in range(11, 13):
        col_value = 2 + (seat_no - 1) * 2  # V=22, X=24
        col_time = col_value + 1            # W=23, Y=25
        # Clear all rows in seat section (1 to summary_start_row + 5)
        for row in range(1, summary_start_row + 6):
            ws.cell(row=row, column=col_value).value = None
            ws.cell(row=row, column=col_value).fill = no_fill
            ws.cell(row=row, column=col_time).value = None
            ws.cell(row=row, column=col_time).fill = no_fill

    # --- Step 6: Copy labels to new summary rows ---
    # Original template has labels in A39-A44, we need them at new summary position
    # After inserting rows, original row 39 shifted to (39 + rows_to_insert)
    src_label_rows = [39 + rows_to_insert, 40 + rows_to_insert, 41 + rows_to_insert,
                      42 + rows_to_insert, 43 + rows_to_insert, 44 + rows_to_insert]
    dst_label_rows = [summary_start_row, summary_start_row + 1, summary_start_row + 2,
                      summary_start_row + 3, summary_start_row + 4, summary_start_row + 5]

    for src_row, dst_row in zip(src_label_rows, dst_label_rows):
        src_cell = ws.cell(row=src_row, column=1)
        dst_cell = ws.cell(row=dst_row, column=1)
        if src_cell.value:
            dst_cell.value = src_cell.value
            if src_cell.fill and src_cell.fill.patternType:
                dst_cell.fill = src_cell.fill.copy()

    # --- Step 7: Create summary formulas at new positions ---
    # Summary formulas sum each row from B to T (columns 2-20) for seats 1-10 value columns
    # We only use even columns: B, D, F, H, J, L, N, P, R, T (seats 1-10)
    # Place the sum in column V (22) instead of Z (26)
    for i, summary_row in enumerate(range(summary_start_row, summary_start_row + 6)):
        ws.cell(row=summary_row, column=22, value=f"=SUM(B{summary_row}:T{summary_row})")

    # --- Step 7b: Add medium outer border around entire seats area ---
    # Seats area: rows 1 to summary_start_row + 5, columns B to V (2 to 22)
    seats_area_end_row = summary_start_row + 5
    thick_side = Side(style='medium')
    for r in range(1, seats_area_end_row + 1):
        for c in range(2, 23):  # B to V (columns 2-22)
            cell = ws.cell(row=r, column=c)
            current_border = cell.border
            left = thick_side if c == 2 else current_border.left
            right = thick_side if c == 22 else current_border.right
            top = thick_side if r == 1 else current_border.top
            bottom = thick_side if r == seats_area_end_row else current_border.bottom
            cell.border = Border(left=left, right=right, top=top, bottom=bottom)

    # --- Step 8: Update formulas throughout the sheet ---
    # The rows after summary section need to reference the new summary rows
    # Original V39-V44 should now reference V{summary_start_row} to V{summary_start_row+5}
    old_summary_rows = [39 + rows_to_insert, 40 + rows_to_insert, 41 + rows_to_insert,
                        42 + rows_to_insert, 43 + rows_to_insert, 44 + rows_to_insert]
    new_summary_rows = [summary_start_row, summary_start_row + 1, summary_start_row + 2,
                        summary_start_row + 3, summary_start_row + 4, summary_start_row + 5]

    # Scan all cells and update formula references
    # The dealer section starts at original row 47, now shifted by rows_to_insert
    dealer_section_start = 45 + rows_to_insert
    for row in range(dealer_section_start, dealer_section_start + 50):
        for col in range(1, 30):
            cell = ws.cell(row=row, column=col)
            val = cell.value
            if isinstance(val, str) and val.startswith('='):
                new_val = val
                # Replace references to old summary rows with new ones (changed from Z to V)
                for old_row, new_row in zip(old_summary_rows, new_summary_rows):
                    new_val = re.sub(rf'\bV{old_row}\b', f'V{new_row}', new_val)
                    # Also replace any Z references to V
                    new_val = re.sub(rf'\bZ{old_row}\b', f'V{new_row}', new_val)
                # Replace references to row 24 (player names from old template) with row 1
                for c in 'BDFHJLNPRTXVX':
                    new_val = re.sub(rf'\b{c}24\b', f'{c}1', new_val)
                if new_val != val:
                    cell.value = new_val

    # --- Step 9: Delete unused rows from original template ---
    # Original template had rows 24-44 for second seat section (21 rows)
    # After inserting rows, these are at (24 + rows_to_insert) to (44 + rows_to_insert)
    rows_24_44_start = 24 + rows_to_insert
    ws.delete_rows(rows_24_44_start, 21)

    # === SECTION: Dealer rake entries ===
    # After row operations: original row 47 -> summary_start_row + 6 + gap (usually row 23)
    # Then after deleting 21 rows, it shifts up by 21
    # Net effect: original 47 -> (47 + rows_to_insert - 21) = 47 - 21 + rows_to_insert = 26 + rows_to_insert
    # But we need to account for the actual position after all operations

    # Calculate dealer section position:
    # - Original template: dealer section at row 47
    # - After inserting rows_to_insert: row 47 + rows_to_insert
    # - After deleting 21 rows (rows 24-44): row 47 + rows_to_insert - 21 = 26 + rows_to_insert
    DEALER_SECTION_START_ROW = 26 + rows_to_insert
    DEALER_HEADER_ROW = 27 + rows_to_insert
    DEALER_DATA_START_ROW = 28 + rows_to_insert
    DEALER_DATA_END_ROW = 65 + rows_to_insert

    # Collect all dealers from sessions
    dealers_with_rake: dict[int, list[DealerRakeEntry]] = {}
    dealer_names: dict[int, str] = {}

    for session in sessions:
        for assignment in session.dealer_assignments:
            dealer_id = int(cast(int, assignment.dealer_id))
            if assignment.dealer:
                dealer_names[dealer_id] = cast(str, assignment.dealer.username)
            if dealer_id not in dealers_with_rake:
                dealers_with_rake[dealer_id] = []
            for entry in (assignment.rake_entries or []):
                dealers_with_rake[dealer_id].append(entry)

    # Sort dealers by ID
    sorted_dealer_ids = sorted(dealers_with_rake.keys())
    num_dealers = len(sorted_dealer_ids)

    # Clear ALL dealer columns first (to remove any template dummy data)
    # Template has up to 3 dealers in columns A-B, C-D, E-F
    # Also clear the bottom summary area (rows 66-70 + rows_to_insert)
    no_border = Border()
    TEMPLATE_DEALER_CLEAR_END = 70 + rows_to_insert  # Clear well past the template summary rows
    for idx in range(0, 3):
        col_rake = 1 + idx * 2
        col_time = col_rake + 1
        # Clear dealer name row, header row, all data rows, and summary rows
        for row in range(DEALER_SECTION_START_ROW, TEMPLATE_DEALER_CLEAR_END + 1):
            for col in [col_rake, col_time]:
                cell = ws.cell(row=row, column=col)
                cell.value = None
                cell.fill = no_fill
                cell.border = no_border

    # Clear G column (column 7) completely - always empty, no borders
    for row in range(DEALER_SECTION_START_ROW, TEMPLATE_DEALER_CLEAR_END + 1):
        cell = ws.cell(row=row, column=7)
        cell.value = None
        cell.fill = no_fill
        cell.border = no_border

    # Define dealer block background colors
    dealer_name_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")  # Blue for name
    dealer_header_fill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")  # Light blue for headers
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # Track the maximum data row used across all dealers
    max_dealer_data_row = DEALER_DATA_START_ROW - 1  # Start before first data row

    # Fill dealer names, headers, and rake entries (only for actual dealers)
    for idx, dealer_id in enumerate(sorted_dealer_ids):
        col_rake = 1 + idx * 2   # A=1, C=3, E=5, ...
        col_time = col_rake + 1  # B=2, D=4, F=6, ...

        # Dealer name with background color
        dealer_name = dealer_names.get(dealer_id, f"D{idx+1}")
        name_cell = ws.cell(row=DEALER_SECTION_START_ROW, column=col_rake, value=dealer_name)
        name_cell.fill = dealer_name_fill
        name_cell.font = Font(bold=True, color="FFFFFF")
        name_cell.border = thin_border
        # Extend background to second column of dealer block
        name_cell2 = ws.cell(row=DEALER_SECTION_START_ROW, column=col_time)
        name_cell2.fill = dealer_name_fill
        name_cell2.border = thin_border

        # Headers with background color
        header_rake = ws.cell(row=DEALER_HEADER_ROW, column=col_rake, value="Рейк")
        header_rake.fill = dealer_header_fill
        header_rake.border = thin_border
        header_time = ws.cell(row=DEALER_HEADER_ROW, column=col_time, value="Время")
        header_time.fill = dealer_header_fill
        header_time.border = thin_border

        # Rake entries
        rake_entries = sorted(dealers_with_rake[dealer_id], key=lambda e: cast(dt.datetime, e.created_at))
        for i, entry in enumerate(rake_entries):
            row = DEALER_DATA_START_ROW + i
            if row > DEALER_DATA_END_ROW:
                break
            rake_cell = ws.cell(row=row, column=col_rake, value=int(cast(int, entry.amount)))
            rake_cell.border = thin_border
            time_str = cast(dt.datetime, entry.created_at).strftime("%H:%M")
            time_cell = ws.cell(row=row, column=col_time, value=time_str)
            time_cell.border = thin_border
            # Track the maximum row used
            if row > max_dealer_data_row:
                max_dealer_data_row = row

    # === DEALER TOTALS SECTION ===
    # Position totals right after the last data row (not at a fixed position)
    # Add 1 empty row after data, then totals
    grand_total_rake = 0

    if num_dealers > 0:
        DEALER_TOTALS_ROW = max_dealer_data_row + 2  # 1 empty row, then totals

        # Add per-dealer totals (only for dealers that have data)
        for idx, dealer_id in enumerate(sorted_dealer_ids):
            col_rake = 1 + idx * 2   # A=1, C=3, E=5, ...
            col_letter = get_column_letter(col_rake)

            # Calculate total for this dealer
            rake_entries = dealers_with_rake[dealer_id]
            dealer_total = sum(int(cast(int, entry.amount)) for entry in rake_entries)
            grand_total_rake += dealer_total

            # Write SUM formula for this dealer
            total_cell = ws.cell(row=DEALER_TOTALS_ROW, column=col_rake,
                    value=f"=SUM({col_letter}{DEALER_DATA_START_ROW}:{col_letter}{max_dealer_data_row})")
            total_cell.font = Font(bold=True)
            total_cell.border = thin_border

    # === SECTION: Clear columns V and beyond for bottom part ===
    # Clear columns V and beyond (22+) for the bottom section - values, fills, and borders
    no_border = Border()
    BOTTOM_SECTION_START = 26 + rows_to_insert
    BOTTOM_SECTION_END = BOTTOM_SECTION_START + 50  # Clear enough rows for bottom section

    for row in range(BOTTOM_SECTION_START, BOTTOM_SECTION_END):
        for col in range(16, 50):  # P onwards (column 16+) - after data columns
            cell = ws.cell(row=row, column=col)
            cell.value = None
            cell.fill = no_fill
            cell.border = no_border

    # === Clear W-Z columns in seat area (columns 23-26, rows 1 to summary) ===
    for row in range(1, summary_start_row + 7):
        for col in range(23, 27):  # W, X, Y, Z
            cell = ws.cell(row=row, column=col)
            cell.value = None
            cell.fill = no_fill
            cell.border = no_border

    # === Clear area below seats but before bottom blocks ===
    # This is the gap between summary rows and dealer section
    # Don't clear BOTTOM_SECTION_START itself - that's where dealer names go
    gap_start = summary_start_row + 6
    gap_end = BOTTOM_SECTION_START - 1  # Stop before dealer name row
    for row in range(gap_start, gap_end + 1):
        for col in range(1, 50):  # Clear all columns in the gap area
            cell = ws.cell(row=row, column=col)
            cell.value = None
            cell.fill = no_fill
            cell.border = no_border

    # === SECTION: H-J columns - Расходы, Доходы, З/П тотал, Рейк ===
    # Data starts at column H (8) - shifted from N (14) to remove waiter columns
    # Use template font: Roboto Mono, size 11

    # After operations, template row 48 becomes 27 + rows_to_insert
    NP_SECTION_START = 27 + rows_to_insert
    template_font = Font(name="Roboto Mono", size=11)
    template_font_bold = Font(name="Roboto Mono", size=11, bold=True)

    # Clear ALL old template data in H-U columns (8-21) for bottom section
    # Start from row 26 (dealer name row) to clear any leftover waiter data in H+ columns
    no_border = Border()
    TEMPLATE_CLEAR_START = 26 + rows_to_insert
    TEMPLATE_CLEAR_END = 70 + rows_to_insert

    for clear_row in range(TEMPLATE_CLEAR_START, TEMPLATE_CLEAR_END + 1):
        for col in range(8, 22):  # H through U columns (8-21)
            cell = ws.cell(row=clear_row, column=col)
            cell.value = None
            cell.fill = no_fill
            cell.border = no_border
            cell.font = Font()
            cell.alignment = Alignment()

    # Prepare data
    negative_adjustments = [ba for ba in balance_adjustments if int(cast(int, ba.amount)) < 0]
    positive_adjustments = [ba for ba in balance_adjustments if int(cast(int, ba.amount)) > 0]

    # Calculate staff salaries
    staff_salaries: list[tuple[str, str, int]] = []  # (name, role, earnings)
    total_staff_salary = 0

    dealers = [s for s in staff if s.role == "dealer"]
    for dealer in dealers:
        dealer_id = int(cast(int, dealer.id))
        dealer_name = cast(str, dealer.username)
        hourly_rate = int(cast(int, dealer.hourly_rate)) if dealer.hourly_rate else 0
        hours = _calculate_dealer_hours(sessions, dealer_id)
        if hours > 0:
            earnings = round(hours * hourly_rate)
            total_staff_salary += earnings
            staff_salaries.append((dealer_name, "Дилер", earnings))

    waiters = [s for s in staff if s.role == "waiter"]
    for waiter in waiters:
        waiter_id = int(cast(int, waiter.id))
        waiter_name = cast(str, waiter.username)
        hourly_rate = int(cast(int, waiter.hourly_rate)) if waiter.hourly_rate else 0
        hours = _calculate_waiter_hours(sessions, waiter_id)
        if hours > 0:
            earnings = round(hours * hourly_rate)
            total_staff_salary += earnings
            staff_salaries.append((waiter_name, "Официант", earnings))

    # Write all data starting from NP_SECTION_START, column H (8)
    current_row = NP_SECTION_START
    stats_start_row = current_row  # Track start for outer border

    # Define light background colors for each section
    expenses_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")  # Light yellow
    income_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")  # Light green
    salary_fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")  # Light blue
    rake_fill = PatternFill(start_color="EDEDED", end_color="EDEDED", fill_type="solid")  # Light gray
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # === РАСХОДЫ (Expenses) ===
    expenses_start = current_row
    ws.cell(row=current_row, column=8, value="РАСХОДЫ")
    ws.cell(row=current_row, column=8).font = template_font_bold
    current_row += 1

    if negative_adjustments:
        for adj in negative_adjustments:
            amount = int(cast(int, adj.amount))
            comment = cast(str, adj.comment) if adj.comment else ""
            ws.cell(row=current_row, column=8, value=comment[:30])
            ws.cell(row=current_row, column=8).font = template_font
            ws.cell(row=current_row, column=9, value=amount)
            ws.cell(row=current_row, column=9).font = template_font
            current_row += 1
        expenses_total = sum(int(cast(int, ba.amount)) for ba in negative_adjustments)
        ws.cell(row=current_row, column=8, value="Итого:")
        ws.cell(row=current_row, column=8).font = template_font_bold
        ws.cell(row=current_row, column=9, value=expenses_total)
        ws.cell(row=current_row, column=9).font = template_font_bold
        current_row += 1
    else:
        ws.cell(row=current_row, column=8, value="(нет)")
        ws.cell(row=current_row, column=8).font = template_font
        current_row += 1
    expenses_end = current_row - 1

    # Apply expenses background
    for r in range(expenses_start, expenses_end + 1):
        for c in range(8, 11):  # H-J
            ws.cell(row=r, column=c).fill = expenses_fill
            ws.cell(row=r, column=c).border = thin_border

    current_row += 1  # Empty row

    # === ДОХОДЫ (Income) ===
    income_start = current_row
    ws.cell(row=current_row, column=8, value="ДОХОДЫ")
    ws.cell(row=current_row, column=8).font = template_font_bold
    current_row += 1

    if positive_adjustments:
        for adj in positive_adjustments:
            amount = int(cast(int, adj.amount))
            comment = cast(str, adj.comment) if adj.comment else ""
            ws.cell(row=current_row, column=8, value=comment[:30])
            ws.cell(row=current_row, column=8).font = template_font
            ws.cell(row=current_row, column=9, value=amount)
            ws.cell(row=current_row, column=9).font = template_font
            current_row += 1
        bonuses_total = sum(int(cast(int, ba.amount)) for ba in positive_adjustments)
        ws.cell(row=current_row, column=8, value="Итого:")
        ws.cell(row=current_row, column=8).font = template_font_bold
        ws.cell(row=current_row, column=9, value=bonuses_total)
        ws.cell(row=current_row, column=9).font = template_font_bold
        current_row += 1
    else:
        ws.cell(row=current_row, column=8, value="(нет)")
        ws.cell(row=current_row, column=8).font = template_font
        current_row += 1
    income_end = current_row - 1

    # Apply income background
    for r in range(income_start, income_end + 1):
        for c in range(8, 11):  # H-J
            ws.cell(row=r, column=c).fill = income_fill
            ws.cell(row=r, column=c).border = thin_border

    current_row += 1  # Empty row

    # === З/П ТОТАЛ (Staff Salaries) ===
    salary_start = current_row
    ws.cell(row=current_row, column=8, value="З/П ТОТАЛ")
    ws.cell(row=current_row, column=8).font = template_font_bold
    current_row += 1

    if staff_salaries:
        for name, role, earnings in staff_salaries:
            ws.cell(row=current_row, column=8, value=name)
            ws.cell(row=current_row, column=8).font = template_font
            ws.cell(row=current_row, column=9, value=role)
            ws.cell(row=current_row, column=9).font = template_font
            ws.cell(row=current_row, column=10, value=earnings)
            ws.cell(row=current_row, column=10).font = template_font
            current_row += 1
        ws.cell(row=current_row, column=8, value="Итого:")
        ws.cell(row=current_row, column=8).font = template_font_bold
        ws.cell(row=current_row, column=10, value=total_staff_salary)
        ws.cell(row=current_row, column=10).font = template_font_bold
        current_row += 1
    else:
        ws.cell(row=current_row, column=8, value="(нет)")
        ws.cell(row=current_row, column=8).font = template_font
        current_row += 1
    salary_end = current_row - 1

    # Apply salary background
    for r in range(salary_start, salary_end + 1):
        for c in range(8, 11):  # H-J
            ws.cell(row=r, column=c).fill = salary_fill
            ws.cell(row=r, column=c).border = thin_border

    current_row += 1  # Blank line

    # === РЕЙК БРУТТО / РЕЙК НЕТТО ===
    rake_start = current_row
    ws.cell(row=current_row, column=8, value="Рейк брутто")
    ws.cell(row=current_row, column=8).font = template_font_bold
    ws.cell(row=current_row, column=9, value=grand_total_rake)
    ws.cell(row=current_row, column=9).font = template_font_bold
    current_row += 1

    # Calculate totals for net rake
    # total_expenses: sum of negative balance adjustments (already negative values)
    total_expenses = sum(int(cast(int, ba.amount)) for ba in negative_adjustments) if negative_adjustments else 0
    # total_income: sum of positive balance adjustments
    total_income = sum(int(cast(int, ba.amount)) for ba in positive_adjustments) if positive_adjustments else 0

    # Net rake = rake brutto - expenses + income - salaries
    # Since total_expenses is already negative, we add it (which subtracts the expense)
    net_rake = grand_total_rake + total_expenses + total_income - total_staff_salary

    ws.cell(row=current_row, column=8, value="Рейк нетто")
    ws.cell(row=current_row, column=8).font = template_font_bold
    ws.cell(row=current_row, column=9, value=net_rake)
    ws.cell(row=current_row, column=9).font = template_font_bold
    current_row += 1
    rake_end = current_row - 1

    # Apply rake background
    for r in range(rake_start, rake_end + 1):
        for c in range(8, 11):  # H-J
            ws.cell(row=r, column=c).fill = rake_fill
            ws.cell(row=r, column=c).border = thin_border

    stats_end_row = current_row - 1  # Track end for outer border

    # Apply thick outer border around entire stats section
    thick_side = Side(style='medium')
    for r in range(stats_start_row, stats_end_row + 1):
        for c in range(8, 11):  # H-J
            cell = ws.cell(row=r, column=c)
            left = thick_side if c == 8 else cell.border.left
            right = thick_side if c == 10 else cell.border.right
            top = thick_side if r == stats_start_row else cell.border.top
            bottom = thick_side if r == stats_end_row else cell.border.bottom
            cell.border = Border(left=left, right=right, top=top, bottom=bottom)

    # === SECTION: L-O columns - Chip operations (+/-) ===
    # Data starts at column L (12) - shifted from R (18)
    # L = (-) amount, M = (-) time, N = (+) amount, O = (+) time

    QT_SECTION_START = 27 + rows_to_insert  # Template row 48

    # Note: H-U columns already cleared above

    # Define background colors for chip operations
    negative_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")  # Very light red/peach
    positive_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")  # Light green
    chip_thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # Header row - columns L-O (12-15) with title spanning across
    chips_start_row = QT_SECTION_START
    ws.cell(row=QT_SECTION_START, column=13, value="Жетоны")
    ws.cell(row=QT_SECTION_START, column=13).font = template_font_bold
    ws.cell(row=QT_SECTION_START, column=14, value="на столе")
    ws.cell(row=QT_SECTION_START, column=14).font = template_font_bold
    # Apply borders to header row
    for c in range(12, 16):
        ws.cell(row=QT_SECTION_START, column=c).border = chip_thin_border

    # Column headers row (2 rows down)
    headers_row = QT_SECTION_START + 2
    ws.cell(row=headers_row, column=12, value="(-)")
    ws.cell(row=headers_row, column=12).font = template_font_bold
    ws.cell(row=headers_row, column=12).fill = negative_fill
    ws.cell(row=headers_row, column=13).fill = negative_fill
    ws.cell(row=headers_row, column=14, value="(+)")
    ws.cell(row=headers_row, column=14).font = template_font_bold
    ws.cell(row=headers_row, column=14).fill = positive_fill
    ws.cell(row=headers_row, column=15).fill = positive_fill
    # Apply borders to headers row
    for c in range(12, 16):
        ws.cell(row=headers_row, column=c).border = chip_thin_border

    # Separate chip purchases into negative (cashouts) and positive (buy-ins)
    negative_ops: list[tuple[int, dt.datetime]] = []  # (amount, timestamp)
    positive_ops: list[tuple[int, dt.datetime]] = []  # (amount, timestamp)

    for p in purchases:
        amount = int(cast(int, p.amount))
        ts = cast(dt.datetime, p.created_at)
        if amount < 0:
            negative_ops.append((amount, ts))
        elif amount > 0:
            positive_ops.append((amount, ts))

    # Sort by timestamp
    negative_ops.sort(key=lambda x: x[1])
    positive_ops.sort(key=lambda x: x[1])

    # Write data rows
    data_start_row = headers_row + 1
    max_ops = max(len(negative_ops), len(positive_ops)) if negative_ops or positive_ops else 0

    for i in range(max_ops):
        row = data_start_row + i

        # Negative (cashout) - columns L (12) and M (13)
        cell_L = ws.cell(row=row, column=12)
        cell_M = ws.cell(row=row, column=13)
        cell_L.fill = negative_fill
        cell_L.border = chip_thin_border
        cell_M.fill = negative_fill
        cell_M.border = chip_thin_border
        if i < len(negative_ops):
            amount, ts = negative_ops[i]
            cell_L.value = amount
            cell_L.font = template_font
            cell_M.value = ts.strftime("%H:%M")
            cell_M.font = template_font

        # Positive (buy-in) - columns N (14) and O (15)
        cell_N = ws.cell(row=row, column=14)
        cell_O = ws.cell(row=row, column=15)
        cell_N.fill = positive_fill
        cell_N.border = chip_thin_border
        cell_O.fill = positive_fill
        cell_O.border = chip_thin_border
        if i < len(positive_ops):
            amount, ts = positive_ops[i]
            cell_N.value = amount
            cell_N.font = template_font
            cell_O.value = ts.strftime("%H:%M")
            cell_O.font = template_font

    # Totals row
    chips_end_row = data_start_row + max_ops - 1 if max_ops > 0 else headers_row
    if max_ops > 0:
        totals_row = data_start_row + max_ops
        neg_total = sum(op[0] for op in negative_ops)
        pos_total = sum(op[0] for op in positive_ops)

        # Negative total with label
        cell_L_tot = ws.cell(row=totals_row, column=12, value=neg_total)
        cell_L_tot.font = template_font_bold
        cell_L_tot.fill = negative_fill
        cell_L_tot.border = chip_thin_border
        cell_M_tot = ws.cell(row=totals_row, column=13, value="Σ(-)")
        cell_M_tot.font = template_font_bold
        cell_M_tot.fill = negative_fill
        cell_M_tot.border = chip_thin_border

        # Positive total with label
        cell_N_tot = ws.cell(row=totals_row, column=14, value=pos_total)
        cell_N_tot.font = template_font_bold
        cell_N_tot.fill = positive_fill
        cell_N_tot.border = chip_thin_border
        cell_O_tot = ws.cell(row=totals_row, column=15, value="Σ(+)")
        cell_O_tot.font = template_font_bold
        cell_O_tot.fill = positive_fill
        cell_O_tot.border = chip_thin_border

        # Net change row with label
        net_row = totals_row + 1
        ws.cell(row=net_row, column=12).border = chip_thin_border
        cell_net_label = ws.cell(row=net_row, column=13, value="Итого:")
        cell_net_label.font = template_font_bold
        cell_net_label.border = chip_thin_border
        cell_net = ws.cell(row=net_row, column=14, value=neg_total + pos_total)
        cell_net.font = template_font_bold
        cell_net.border = chip_thin_border
        ws.cell(row=net_row, column=15).border = chip_thin_border
        chips_end_row = net_row

    # Apply outer border to entire chip operations section
    thick_side = Side(style='medium')
    for r in range(chips_start_row, chips_end_row + 1):
        for c in range(12, 16):  # L-O
            cell = ws.cell(row=r, column=c)
            left = thick_side if c == 12 else cell.border.left
            right = thick_side if c == 15 else cell.border.right
            top = thick_side if r == chips_start_row else cell.border.top
            bottom = thick_side if r == chips_end_row else cell.border.bottom
            cell.border = Border(left=left, right=right, top=top, bottom=bottom)

    # X-Z columns are no longer used - already cleared in the bottom section clearing above


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
        # Merge cells for table header to span across columns (6 columns now includes Rake)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        for col in range(1, 7):
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

            # Staff earnings section with rake
            dealer_earnings = _calculate_session_dealer_earnings(session, db)
            waiter_earnings = _calculate_session_waiter_earnings(session, db)

            if dealer_earnings or waiter_earnings:
                row += 1  # Add spacing
                ws.cell(row=row, column=1, value="Персонал сессии:")
                ws.cell(row=row, column=1).font = Font(bold=True, italic=True)
                row += 1

                # Dealer earnings header (now with Rake column)
                if dealer_earnings:
                    staff_headers = ["Сотрудник", "Роль", "Часов", "Ставка/час", "Зарплата", "Рейк"]
                    for col, h in enumerate(staff_headers, 1):
                        ws.cell(row=row, column=col, value=h)
                    _style_header(ws, row, len(staff_headers))
                    row += 1

                    # Display each dealer's earnings with rake
                    total_dealer_salary = 0
                    total_dealer_rake = 0
                    for earning in dealer_earnings:
                        ws.cell(row=row, column=1, value=earning["dealer_name"])
                        ws.cell(row=row, column=2, value="Дилер")
                        ws.cell(row=row, column=3, value=round(earning["hours"], 2))
                        ws.cell(row=row, column=4, value=earning["hourly_rate"])
                        salary_cell = ws.cell(row=row, column=5, value=earning["salary"])
                        salary_cell.fill = MONEY_NEGATIVE_FILL  # Salary is an expense
                        total_dealer_salary += earning["salary"]
                        # Rake column
                        rake_value = earning.get("rake", 0) or 0
                        rake_cell = ws.cell(row=row, column=6, value=rake_value)
                        if rake_value > 0:
                            rake_cell.fill = MONEY_POSITIVE_FILL
                        total_dealer_rake += rake_value
                        row += 1

                    # Show total if multiple dealers
                    if len(dealer_earnings) > 1:
                        ws.cell(row=row, column=4, value="Итого дилеры:")
                        ws.cell(row=row, column=4).font = Font(bold=True)
                        total_cell = ws.cell(row=row, column=5, value=total_dealer_salary)
                        total_cell.font = Font(bold=True)
                        total_cell.fill = MONEY_NEGATIVE_FILL
                        total_rake_cell = ws.cell(row=row, column=6, value=total_dealer_rake)
                        total_rake_cell.font = Font(bold=True)
                        if total_dealer_rake > 0:
                            total_rake_cell.fill = MONEY_POSITIVE_FILL
                        row += 1

                # Waiter earnings
                if waiter_earnings:
                    # Add header if not already added
                    if not dealer_earnings:
                        staff_headers = ["Сотрудник", "Роль", "Часов", "Ставка/час", "Зарплата", "Рейк"]
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
                    ws.cell(row=row, column=6, value="—")  # Waiters don't have rake
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
    total_chip_income_credit = 0  # Credit buyins (informational only, NOT in rake calculation)

    for p in purchases:
        amount = int(cast(int, p.amount))
        if amount > 0:  # Buyin
            if p.payment_type == "credit":
                total_chip_income_credit += amount  # Track for info only
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

    # Gross rake ("грязный") = sum of manually entered rake entries from dealer assignments
    gross_rake = 0
    for s in sessions:
        for assignment in s.dealer_assignments:
            for entry in (assignment.rake_entries or []):
                gross_rake += int(cast(int, entry.amount))

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

    ws.cell(row=row, column=1, value="Количество сессий:")
    ws.cell(row=row, column=2, value=len(sessions))
    row += 1

    open_sessions = len([s for s in sessions if s.status == "open"])
    ws.cell(row=row, column=1, value="Открытых сессий:")
    ws.cell(row=row, column=2, value=open_sessions)

    _auto_width(ws)