from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_traffic_observations"
down_revision: Union[str, None] = "005_pollution_hotspots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "traffic_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("road_name", sa.String(255), nullable=True),
        sa.Column("traffic_level", sa.Float(), nullable=False),
        sa.Column("congestion_category", sa.String(20), nullable=False),
        sa.Column("vehicle_count", sa.Integer(), nullable=True),
        sa.Column("data_source", sa.String(100), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index("ix_traffic_observations_city", "traffic_observations", ["city"])
    op.create_index(
        "ix_traffic_observations_ward_id", "traffic_observations", ["ward_id"]
    )
    op.create_index(
        "ix_traffic_observations_observed_at",
        "traffic_observations",
        ["observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_traffic_observations_observed_at", table_name="traffic_observations"
    )
    op.drop_index("ix_traffic_observations_ward_id", table_name="traffic_observations")
    op.drop_index("ix_traffic_observations_city", table_name="traffic_observations")
    op.drop_table("traffic_observations")
