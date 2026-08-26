from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014_city_water_resources"
down_revision: Union[str, None] = "013_ward_waste_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "city_water_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("reservoir_level_pct", sa.Float(), nullable=True),
        sa.Column("water_consumption_mld", sa.Float(), nullable=True),
        sa.Column("groundwater_level_m", sa.Float(), nullable=True),
        sa.Column("data_as_of", sa.Date(), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
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
    op.create_index("ix_city_water_resources_city", "city_water_resources", ["city"])
    op.create_unique_constraint(
        "uq_city_water_resources_city", "city_water_resources", ["city"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_city_water_resources_city", "city_water_resources", type_="unique"
    )
    op.drop_index("ix_city_water_resources_city", table_name="city_water_resources")
    op.drop_table("city_water_resources")
