from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_weather_measurements"
down_revision: Union[str, None] = "006_traffic_observations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "weather_measurements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("humidity", sa.Float(), nullable=True),
        sa.Column("wind_speed", sa.Float(), nullable=True),
        sa.Column("wind_direction", sa.Float(), nullable=True),
        sa.Column("pressure", sa.Float(), nullable=True),
        sa.Column("precipitation", sa.Float(), nullable=True),
        sa.Column("weather_code", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="open_meteo"),
        sa.Column(
            "is_forecast", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint(
            "city", "observed_at", "source", name="uq_weather_city_time_source"
        ),
    )
    op.create_index("ix_weather_measurements_city", "weather_measurements", ["city"])
    op.create_index(
        "ix_weather_measurements_observed_at",
        "weather_measurements",
        ["observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_weather_measurements_observed_at", table_name="weather_measurements"
    )
    op.drop_index("ix_weather_measurements_city", table_name="weather_measurements")
    op.drop_table("weather_measurements")
