"""Add heat_readings table for Urban Heat Intelligence history.

Revision ID: 022_heat_readings
Revises: 021_water_resource_history
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_heat_readings"
down_revision: Union[str, None] = "021_water_resource_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "heat_readings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("ward_id", sa.String(length=20), nullable=True),
        sa.Column("air_temperature_c", sa.Float(), nullable=False),
        sa.Column("apparent_temperature_c", sa.Float(), nullable=True),
        sa.Column("relative_humidity_pct", sa.Float(), nullable=True),
        sa.Column("heat_index_c", sa.Float(), nullable=True),
        sa.Column("heat_risk", sa.String(length=20), nullable=False),
        sa.Column("mean_ndvi", sa.Float(), nullable=True),
        sa.Column("cooling_priority", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_heat_readings_recorded_at", "heat_readings", ["recorded_at"])
    op.create_index("ix_heat_readings_city", "heat_readings", ["city"])


def downgrade() -> None:
    op.drop_index("ix_heat_readings_city", table_name="heat_readings")
    op.drop_index("ix_heat_readings_recorded_at", table_name="heat_readings")
    op.drop_table("heat_readings")
