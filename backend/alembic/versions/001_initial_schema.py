"""initial schema

Revision ID: 001
Revises: 
Create Date: 2026-01-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tables table
    op.create_table('tables',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('seats_count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create users table
    op.create_table('users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('table_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('hourly_rate', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['table_id'], ['tables.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=False)

    # Create sessions table
    op.create_table('sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('table_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('dealer_id', sa.Integer(), nullable=True),
        sa.Column('waiter_id', sa.Integer(), nullable=True),
        sa.Column('chips_in_play', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['dealer_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['table_id'], ['tables.id'], ),
        sa.ForeignKeyConstraint(['waiter_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sessions_created_at'), 'sessions', ['created_at'], unique=False)
    op.create_index(op.f('ix_sessions_date'), 'sessions', ['date'], unique=False)
    op.create_index(op.f('ix_sessions_dealer_id'), 'sessions', ['dealer_id'], unique=False)
    op.create_index(op.f('ix_sessions_status'), 'sessions', ['status'], unique=False)
    op.create_index(op.f('ix_sessions_table_id'), 'sessions', ['table_id'], unique=False)
    op.create_index(op.f('ix_sessions_waiter_id'), 'sessions', ['waiter_id'], unique=False)

    # Create seats table
    op.create_table('seats',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('seat_no', sa.Integer(), nullable=False),
        sa.Column('player_name', sa.String(length=255), nullable=True),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'seat_no', name='uq_seat_session_seatno')
    )
    op.create_index('ix_seat_session_seat', 'seats', ['session_id', 'seat_no'], unique=False)
    op.create_index(op.f('ix_seats_session_id'), 'seats', ['session_id'], unique=False)

    # Create chip_ops table
    op.create_table('chip_ops',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('seat_no', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chip_ops_session_id'), 'chip_ops', ['session_id'], unique=False)

    # Create chip_purchases table
    op.create_table('chip_purchases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('table_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('seat_no', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('chip_op_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.Column('payment_type', sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(['chip_op_id'], ['chip_ops.id'], ),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
        sa.ForeignKeyConstraint(['table_id'], ['tables.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chip_op_id', name='uq_chip_purchases_chip_op_id')
    )
    op.create_index(op.f('ix_chip_purchases_chip_op_id'), 'chip_purchases', ['chip_op_id'], unique=False)
    op.create_index(op.f('ix_chip_purchases_created_at'), 'chip_purchases', ['created_at'], unique=False)
    op.create_index(op.f('ix_chip_purchases_created_by_user_id'), 'chip_purchases', ['created_by_user_id'], unique=False)
    op.create_index(op.f('ix_chip_purchases_seat_no'), 'chip_purchases', ['seat_no'], unique=False)
    op.create_index(op.f('ix_chip_purchases_session_id'), 'chip_purchases', ['session_id'], unique=False)
    op.create_index(op.f('ix_chip_purchases_table_id'), 'chip_purchases', ['table_id'], unique=False)

    # Create casino_balance_adjustments table
    op.create_table('casino_balance_adjustments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_casino_balance_adjustments_created_at'), 'casino_balance_adjustments', ['created_at'], unique=False)
    op.create_index(op.f('ix_casino_balance_adjustments_created_by_user_id'), 'casino_balance_adjustments', ['created_by_user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('casino_balance_adjustments')
    op.drop_table('chip_purchases')
    op.drop_table('chip_ops')
    op.drop_table('seats')
    op.drop_table('sessions')
    op.drop_table('users')
    op.drop_table('tables')

