from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .api import admin_router, auth_router, sessions_router
from .core.config import settings
from .core.db import SessionLocal, engine
from .core.security import get_password_hash
from .models.db import Base, User


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

    app.include_router(auth_router)
    app.include_router(sessions_router)
    app.include_router(admin_router)

    @app.get("/")
    def root():
        return {"ok": True, "service": "chips-manager", "docs": "/docs"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.on_event("startup")
    def startup():
        Base.metadata.create_all(bind=engine)

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

        db = SessionLocal()
        try:
          exists = db.query(User).filter(User.role == "superadmin").first()
          if not exists:
              u = User(
                  username=settings.SUPERADMIN_USERNAME,
                  password_hash=get_password_hash(settings.SUPERADMIN_PASSWORD),
                  role="superadmin",
                  table_id=None,
                  is_active=True,
              )
              db.add(u)
              db.commit()
        finally:
            db.close()

    return app


app = create_app()
