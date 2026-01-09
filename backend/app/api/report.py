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
from ..models.db import CasinoBalanceAdjustment, ChipPurchase, Seat, Session, Table, User, ChipOp

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
    current_user: Any = Depends(require_roles("superadmin")),
):
    """
    Get the preselected date for the daily summary page.
    
    Returns the starting day of:
    1. Current working day if it's not yet finished (has open sessions)
    2. Most recent working day if current one is finished but next hasn't started
    
    Working day: 20:00 (8 PM) to 18:00 (6 PM) of next day.
    """
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
    open_sessions = (
        db.query(Session)
        .filter(Session.created_at >= start_time, Session.created_at < end_time)
        .filter(Session.status == "open")
        .first()
    )
    
    if open_sessions:
        # Current working day is not finished
        return {"date": working_day_start.isoformat()}
    
    # Check if current working day has any sessions at all
    any_sessions = (
        db.query(Session)
        .filter(Session.created_at >= start_time, Session.created_at < end_time)
        .first()
    )
    
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
            .first()
        )
        
        if prev_sessions:
            return {"date": prev_day.isoformat()}
    
    # No sessions found in the last 7 days, return current working day
    return {"date": working_day_start.isoformat()}


@router.get("/day-summary")
def get_day_summary(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    db: DBSession = Depends(get_db),
    current_user: Any = Depends(require_roles("superadmin")),
):
    """Get day summary data (profit/loss) as JSON for mobile display."""
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Get working day boundaries (20:00 to 18:00 next day)
    start_time, end_time = _get_working_day_boundaries(d)

    # Fetch sessions for the working day
    sessions = (
        db.query(Session)
        .options(joinedload(Session.dealer), joinedload(Session.waiter))
        .filter(Session.created_at >= start_time, Session.created_at < end_time)
        .order_by(Session.table_id.asc(), Session.created_at.asc())
        .all()
    )

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
    balance_adjustments = (
        db.query(CasinoBalanceAdjustment)
        .options(joinedload(CasinoBalanceAdjustment.created_by))
        .filter(CasinoBalanceAdjustment.created_at >= start_time, CasinoBalanceAdjustment.created_at < end_time)
        .order_by(CasinoBalanceAdjustment.created_at.asc())
        .all()
    )

    # Fetch all staff
    staff = db.query(User).filter(User.role.in_(["dealer", "waiter"])).all()

    # Calculate totals
    total_chip_income_cash = 0  # Cash buyins
    total_chip_income_credit = 0  # Credit buyins (expenses)
    total_balance_adjustments_profit = 0  # Positive adjustments
    total_balance_adjustments_expense = 0  # Negative adjustments (absolute value)

    for p in purchases:
        amount = int(cast(int, p.amount))
        if amount > 0:  # Buyin
            if p.payment_type == "credit":
                total_chip_income_credit += amount
            else:
                total_chip_income_cash += amount

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

    # Calculate staff salary
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

    # Calculate net per-seat totals
    total_player_balance = 0
    for sid, seats in seats_by_session.items():
        for seat in seats:
            total_player_balance += int(cast(int, seat.total))

    # Casino result
    casino_result = total_chip_income_cash - total_player_balance - total_salary - total_chip_income_credit + total_balance_adjustments_profit - total_balance_adjustments_expense

    open_sessions = len([s for s in sessions if s.status == "open"])

    return {
        "date": date,
        "income": {
            "buyin_cash": total_chip_income_cash,
            "balance_adjustments": total_balance_adjustments_profit,
        },
        "expenses": {
            "salaries": total_salary,
            "buyin_credit": total_chip_income_credit,
            "balance_adjustments": total_balance_adjustments_expense,
        },
        "result": casino_result,
        "info": {
            "player_balance": total_player_balance,
            "total_sessions": len(sessions),
            "open_sessions": open_sessions,
        },
        "staff": staff_details,
        "balance_adjustments": balance_adjustments_list,
    }


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
    for column_cells in ws.columns:
        max_length = 0
        column = column_cells[0].column_letter
        for cell in column_cells:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        # Increased minimum width from (max_length + 2) to (max_length + 4) for better fit
        # Also increased maximum from 50 to 60 for longer text fields
        adjusted_width = min(max_length + 4, 60)
        # Ensure minimum width of 12 for very short columns
        adjusted_width = max(adjusted_width, 12)
        ws.column_dimensions[column].width = adjusted_width


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
    Calculate dealer working hours. Dealers can only work one session at a time,
    so we just sum up the session durations.
    """
    total_seconds = 0.0
    for s in sessions:
        if s.dealer_id != dealer_id:
            continue
        start = cast(dt.datetime, s.created_at)
        end = cast(dt.datetime, s.closed_at) if s.closed_at else dt.datetime.utcnow()
        total_seconds += (end - start).total_seconds()
    return total_seconds / 3600.0


@router.get(
    "/export-report",
    dependencies=[Depends(require_roles("superadmin"))],
)
def export_report(
    date: str = Query(..., description="YYYY-MM-DD"),
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate comprehensive XLSX report for a specific date."""
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (expected YYYY-MM-DD)")

    # Get working day boundaries (20:00 to 18:00 next day)
    start_time, end_time = _get_working_day_boundaries(d)

    # Fetch all data for the working day
    tables = db.query(Table).order_by(Table.id.asc()).all()
    sessions = (
        db.query(Session)
        .options(joinedload(Session.dealer), joinedload(Session.waiter))
        .filter(Session.created_at >= start_time, Session.created_at < end_time)
        .order_by(Session.table_id.asc(), Session.created_at.asc())
        .all()
    )

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
    balance_adjustments = (
        db.query(CasinoBalanceAdjustment)
        .options(joinedload(CasinoBalanceAdjustment.created_by))
        .filter(CasinoBalanceAdjustment.created_at >= start_time, CasinoBalanceAdjustment.created_at < end_time)
        .order_by(CasinoBalanceAdjustment.created_at.asc())
        .all()
    )

    # Fetch all staff (dealers and waiters)
    staff = db.query(User).filter(User.role.in_(["dealer", "waiter"])).all()

    # Create workbook
    wb = Workbook()
    wb.remove(wb.active)  # Remove default sheet

    # Sheet 1: Table States (per-seat summary for each table)
    _create_table_states_sheet(wb, tables, sessions, seats_by_session)

    # Sheet 2: Chip Purchase Chronology
    _create_purchases_sheet(wb, purchases, tables, db)

    # Sheet 3: Staff Salaries
    _create_staff_sheet(wb, sessions, staff, d)

    # Sheet 4: Balance Adjustments
    _create_balance_adjustments_sheet(wb, balance_adjustments, d)

    # Sheet 5: Summary (Profit/Expense)
    _create_summary_sheet(wb, sessions, seats_by_session, purchases, staff, balance_adjustments, d)

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
):
    """Create sheet with table states - seats, players, and totals."""
    ws = wb.create_sheet(title="Состояние столов")

    if not sessions:
        ws.cell(row=1, column=1, value="Нет данных за выбранную дату")
        ws.cell(row=1, column=1).font = Font(italic=True)
        return

    row = 1
    for table in tables:
        table_sessions = [s for s in sessions if s.table_id == table.id]
        if not table_sessions:
            continue

        # Table header
        ws.cell(row=row, column=1, value=f"Стол: {table.name}")
        ws.cell(row=row, column=1).font = Font(bold=True, size=14)
        row += 1

        for session in table_sessions:
            sid = cast(str, session.id)
            seats = seats_by_session.get(sid, [])

            # Session info
            start_time = cast(dt.datetime, session.created_at).strftime("%H:%M")
            if session.closed_at:
                end_time = cast(dt.datetime, session.closed_at).strftime("%H:%M")
            elif session.status == "closed":
                end_time = "закрыта"
            else:
                end_time = "открыта"
            dealer_name = session.dealer.username if session.dealer else "—"
            waiter_name = session.waiter.username if session.waiter else "—"
            status_text = "закрыта" if session.status == "closed" else "открыта"
            chips_in_play = int(cast(int, session.chips_in_play))

            ws.cell(row=row, column=1, value=f"Сессия: {start_time} - {end_time}")
            ws.cell(row=row, column=2, value=f"Дилер: {dealer_name}")
            ws.cell(row=row, column=3, value=f"Официант: {waiter_name}")
            ws.cell(row=row, column=4, value=f"Статус: {status_text}")
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
            row += 2

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
        if amount > 0:
            cell.fill = MONEY_POSITIVE_FILL
        elif amount < 0:
            cell.fill = MONEY_NEGATIVE_FILL

        # Payment type column
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
):
    """Create summary sheet with profit/expense overview."""
    ws = wb.create_sheet(title="Итоги дня")

    # Calculate totals
    total_chip_income_cash = 0  # Cash buyins
    total_chip_income_credit = 0  # Credit buyins (expenses)

    for p in purchases:
        amount = int(cast(int, p.amount))
        if amount > 0:  # Buyin
            if p.payment_type == "credit":
                total_chip_income_credit += amount
            else:
                total_chip_income_cash += amount

    # Calculate balance adjustments
    total_balance_adjustments_profit = 0
    total_balance_adjustments_expense = 0
    for adj in balance_adjustments:
        amount = int(cast(int, adj.amount))
        if amount > 0:
            total_balance_adjustments_profit += amount
        else:
            total_balance_adjustments_expense += abs(amount)

    # Calculate staff salary
    total_salary = 0
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

    ws.cell(row=row, column=1, value="Покупка фишек (наличные):")
    ws.cell(row=row, column=2, value=total_chip_income_cash)
    ws.cell(row=row, column=2).fill = MONEY_POSITIVE_FILL
    row += 1

    ws.cell(row=row, column=1, value="Корректировки баланса (доход):")
    ws.cell(row=row, column=2, value=total_balance_adjustments_profit)
    ws.cell(row=row, column=2).fill = MONEY_POSITIVE_FILL
    row += 2

    # Expense section
    ws.cell(row=row, column=1, value="РАСХОДЫ")
    ws.cell(row=row, column=1).font = Font(bold=True)
    ws.cell(row=row, column=1).fill = MONEY_NEGATIVE_FILL
    row += 1

    ws.cell(row=row, column=1, value="Зарплаты персонала:")
    ws.cell(row=row, column=2, value=total_salary)
    ws.cell(row=row, column=2).fill = MONEY_NEGATIVE_FILL
    row += 1

    ws.cell(row=row, column=1, value="Покупка фишек (кредит):")
    ws.cell(row=row, column=2, value=total_chip_income_credit)
    ws.cell(row=row, column=2).fill = MONEY_NEGATIVE_FILL
    row += 1

    ws.cell(row=row, column=1, value="Корректировки баланса (расход):")
    ws.cell(row=row, column=2, value=total_balance_adjustments_expense)
    ws.cell(row=row, column=2).fill = MONEY_NEGATIVE_FILL
    row += 2

    # Net result
    # Casino profit = cash_buyin - player_balance (what players have left) - salary - credit_buyin + adj_profit - adj_expense
    casino_result = total_chip_income_cash - total_player_balance - total_salary - total_chip_income_credit + total_balance_adjustments_profit - total_balance_adjustments_expense

    ws.cell(row=row, column=1, value="ИТОГО ЗА ДЕНЬ:")
    ws.cell(row=row, column=1).font = Font(bold=True, size=12)
    cell = ws.cell(row=row, column=2, value=casino_result)
    cell.font = Font(bold=True, size=12)
    if casino_result >= 0:
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

    ws.cell(row=row, column=1, value="Количество сессий:")
    ws.cell(row=row, column=2, value=len(sessions))
    row += 1

    open_sessions = len([s for s in sessions if s.status == "open"])
    ws.cell(row=row, column=1, value="Открытых сессий:")
    ws.cell(row=row, column=2, value=open_sessions)

    _auto_width(ws)