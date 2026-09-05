from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "003_timescaledb_optimization"
down_revision: Union[str, None] = "002_phase_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RETENTION_INTERVAL = "2 years"
COMPRESS_AFTER = "7 days"


def upgrade() -> None:

    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS aqi_daily_by_station
        WITH (timescaledb.continuous) AS
        SELECT
            station_id,
            time_bucket('1 day', timestamp) AS day,
            AVG(aqi) AS avg_aqi,
            MAX(aqi) AS max_aqi,
            MIN(aqi) AS min_aqi,
            AVG(pm25) AS avg_pm25,
            AVG(pm10) AS avg_pm10,
            COUNT(*) AS reading_count
        FROM aqi_readings
        WHERE is_deleted = false AND quality_flag != 'invalid'
        GROUP BY station_id, day
        WITH NO DATA
    """
    )

    op.execute(
        """
        SELECT add_continuous_aggregate_policy('aqi_daily_by_station',
            start_offset => INTERVAL '3 days',
            end_offset => INTERVAL '1 hour',
            schedule_interval => INTERVAL '30 minutes',
            if_not_exists => TRUE
        )
    """
    )

    op.execute(
        """
        ALTER TABLE aqi_readings SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'station_id',
            timescaledb.compress_orderby = 'timestamp DESC'
        )
    """
    )
    op.execute(
        f"""
        SELECT add_compression_policy('aqi_readings', INTERVAL '{COMPRESS_AFTER}', if_not_exists => TRUE)
    """
    )

    op.execute(
        """
        ALTER TABLE pollution_attributions SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'ward_id',
            timescaledb.compress_orderby = 'timestamp DESC'
        )
    """
    )
    op.execute(
        f"""
        SELECT add_compression_policy('pollution_attributions', INTERVAL '{COMPRESS_AFTER}', if_not_exists => TRUE)
    """
    )

    op.execute(
        f"""
        SELECT add_retention_policy('aqi_readings', INTERVAL '{RETENTION_INTERVAL}', if_not_exists => TRUE)
    """
    )


def downgrade() -> None:
    op.execute("SELECT remove_retention_policy('aqi_readings', if_exists => TRUE)")
    op.execute(
        "SELECT remove_compression_policy('pollution_attributions', if_exists => TRUE)"
    )
    op.execute("SELECT remove_compression_policy('aqi_readings', if_exists => TRUE)")
    op.execute("ALTER TABLE pollution_attributions SET (timescaledb.compress = false)")
    op.execute("ALTER TABLE aqi_readings SET (timescaledb.compress = false)")
    op.execute(
        "SELECT remove_continuous_aggregate_policy('aqi_daily_by_station', if_exists => TRUE)"
    )
    op.execute("DROP MATERIALIZED VIEW IF EXISTS aqi_daily_by_station")
