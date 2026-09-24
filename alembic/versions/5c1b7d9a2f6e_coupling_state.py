"""add coupling_states table (SIH26082 Phase 30 persistence)

Adds the ``coupling_states`` table that stores the latest coupling-engine
snapshot per station: the nine coupling features, key atmospheric inputs,
inversion and fire-transport fields, provenance timestamps and the
``coupling_state`` / ``coupling_domains`` / ``data_quality`` labels. One row
per station (UNIQUE station_id), refreshed write-through every time the
coupling features are computed. SQLite dev databases get the table via the
unconditional ``Base.metadata.create_all`` at startup.

Revision ID: 5c1b7d9a2f6e
Revises: d3e5f7a4b8c2
Create Date: 2026-09-24 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '5c1b7d9a2f6e'
down_revision: Union[str, None] = 'd3e5f7a4b8c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'coupling_states',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('station_id', sa.Integer(), sa.ForeignKey('stations.id'), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('wind_speed_mps', sa.Float(), nullable=True),
        sa.Column('wind_direction_deg', sa.Float(), nullable=True),
        sa.Column('pbl_height_m', sa.Float(), nullable=True),
        sa.Column('inversion_detected', sa.Boolean(), nullable=True),
        sa.Column('inversion_strength', sa.Float(), nullable=True),
        sa.Column('inversion_category', sa.String(), nullable=True),
        sa.Column('inversion_source', sa.String(), nullable=True),
        sa.Column('fire_count', sa.Integer(), nullable=True),
        sa.Column('upwind_fire_count', sa.Integer(), nullable=True),
        sa.Column('nearest_fire_distance_km', sa.Float(), nullable=True),
        sa.Column('fire_impact_score', sa.Float(), nullable=True),
        sa.Column('wind_alignment_pct', sa.Float(), nullable=True),
        sa.Column('fire_transport_direction', sa.String(), nullable=True),
        sa.Column('fire_transport_time_hours', sa.Float(), nullable=True),
        sa.Column('fire_transport_influence', sa.Float(), nullable=True),
        sa.Column('dispersion_potential', sa.Float(), nullable=True),
        sa.Column('accumulation_potential', sa.Float(), nullable=True),
        sa.Column('inversion_trapping_potential', sa.Float(), nullable=True),
        sa.Column('pollution_stagnation_index', sa.Float(), nullable=True),
        sa.Column('aerosol_accumulation_potential', sa.Float(), nullable=True),
        sa.Column('regional_transport_potential', sa.Float(), nullable=True),
        sa.Column('ozone_photochemical_potential', sa.Float(), nullable=True),
        sa.Column('meteorology_pollution_interaction', sa.Float(), nullable=True),
        sa.Column('coupling_state', sa.String(), nullable=True),
        sa.Column('coupling_domains', sa.String(), nullable=True),
        sa.Column('data_quality', sa.String(), nullable=True),
        sa.Column('weather_reading_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pollution_reading_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('station_id', name='uq_coupling_state_station'),
    )
    op.create_index('ix_coupling_states_id', 'coupling_states', ['id'])
    op.create_index('ix_coupling_states_station_id', 'coupling_states', ['station_id'])


def downgrade() -> None:
    op.drop_index('ix_coupling_states_station_id', table_name='coupling_states')
    op.drop_index('ix_coupling_states_id', table_name='coupling_states')
    op.drop_table('coupling_states')