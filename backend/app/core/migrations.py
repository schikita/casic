"""Database migration utilities using Alembic."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)


def get_alembic_config() -> Config:
    """Get Alembic configuration object."""
    # Get the backend directory (parent of app directory)
    backend_dir = Path(__file__).parent.parent.parent
    alembic_ini_path = backend_dir / "alembic.ini"
    
    if not alembic_ini_path.exists():
        raise FileNotFoundError(f"alembic.ini not found at {alembic_ini_path}")
    
    alembic_cfg = Config(str(alembic_ini_path))
    
    # Set the script location to the alembic directory
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    
    return alembic_cfg


def run_migrations() -> None:
    """Run all pending database migrations."""
    try:
        logger.info("Running database migrations...")
        alembic_cfg = get_alembic_config()
        
        # Run migrations to the latest version
        command.upgrade(alembic_cfg, "head")
        
        logger.info("Database migrations completed successfully")
    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        raise


def stamp_database(revision: str = "head") -> None:
    """
    Stamp the database with a specific revision without running migrations.
    
    This is useful for marking an existing database as being at a specific
    migration version without actually running the migration SQL.
    
    Args:
        revision: The revision to stamp (default: "head" for latest)
    """
    try:
        logger.info(f"Stamping database with revision: {revision}")
        alembic_cfg = get_alembic_config()
        command.stamp(alembic_cfg, revision)
        logger.info(f"Database stamped successfully with revision: {revision}")
    except Exception as e:
        logger.error(f"Error stamping database: {e}")
        raise


def get_current_revision() -> str | None:
    """Get the current database revision."""
    try:
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine
        from .config import settings
        
        # Create engine with same settings as main app
        connect_args = {}
        if settings.DB_URL.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        
        engine = create_engine(settings.DB_URL, connect_args=connect_args)
        
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()
            return current_rev
    except Exception as e:
        logger.warning(f"Could not get current revision: {e}")
        return None

