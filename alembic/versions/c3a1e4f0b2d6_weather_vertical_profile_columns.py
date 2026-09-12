"""Weather vertical profile columns

Adds the pressure-level atmospheric columns to ``weather_observations``
for the PostgreSQL deployment. The SQLite dev path already applies these
via ``apply_migrations()`` in ``backend/app/database.py``; this migration
keeps the PostgreSQL schema equivalent.

Columns (all additive, nullable):
  * temperature_1000hPa / 925 / 850 / 700hPa  (degC, standard levels)
  * geopotential_height_925hPa / 850hPa       (gpm, inversion-base reporting)

These feed lapse-rate inversion analysis (see ``ml/features/atmospheric_profile.py``
and ``docs/SIH_FINAL_COMPLIANCE.md`` R1/R2). NULL is meaningful: when vertical
data is absent the PBL-height proxy remains the fallback.

Revision ID: c3a1e4f0b2d6
Revises: d4a1e4c9f0b2
Create Date: 2026-09-12 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3a1e4f0b2d6'
down_revision: Union[str, None] = 'd4a1e4c9f0b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('weather_observations', sa.Column('temperature_1000hPa', sa.Float(), nullable=True))
    op.add_column('weather_observations', sa.Column('temperature_925hPa', sa.Float(), nullable=True))
    op.add_column('weather_observations', sa.Column('temperature_850hPa', sa.Float(), nullable=True))
    op.add_column('weather_observations', sa.Column('temperature_700hPa', sa.Float(), nullable=True))
    op.add_column('weather_observations', sa.Column('geopotential_height_925hPa', sa.Float(), nullable=True))
    op.add_column('weather_observations', sa.Column('geopotential_height_850hPa', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('weather_observations', 'geopotential_height_850hPa')
    op.drop_column('weather_observations', 'geopotential_height_925hPa')
    op.drop_column('weather_observations', 'temperature_700hPa')
    op.drop_column('weather_observations', 'temperature_850hPa')
    op.drop_column('weather_observations', 'temperature_925hPa')
    op.drop_column('weather_observations', 'temperature_1000hPa')