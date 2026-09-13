"""weather_observations unique (station_id, timestamp)

Adds a unique constraint on weather_observations so duplicate weather rows
cannot be inserted (dedup-logic guard): the pre-insert dedup was comparing
timezone-aware PostgreSQL datetimes against naive-UTC source timestamps and
never matched, so duplicates accumulated. Existing rows are deduplicated
before the constraint is added. SQLite dev DBs receive the same dedup +
unique index via ``apply_migrations()`` in ``backend/app/database.py``.

Revision ID: f6a2e7b3c8d9
Revises: e2b1c3d4a5f7
Create Date: 2026-09-13 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a2e7b3c8d9'
down_revision: Union[str, None] = 'e2b1c3d4a5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep the row with the max id for each (station_id, timestamp) so the
    # unique constraint can be created cleanly.
    op.execute(
        """
        DELETE FROM weather_observations a
        USING weather_observations b
        WHERE a.id < b.id
          AND a.station_id = b.station_id
          AND a.timestamp = b.timestamp
        """
    )
    op.create_unique_constraint(
        'uq_weather_station_ts', 'weather_observations', ['station_id', 'timestamp']
    )


def downgrade() -> None:
    op.drop_constraint('uq_weather_station_ts', 'weather_observations', type_='unique')