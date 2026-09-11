from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "024_pune_live_stale_since"
down_revision: str | None = "023_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Tracks how long a Pune Live station's cached `openaq_location_id`
    # has been failing to produce a current observation, so the
    # ingestion pipeline can decide when to search for a DIFFERENT,
    # currently-reporting OpenAQ location for that station instead of
    # polling a decommissioned/inactive one forever. See
    # app.workers.tasks.aqi_ingestion._try_reresolve_pune_station.
    op.add_column(
        "monitoring_stations",
        sa.Column(
            "openaq_location_stale_since", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("monitoring_stations", "openaq_location_stale_since")
