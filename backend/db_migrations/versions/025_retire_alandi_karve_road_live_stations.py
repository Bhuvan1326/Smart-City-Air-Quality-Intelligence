from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "025_retire_alandi_karve_road"
down_revision: str | None = "024_pune_live_stale_since"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RETIRED_STATION_CODES = ("PUNE_LIVE_ALANDI", "PUNE_LIVE_KARVE_ROAD")
RETIRED_OPENAQ_LOCATION_IDS = (12042, 5661)


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE monitoring_stations
            SET is_active = false
            WHERE is_active = true
              AND (
                station_code IN :codes
                OR openaq_location_id IN :location_ids
              )
            """
        ).bindparams(
            sa.bindparam("codes", expanding=True, value=RETIRED_STATION_CODES),
            sa.bindparam(
                "location_ids", expanding=True, value=RETIRED_OPENAQ_LOCATION_IDS
            ),
        )
    )


def downgrade() -> None:
    pass
