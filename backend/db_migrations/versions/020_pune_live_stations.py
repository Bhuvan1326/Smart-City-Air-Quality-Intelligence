from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "020_pune_live_stations"
down_revision: Union[str, None] = "019_monitoring_station_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monitoring_stations",
        sa.Column("openaq_location_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_stations_openaq_location_id",
        "monitoring_stations",
        ["openaq_location_id"],
        unique=True,
        postgresql_where=sa.text("openaq_location_id IS NOT NULL"),
    )

    op.create_index(
        "uq_aqi_readings_station_timestamp",
        "aqi_readings",
        ["station_id", "timestamp"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_aqi_readings_station_timestamp", table_name="aqi_readings")
    op.drop_index("ix_stations_openaq_location_id", table_name="monitoring_stations")
    op.drop_column("monitoring_stations", "openaq_location_id")
