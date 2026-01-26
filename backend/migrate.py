#!/usr/bin/env python3
"""
Database migration helper script.

This script provides convenient commands for managing database migrations using Alembic.

Usage:
    python migrate.py create "description of changes"  # Create a new migration
    python migrate.py upgrade                          # Apply all pending migrations
    python migrate.py downgrade                        # Rollback one migration
    python migrate.py current                          # Show current migration version
    python migrate.py history                          # Show migration history
    python migrate.py stamp <revision>                 # Mark database as being at a specific revision
"""

import sys
from pathlib import Path

# Add the backend directory to the path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from alembic import command
from alembic.config import Config


def get_alembic_config() -> Config:
    """Get Alembic configuration."""
    alembic_ini = backend_dir / "alembic.ini"
    if not alembic_ini.exists():
        print(f"Error: alembic.ini not found at {alembic_ini}")
        sys.exit(1)
    
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    return cfg


def create_migration(message: str):
    """Create a new migration with autogenerate."""
    print(f"Creating new migration: {message}")
    cfg = get_alembic_config()
    command.revision(cfg, message=message, autogenerate=True)
    print("Migration created successfully!")
    print("\nNext steps:")
    print("1. Review the generated migration file in alembic/versions/")
    print("2. Test the migration: python migrate.py upgrade")
    print("3. Rebuild and restart docker containers to apply changes")


def upgrade_migrations():
    """Apply all pending migrations."""
    print("Applying pending migrations...")
    cfg = get_alembic_config()
    command.upgrade(cfg, "head")
    print("Migrations applied successfully!")


def downgrade_migration():
    """Rollback one migration."""
    print("Rolling back one migration...")
    cfg = get_alembic_config()
    command.downgrade(cfg, "-1")
    print("Migration rolled back successfully!")


def show_current():
    """Show current migration version."""
    print("Current migration version:")
    cfg = get_alembic_config()
    command.current(cfg)


def show_history():
    """Show migration history."""
    print("Migration history:")
    cfg = get_alembic_config()
    command.history(cfg)


def stamp_revision(revision: str):
    """Stamp database with a specific revision."""
    print(f"Stamping database with revision: {revision}")
    cfg = get_alembic_config()
    command.stamp(cfg, revision)
    print("Database stamped successfully!")


def print_usage():
    """Print usage information."""
    print(__doc__)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    
    cmd = sys.argv[1].lower()
    
    if cmd == "create":
        if len(sys.argv) < 3:
            print("Error: Please provide a migration message")
            print('Usage: python migrate.py create "description of changes"')
            sys.exit(1)
        message = sys.argv[2]
        create_migration(message)
    
    elif cmd == "upgrade":
        upgrade_migrations()
    
    elif cmd == "downgrade":
        downgrade_migration()
    
    elif cmd == "current":
        show_current()
    
    elif cmd == "history":
        show_history()
    
    elif cmd == "stamp":
        if len(sys.argv) < 3:
            print("Error: Please provide a revision")
            print('Usage: python migrate.py stamp <revision>')
            sys.exit(1)
        revision = sys.argv[2]
        stamp_revision(revision)
    
    else:
        print(f"Error: Unknown command '{cmd}'")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()

