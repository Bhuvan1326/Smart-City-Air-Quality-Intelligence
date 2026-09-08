"""Allow multiple dated water-resource readings per city for trend charting.

Drops the unique constraint on city_water_resources.city so admins can log
periodic reservoir/consumption/groundwater snapshots. The API layer now
returns the most-recent row when a single current value is needed, and the
new /water/history endpoint returns the full ordered series for charting.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "021_water_resource_history"
down_revision: Union[str, None] = "020_pune_live_stations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_city_water_resources_city",
        "city_water_resources",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_city_water_resources_city",
        "city_water_resources",
        ["city"],
    )
