"""add pollution_observations.data_source provenance tag

Adds the optional ``data_source`` column on ``pollution_observations`` so the
17/17-station coverage audit can attribute every reading to the official source
that produced it (``data_gov_in | opencity_ckan | cpcb_dataset | cpcb_live``).
Legacy rows keep the value NULL, which the coverage report renders as
``legacy``. SQLite dev databases get the same additive column via
``apply_migrations()`` in ``backend/app/database.py``.

Revision ID: d3e5f7a4b8c2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-18 09:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'd3e5f7a4b8c2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pollution_observations', sa.Column('data_source', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('pollution_observations', 'data_source')