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
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")

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
