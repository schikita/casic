# Database Migrations Guide

This project uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations. This allows you to make changes to the database structure without dropping and recreating the database.

## Overview

- **Migration files** are stored in `backend/alembic/versions/`
- **Configuration** is in `backend/alembic.ini` and `backend/alembic/env.py`
- **Helper script** `backend/migrate.py` provides convenient commands
- **Automatic migrations** run on application startup

## How It Works

1. When the application starts, it checks if the database has a migration version
2. If not (first time), it stamps the database with the initial migration (001)
3. It then runs any pending migrations automatically
4. Your database is now up to date!

## Creating a New Migration

When you need to change the database schema (add/remove columns, tables, etc.):

### Step 1: Update Your Models

First, make changes to your SQLAlchemy models in `backend/app/models/db.py`.

For example, to add a new column:
```python
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(120), unique=True, nullable=False)
    # ... existing columns ...
    
    # NEW COLUMN
    email = Column(String(255), nullable=True)  # Add this
```

### Step 2: Generate the Migration

Run the migration helper script to auto-generate a migration:

```bash
cd backend
python migrate.py create "add email column to users"
```

This will:
- Detect the changes you made to your models
- Generate a new migration file in `alembic/versions/`
- The file will contain `upgrade()` and `downgrade()` functions

### Step 3: Review the Migration

Open the generated migration file in `alembic/versions/` and review it:

```python
def upgrade() -> None:
    op.add_column('users', sa.Column('email', sa.String(length=255), nullable=True))

def downgrade() -> None:
    op.drop_column('users', 'email')
```

Make sure it looks correct!

### Step 4: Test Locally (Optional)

You can test the migration locally before deploying:

```bash
cd backend
python migrate.py upgrade
```

### Step 5: Deploy

Rebuild and restart your Docker containers:

```bash
docker-compose down
docker-compose up --build -d
```

The migration will run automatically on startup!

## Migration Commands

The `migrate.py` script provides these commands:

```bash
# Create a new migration (auto-generates based on model changes)
python migrate.py create "description of changes"

# Apply all pending migrations
python migrate.py upgrade

# Rollback the last migration
python migrate.py downgrade

# Show current migration version
python migrate.py current

# Show migration history
python migrate.py history

# Mark database as being at a specific version (without running migrations)
python migrate.py stamp <revision>
```

## Manual Migrations (Advanced)

If you need to write a migration manually (for data migrations, complex changes, etc.):

```bash
cd backend
alembic revision -m "description"
```

Then edit the generated file to add your custom SQL or Python code.

## Troubleshooting

### Migration fails on startup

If a migration fails, the application will fall back to the old `create_all()` method. Check the logs for details.

### Need to mark existing database

If you have an existing database that matches the current schema, you can stamp it:

```bash
cd backend
python migrate.py stamp head
```

### Reset migrations (DANGER - will lose data!)

If you need to completely reset (development only):

```bash
# Delete the database
rm -f backend/chips.db

# Restart the application - it will create a fresh database with all migrations applied
docker-compose restart backend
```

## Best Practices

1. **Always review** auto-generated migrations before applying them
2. **Test migrations** on a copy of production data before deploying
3. **Keep migrations small** - one logical change per migration
4. **Never edit** old migrations that have been applied to production
5. **Always provide** a `downgrade()` function for rollback capability
6. **Commit migrations** to version control along with model changes

## Migration File Naming

Migration files are automatically named with:
- A revision ID (e.g., `abc123def456`)
- Your description (e.g., `add_email_column_to_users`)

Example: `abc123def456_add_email_column_to_users.py`

## Backward Compatibility

The application still includes legacy manual migrations in `main.py` for backward compatibility. These will be no-ops if the columns already exist. New changes should use Alembic migrations instead.

