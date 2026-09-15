"""users table for the portal authentication layer

Adds the ``users`` account table backing the SIH26082 UI login layer. Passwords
are scrypt-hashed with a per-user random salt (see ``backend/app/security.py``);
only ``password_salt`` + ``password_hash`` are persisted. SQLite dev databases
get the same table via ``Base.metadata.create_all`` at startup.

Revision ID: a1b2c3d4e5f6
Revises: f6a2e7b3c8d9
Create Date: 2026-09-15 10:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f6a2e7b3c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False, server_default='Analyst'),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('password_salt', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_id', 'users', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_id', table_name='users')
    op.drop_table('users')