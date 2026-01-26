from __future__ import annotations

import logging
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .api import admin_router, auth_router, sessions_router, report_router
from .core.config import settings
from .core.db import SessionLocal, engine
from .core.security import get_password_hash
from .core.migrations import run_migrations, stamp_database, get_current_revision
from .models.db import Base, User


def configure_logging() -> None:
    """Configure structured logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    
    # Set specific log levels for third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)
configure_logging()


def create_app() -> FastAPI:
    app = FastAPI(title="Chips Manager", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    # Add request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log incoming requests."""
        logger.info(f"Request: {request.method} {request.url.path}")
        response = await call_next(request)
        logger.info(f"Response: {request.method} {request.url.path} - Status: {response.status_code}")
        return response

    app.include_router(auth_router)
    app.include_router(sessions_router)
    app.include_router(admin_router)
    app.include_router(report_router)

    @app.get("/")
    def root():
        return {"ok": True, "service": "chips-manager", "docs": "/docs"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.on_event("startup")
    def startup():
        logger.info("Starting application...")

        # Check if database has been initialized with migrations
        current_rev = get_current_revision()

        if current_rev is None:
            # Database exists but hasn't been stamped with a migration version yet
            # This means it's an existing database that was created with create_all()
            # We need to stamp it with the initial migration without running it
            logger.info("Existing database detected without migration version")
            logger.info("Stamping database with initial migration (001)...")
            try:
                stamp_database("001")
                logger.info("Database stamped successfully")
            except Exception as e:
                logger.warning(f"Could not stamp database: {e}")
                logger.info("Falling back to create_all() for database initialization")
                Base.metadata.create_all(bind=engine)

        # Run any pending migrations
        try:
            run_migrations()
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            logger.info("Falling back to create_all() for database initialization")
            Base.metadata.create_all(bind=engine)

        logger.info("Database tables created/verified")

        # ============================================================================
        # LEGACY MANUAL MIGRATIONS (kept for backward compatibility)
        # These are kept to ensure smooth transition for existing databases.
        # New schema changes should be added as Alembic migrations instead.
        # ============================================================================

        # Migrate: add dealer_id and waiter_id columns to sessions if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT dealer_id FROM sessions LIMIT 1"))
            except Exception:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN dealer_id INTEGER REFERENCES users(id)"))
                conn.commit()
            try:
                conn.execute(text("SELECT waiter_id FROM sessions LIMIT 1"))
            except Exception:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN waiter_id INTEGER REFERENCES users(id)"))
                conn.commit()

        # Migrate: add hourly_rate column to users if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT hourly_rate FROM users LIMIT 1"))
            except Exception:
                conn.execute(text("ALTER TABLE users ADD COLUMN hourly_rate INTEGER"))
                conn.commit()

        # Migrate: add closed_at column to sessions if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT closed_at FROM sessions LIMIT 1"))
            except Exception:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN closed_at DATETIME"))
                conn.commit()

        # Migrate: add rake_in and rake_out columns to sessions if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT rake_in FROM sessions LIMIT 1"))
            except Exception:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN rake_in INTEGER NOT NULL DEFAULT 0"))
                conn.commit()
            try:
                conn.execute(text("SELECT rake_out FROM sessions LIMIT 1"))
            except Exception:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN rake_out INTEGER NOT NULL DEFAULT 0"))
                conn.commit()

        # Migrate: add payment_type column to chip_purchases if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT payment_type FROM chip_purchases LIMIT 1"))
            except Exception:
                conn.execute(text("ALTER TABLE chip_purchases ADD COLUMN payment_type VARCHAR(16) NOT NULL DEFAULT 'cash'"))
                conn.commit()

        # Migrate: add chips_in_play column to sessions if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT chips_in_play FROM sessions LIMIT 1"))
            except Exception as e:
                logger.info(f"Adding chips_in_play column to sessions: {e}")
                conn.execute(text("ALTER TABLE sessions ADD COLUMN chips_in_play INTEGER NOT NULL DEFAULT 0"))
                conn.commit()
                logger.info("Successfully added chips_in_play column to sessions")

        # Migrate: create casino_balance_adjustments table if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT id FROM casino_balance_adjustments LIMIT 1"))
            except Exception:
                conn.execute(text("""
                    CREATE TABLE casino_balance_adjustments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at DATETIME NOT NULL,
                        amount INTEGER NOT NULL,
                        comment TEXT NOT NULL,
                        created_by_user_id INTEGER NOT NULL,
                        FOREIGN KEY (created_by_user_id) REFERENCES users(id)
                    )
                """))
                conn.commit()

        # Migrate: create session_dealer_assignments table if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT id FROM session_dealer_assignments LIMIT 1"))
            except Exception:
                logger.info("Creating session_dealer_assignments table")
                conn.execute(text("""
                    CREATE TABLE session_dealer_assignments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id VARCHAR(36) NOT NULL,
                        dealer_id INTEGER NOT NULL,
                        started_at DATETIME NOT NULL,
                        ended_at DATETIME,
                        FOREIGN KEY (session_id) REFERENCES sessions(id),
                        FOREIGN KEY (dealer_id) REFERENCES users(id)
                    )
                """))
                conn.execute(text("CREATE INDEX ix_session_dealer_assignment_session ON session_dealer_assignments(session_id)"))
                conn.execute(text("CREATE INDEX ix_session_dealer_assignment_dealer ON session_dealer_assignments(dealer_id)"))
                conn.commit()
                logger.info("Successfully created session_dealer_assignments table")

        # Migrate: add rake column to session_dealer_assignments if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT rake FROM session_dealer_assignments LIMIT 1"))
            except Exception:
                logger.info("Adding rake column to session_dealer_assignments")
                conn.execute(text("ALTER TABLE session_dealer_assignments ADD COLUMN rake INTEGER"))
                conn.commit()
                logger.info("Successfully added rake column to session_dealer_assignments")

        # Migrate: create session_waiter_assignments table if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT id FROM session_waiter_assignments LIMIT 1"))
            except Exception:
                logger.info("Creating session_waiter_assignments table")
                conn.execute(text("""
                    CREATE TABLE session_waiter_assignments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id VARCHAR(36) NOT NULL,
                        waiter_id INTEGER NOT NULL,
                        started_at DATETIME NOT NULL,
                        ended_at DATETIME,
                        FOREIGN KEY (session_id) REFERENCES sessions(id),
                        FOREIGN KEY (waiter_id) REFERENCES users(id)
                    )
                """))
                conn.execute(text("CREATE INDEX ix_session_waiter_assignment_session ON session_waiter_assignments(session_id)"))
                conn.execute(text("CREATE INDEX ix_session_waiter_assignment_waiter ON session_waiter_assignments(waiter_id)"))
                conn.commit()
                logger.info("Successfully created session_waiter_assignments table")

        # Migrate: create seat_name_changes table if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT id FROM seat_name_changes LIMIT 1"))
            except Exception:
                logger.info("Creating seat_name_changes table")
                conn.execute(text("""
                    CREATE TABLE seat_name_changes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id VARCHAR(36) NOT NULL,
                        seat_no INTEGER NOT NULL,
                        old_name VARCHAR(255),
                        new_name VARCHAR(255),
                        change_type VARCHAR(32) NOT NULL DEFAULT 'name_change',
                        created_at DATETIME NOT NULL,
                        created_by_user_id INTEGER NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES sessions(id),
                        FOREIGN KEY (created_by_user_id) REFERENCES users(id)
                    )
                """))
                conn.commit()
                logger.info("Successfully created seat_name_changes table")

        # Migrate: add change_type column to seat_name_changes if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT change_type FROM seat_name_changes LIMIT 1"))
            except Exception:
                logger.info("Adding change_type column to seat_name_changes")
                conn.execute(text("ALTER TABLE seat_name_changes ADD COLUMN change_type VARCHAR(32) NOT NULL DEFAULT 'name_change'"))
                conn.commit()
                logger.info("Successfully added change_type column to seat_name_changes")

        # Migrate: add owner_id column to tables if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT owner_id FROM tables LIMIT 1"))
            except Exception:
                logger.info("Adding owner_id column to tables")
                conn.execute(text("ALTER TABLE tables ADD COLUMN owner_id INTEGER REFERENCES users(id)"))
                conn.execute(text("CREATE INDEX ix_tables_owner ON tables(owner_id)"))
                conn.commit()
                logger.info("Successfully added owner_id column to tables")

        # Migrate: add owner_id column to casino_balance_adjustments if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT owner_id FROM casino_balance_adjustments LIMIT 1"))
            except Exception:
                logger.info("Adding owner_id column to casino_balance_adjustments")
                conn.execute(text("ALTER TABLE casino_balance_adjustments ADD COLUMN owner_id INTEGER REFERENCES users(id)"))
                conn.execute(text("CREATE INDEX ix_balance_adjustment_owner ON casino_balance_adjustments(owner_id)"))
                conn.commit()
                logger.info("Successfully added owner_id column to casino_balance_adjustments")

        # Migrate: add owner_id column to users if missing
        with engine.connect() as conn:
            try:
                conn.execute(text("SELECT owner_id FROM users LIMIT 1"))
            except Exception:
                logger.info("Adding owner_id column to users")
                conn.execute(text("ALTER TABLE users ADD COLUMN owner_id INTEGER REFERENCES users(id)"))
                conn.execute(text("CREATE INDEX ix_user_owner ON users(owner_id)"))
                conn.commit()
                logger.info("Successfully added owner_id column to users")

        # Migrate: populate session_dealer_assignments from existing sessions with dealers
        db = SessionLocal()
        try:
            from .models.db import Session as SessionModel, SessionDealerAssignment
            # Check if there are sessions with dealers that don't have assignments yet
            sessions_with_dealers = db.query(SessionModel).filter(
                SessionModel.dealer_id.isnot(None)
            ).all()

            for session in sessions_with_dealers:
                # Check if this session already has dealer assignments
                existing = db.query(SessionDealerAssignment).filter(
                    SessionDealerAssignment.session_id == session.id
                ).first()
                if not existing:
                    # Create initial assignment from session's dealer_id
                    ended_at = session.closed_at if session.status == "closed" else None
                    assignment = SessionDealerAssignment(
                        session_id=session.id,
                        dealer_id=session.dealer_id,
                        started_at=session.created_at,
                        ended_at=ended_at,
                    )
                    db.add(assignment)
                    logger.info(f"Migrated dealer assignment for session {session.id}")
            db.commit()
        except Exception as e:
            logger.warning(f"Error migrating dealer assignments: {e}")
            db.rollback()
        finally:
            db.close()

        # Migrate: populate session_waiter_assignments from existing sessions with waiters
        db = SessionLocal()
        try:
            from .models.db import Session as SessionModel, SessionWaiterAssignment
            # Check if there are sessions with waiters that don't have assignments yet
            sessions_with_waiters = db.query(SessionModel).filter(
                SessionModel.waiter_id.isnot(None)
            ).all()

            for session in sessions_with_waiters:
                # Check if this session already has waiter assignments
                existing = db.query(SessionWaiterAssignment).filter(
                    SessionWaiterAssignment.session_id == session.id
                ).first()
                if not existing:
                    # Create initial assignment from session's waiter_id
                    ended_at = session.closed_at if session.status == "closed" else None
                    assignment = SessionWaiterAssignment(
                        session_id=session.id,
                        waiter_id=session.waiter_id,
                        started_at=session.created_at,
                        ended_at=ended_at,
                    )
                    db.add(assignment)
                    logger.info(f"Migrated waiter assignment for session {session.id}")
            db.commit()
        except Exception as e:
            logger.warning(f"Error migrating waiter assignments: {e}")
            db.rollback()
        finally:
            db.close()

        db = SessionLocal()
        try:
          exists = db.query(User).filter(User.role == "superadmin").first()
          if not exists:
              logger.info("Creating default superadmin user")
              u = User(
                  username=settings.SUPERADMIN_USERNAME,
                  password_hash=get_password_hash(settings.SUPERADMIN_PASSWORD),
                  role="superadmin",
                  table_id=None,
                  is_active=True,
              )
              db.add(u)
              db.commit()
              logger.info(f"Superadmin user '{settings.SUPERADMIN_USERNAME}' created successfully")
          else:
              logger.info("Superadmin user already exists")
        finally:
            db.close()
        
        logger.info("Application startup complete")

    return app


app = create_app()
