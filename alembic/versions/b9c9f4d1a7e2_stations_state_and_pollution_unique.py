"""stations.state + unique (station_id, timestamp) on pollution_readings

Phase 1 (official data.gov.in CPCB pipeline) adds:
  * stations.state                -- required station field
  * pollution_readings unique constraint on (station_id, timestamp)
    so the official ingestion endpoint cannot create duplicate rows.

Revision ID: b9c9f4d1a7e2
Revises: 0964e5b227e3
Create Date: 2026-09-09 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9c9f4d1a7e2'
down_revision: Union[str, None] = '0964e5b227e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('stations', sa.Column('state', sa.String(), nullable=True))
    # Pre-existing rows (from the earlier opencity.in pipeline) may contain
    # duplicate (station_id, timestamp) pairs; deduplicate before adding the
    # unique constraint so Postgres accepts it (keep the row with max id).
    op.execute(
        """
        DELETE FROM pollution_readings a
        USING pollution_readings b
        WHERE a.id < b.id
          AND a.station_id = b.station_id
          AND a.timestamp = b.timestamp
        """
    )
    op.create_unique_constraint(
        'uq_pollution_station_ts', 'pollution_readings', ['station_id', 'timestamp']
    )


def downgrade() -> None:
    op.drop_constraint('uq_pollution_station_ts', 'pollution_readings', type_='unique')
    op.drop_column('stations', 'state')