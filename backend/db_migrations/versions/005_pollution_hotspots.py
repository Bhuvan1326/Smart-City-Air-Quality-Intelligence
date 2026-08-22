from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "005_pollution_hotspots"
down_revision: Union[str, None] = "004_forecast_explainability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pollution_hotspots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column(
            "centroid", Geometry(geometry_type="POINT", srid=4326), nullable=False
        ),
        sa.Column("centroid_latitude", sa.Float(), nullable=False),
        sa.Column("centroid_longitude", sa.Float(), nullable=False),
        sa.Column("approx_radius_m", sa.Float(), nullable=False),
        sa.Column("avg_aqi", sa.Float(), nullable=False),
        sa.Column("peak_aqi", sa.Float(), nullable=False),
        sa.Column("dominant_pollutant", sa.String(20), nullable=True),
        sa.Column("point_count", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("aqi_category", sa.String(50), nullable=False),
        sa.Column("trend", sa.String(20), nullable=False, server_default="new"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
    op.create_index("ix_pollution_hotspots_city", "pollution_hotspots", ["city"])
    op.create_index(
        "ix_pollution_hotspots_detected_at", "pollution_hotspots", ["detected_at"]
    )
    op.create_index(
        "ix_pollution_hotspots_is_active", "pollution_hotspots", ["is_active"]
    )
    op.create_index(
        "ix_pollution_hotspots_centroid",
        "pollution_hotspots",
        ["centroid"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_pollution_hotspots_centroid", table_name="pollution_hotspots")
    op.drop_index("ix_pollution_hotspots_is_active", table_name="pollution_hotspots")
    op.drop_index("ix_pollution_hotspots_detected_at", table_name="pollution_hotspots")
    op.drop_index("ix_pollution_hotspots_city", table_name="pollution_hotspots")
    op.drop_table("pollution_hotspots")
