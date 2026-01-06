from __future__ import annotations

import csv
import datetime as dt
import io
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession, joinedload

from typing import Any, cast

from ..core.deps import get_current_user, get_db, require_roles
from ..core.security import get_password_hash
from ..models.db import ChipPurchase, Seat, Session, Table, User
from ..models.schemas import (
    ChipPurchaseOut,
    TableCreateIn,
    TableOut,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _normalize_username(v: str) -> str:
    return v.strip()


def _normalize_table_name(v: str) -> str:
    return v.strip()


def _sanitize_cell(v: str) -> str:
    # В CSV/TSV переносы строк и табы часто ломают "по-строчно" парсинг в Excel/BI
    return v.replace("\r", " ").replace("\n", " ").replace("\t", " ")


def _ascii_filename_component(name: str) -> str:
    # Нужен именно ASCII, иначе часть клиентов игнорирует filename= и берёт "кракозябры"
    out = []
    for ch in name:
        if ch.isascii() and (ch.isalnum() or ch in "._-"):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


@router.get("/tables", response_model=list[TableOut])
def list_tables(
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    role = cast(str, user.role)

    if role == "superadmin":
        tables = db.query(Table).order_by(Table.id.asc()).all()
        return [TableOut.model_validate(t) for t in tables]

    if user.table_id is None:
        return []

    t = db.query(Table).filter(Table.id == user.table_id).first()
    return [TableOut.model_validate(t)] if t else []


@router.post("/tables", response_model=TableOut, dependencies=[Depends(require_roles("superadmin"))])
def create_table(payload: TableCreateIn, db: DBSession = Depends(get_db)) -> TableOut:
    name = _normalize_table_name(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="Table name is required")

    existing = db.query(Table).filter(Table.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Table name already exists")

    t = Table(name=name, seats_count=payload.seats_count)
    db.add(t)
    db.commit()
    db.refresh(t)
    return TableOut.model_validate(t)


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_roles("superadmin"))])
def list_users(db: DBSession = Depends(get_db)) -> list[UserOut]:
    users = db.query(User).order_by(User.id.asc()).all()
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


@router.post("/users", response_model=UserOut, dependencies=[Depends(require_roles("superadmin"))])
def create_user(payload: UserCreateIn, db: DBSession = Depends(get_db)) -> UserOut:
    username = _normalize_username(payload.username)
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    if payload.role == "table_admin":
        # table_admin requires table_id
        if payload.table_id is None:
            raise HTTPException(status_code=400, detail="table_id is required for table_admin role")
        if not db.query(Table).filter(Table.id == payload.table_id).first():
            raise HTTPException(status_code=404, detail="Table not found")
        _replace_existing_table_admin(db, payload.table_id)
    elif payload.role == "dealer":
        # dealer is not associated with tables, will be assigned to sessions
        if payload.table_id is not None:
            raise HTTPException(status_code=400, detail="dealer role should not have table_id")
    elif payload.role == "waiter" and payload.table_id is not None:
        # waiter can optionally have a table_id, validate it if provided
        if not db.query(Table).filter(Table.id == payload.table_id).first():
            raise HTTPException(status_code=404, detail="Table not found")

    # hourly_rate is only applicable for dealer and waiter roles
    hourly_rate = payload.hourly_rate if payload.role in ("dealer", "waiter") else None

    u = User(
        username=username,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
        table_id=payload.table_id if payload.role == "table_admin" else None,
        is_active=payload.is_active,
        hourly_rate=hourly_rate,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return UserOut.model_validate(u)


@router.put("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_roles("superadmin"))])
def update_user(user_id: int, payload: UserUpdateIn, db: DBSession = Depends(get_db)) -> UserOut:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.role is not None:
        u.role = cast(Any, str(payload.role))

    if payload.table_id is not None:
        u.table_id = cast(Any, payload.table_id)

    if payload.is_active is not None:
        u.is_active = cast(Any, payload.is_active)

    if payload.password is not None:
        u.password_hash = cast(Any, get_password_hash(payload.password))

    if payload.hourly_rate is not None:
        u.hourly_rate = cast(Any, payload.hourly_rate)

    u_role = cast(str, u.role)

    if u_role == "superadmin":
        u.table_id = cast(Any, None)
        u.hourly_rate = cast(Any, None)  # hourly_rate not applicable for superadmin
    elif u_role == "dealer":
        # dealer is not associated with tables, will be assigned to sessions
        u.table_id = cast(Any, None)
    elif u_role == "table_admin":
        # table_admin requires table_id
        if u.table_id is None:
            raise HTTPException(status_code=400, detail="table_id is required for table_admin role")
        if not db.query(Table).filter(Table.id == u.table_id).first():
            raise HTTPException(status_code=404, detail="Table not found")
        _replace_existing_table_admin(
            db,
            table_id=int(cast(int, u.table_id)),
            exclude_user_id=int(cast(int, u.id)),
        )
        u.hourly_rate = cast(Any, None)  # hourly_rate not applicable for table_admin
    elif u_role == "waiter":
        # waiter can optionally have a table_id, validate it if provided
        if u.table_id is not None:
            if not db.query(Table).filter(Table.id == u.table_id).first():
                raise HTTPException(status_code=404, detail="Table not found")

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


@router.get("/export")
def export_day(
    date: str = Query(..., description="YYYY-MM-DD"),
    table_id: int | None = Query(default=None),
    format: str = Query(default="tsv", pattern="^(tsv|csv)$"),
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        d = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (expected YYYY-MM-DD)")

    role = cast(str, user.role)

    if role not in ("superadmin", "table_admin", "waiter"):
        raise HTTPException(status_code=403, detail="Forbidden")

    if role == "superadmin":
        if table_id is None:
            raise HTTPException(status_code=400, detail="table_id is required for superadmin")
        tid = int(table_id)
    else:
        if user.table_id is None:
            raise HTTPException(status_code=403, detail="No table assigned")
        tid = int(cast(int, user.table_id))
        if table_id is not None and int(table_id) != tid:
            raise HTTPException(status_code=403, detail="Forbidden for this table")

    table = db.query(Table).filter(Table.id == tid).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    sessions = (
        db.query(Session)
        .filter(Session.table_id == tid, Session.date == d)
        .order_by(Session.created_at.asc())
        .all()
    )

    fmt = format
    delim = "\t" if fmt == "tsv" else ","
    media_type = "text/tab-separated-values" if fmt == "tsv" else "text/csv"

    session_ids = [cast(str, s.id) for s in sessions]
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

    table_name = cast(str, table.name)

    filename = f"session_{table_name}_{date}.{fmt}"
    filename_ascii = f"session_{_ascii_filename_component(table_name)}_{date}.{fmt}"

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=delim, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)

        w.writerow(["table", "date", "session_id", "status", "seat_no", "player_name", "total"])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for s in sessions:
            sid = cast(str, s.id)
            s_status = cast(str, s.status)
            seats = seats_by_session.get(sid, [])

            for seat in seats:
                pn = cast(str, seat.player_name) if seat.player_name is not None else ""
                pn = _sanitize_cell(pn)

                w.writerow(
                    [
                        table_name,
                        s.date.isoformat(),
                        sid,
                        s_status,
                        str(int(cast(int, seat.seat_no))),
                        pn,
                        str(int(cast(int, seat.total))),
                    ]
                )
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)

    headers = {
        "Content-Disposition": (
            f'attachment; filename="{filename_ascii}"; '
            f"filename*=UTF-8''{quote(filename)}"
        )
    }
    return StreamingResponse(gen(), media_type=media_type, headers=headers)
