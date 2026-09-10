from collections.abc import Sequence

from alembic import op

revision: str = "003_timescaledb_optimization"
down_revision: str | None = "002_phase_features"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS aqi_daily_by_station AS
        SELECT
            station_id,
            date_trunc('day', timestamp) AS day,
            AVG(aqi) AS avg_aqi,
            MAX(aqi) AS max_aqi,
            MIN(aqi) AS min_aqi,
            AVG(pm25) AS avg_pm25,
            AVG(pm10) AS avg_pm10,
            COUNT(*) AS reading_count
        FROM aqi_readings
        WHERE is_deleted = false
          AND quality_flag != 'invalid'
        GROUP BY station_id, date_trunc('day', timestamp)
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS aqi_daily_by_station")
