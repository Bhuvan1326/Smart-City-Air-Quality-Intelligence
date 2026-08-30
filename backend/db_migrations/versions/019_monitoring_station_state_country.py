"""Add state/country to monitoring_stations (India AQI Intelligence).

Backend foundation for the new India-level AQI feature. The platform was
originally Pune/Mumbai-only and `monitoring_stations` had no notion of
state or country — only `city`/`ward_id`. This migration adds both without
touching or renaming any existing column.

country:
    NOT NULL, server_default 'India'. Every station this platform has ever
    ingested (existing Pune/Mumbai fixtures, and anything planned for
    India-wide ingestion) is Indian, so backfilling existing rows with
    'India' is not a guess — it accurately reflects the data. The server
    default is kept (not dropped after backfill) so any future INSERT that
    doesn't explicitly set `country` still defaults correctly, matching the
    ORM-level default in app/models/monitoring.py.

state:
    Nullable, NO default. Unlike country, a station's state is not reliably
    derivable in general (e.g. for stations discovered generically from a
    provider), and per the India AQI Intelligence requirements we do not
    fabricate it. Existing rows are simply backfilled to NULL here; the
    application layer separately sets state="Maharashtra" for the existing
    Pune/Mumbai station fixtures where it is genuinely known (see
    app/workers/tasks/aqi_ingestion.py), which is ordinary data, not a
    schema-migration concern.

Indexes: both columns are added as filterable dimensions for the new
GET /api/v1/aqi/india endpoint (state/city/country filters), so both get a
plain btree index, consistent with the existing `ix_stations_city` index on
this table. `country` has low selectivity today (effectively constant), but
the column exists specifically to support other countries later, so the
index is cheap groundwork rather than premature optimization on today's
data.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_monitoring_station_state_country"
down_revision: Union[str, None] = "018_widen_ward_assignment_method"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monitoring_stations",
        sa.Column(
            "country",
            sa.String(length=100),
            nullable=False,
            server_default="India",
        ),
    )
    op.add_column(
        "monitoring_stations",
        sa.Column("state", sa.String(length=100), nullable=True),
    )

    op.create_index("ix_stations_country", "monitoring_stations", ["country"])
    op.create_index("ix_stations_state", "monitoring_stations", ["state"])


def downgrade() -> None:
    op.drop_index("ix_stations_state", table_name="monitoring_stations")
    op.drop_index("ix_stations_country", table_name="monitoring_stations")
    op.drop_column("monitoring_stations", "state")
    op.drop_column("monitoring_stations", "country")
