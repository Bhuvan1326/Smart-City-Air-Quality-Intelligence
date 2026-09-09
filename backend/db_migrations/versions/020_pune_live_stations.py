from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020_pune_live_stations"
down_revision: str | None = "019_monitoring_station_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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

    bind = op.get_bind()
    has_timescaledb = bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")
        ).first()
    )
    compression_active = has_timescaledb and bool(
        bind.execute(
            sa.text(
                """
                SELECT 1
                FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'aqi_readings'
                  AND compression_enabled = true
                """
            )
        ).first()
    )

    if compression_active:
        op.execute("ALTER TABLE aqi_readings SET (timescaledb.compress = false)")

    op.create_index(
        "uq_aqi_readings_station_timestamp",
        "aqi_readings",
        ["station_id", "timestamp"],
        unique=True,
    )

    if compression_active:
        op.execute(
            """
            ALTER TABLE aqi_readings SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'station_id',
                timescaledb.compress_orderby = 'timestamp DESC'
            )
            """
        )


def downgrade() -> None:
    compression_active = bool(
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT 1
                FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'aqi_readings'
                  AND compression_enabled = true
                """
            )
        )
        .first()
    )

    if compression_active:
        op.execute("ALTER TABLE aqi_readings SET (timescaledb.compress = false)")

    op.drop_index("uq_aqi_readings_station_timestamp", table_name="aqi_readings")

    if compression_active:
        op.execute(
            """
            ALTER TABLE aqi_readings SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'station_id',
                timescaledb.compress_orderby = 'timestamp DESC'
            )
            """
        )

    op.drop_index("ix_stations_openaq_location_id", table_name="monitoring_stations")
    op.drop_column("monitoring_stations", "openaq_location_id")