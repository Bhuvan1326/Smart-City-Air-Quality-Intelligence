from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_phase_features"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "enforcement_actions",
        sa.Column(
            "evidence_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    op.create_table(
        "satellite_observations",
        sa.Column("ward_id", sa.String(length=50), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mean_ndvi", sa.Float(), nullable=True),
        sa.Column("mean_ndbi", sa.Float(), nullable=True),
        sa.Column("vegetation_loss_detected", sa.Boolean(), nullable=False),
        sa.Column("construction_activity_detected", sa.Boolean(), nullable=False),
        sa.Column("thermal_hotspot_count", sa.Integer(), nullable=False),
        sa.Column("biomass_burning_hotspots", sa.Integer(), nullable=False),
        sa.Column("industrial_thermal_hotspots", sa.Integer(), nullable=False),
        sa.Column("max_fire_radiative_power_mw", sa.Float(), nullable=True),
        sa.Column(
            "category_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
    op.create_index(
        op.f("ix_satellite_observations_city"),
        "satellite_observations",
        ["city"],
        unique=False,
    )
    op.create_index(
        op.f("ix_satellite_observations_observed_at"),
        "satellite_observations",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_satellite_observations_ward_id"),
        "satellite_observations",
        ["ward_id"],
        unique=False,
    )

    op.create_table(
        "drone_flight_plans",
        sa.Column("hotspot_id", sa.String(length=100), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("ward_id", sa.String(length=50), nullable=True),
        sa.Column("launch_latitude", sa.Float(), nullable=False),
        sa.Column("launch_longitude", sa.Float(), nullable=False),
        sa.Column("total_sorties", sa.Integer(), nullable=False),
        sa.Column("total_waypoints", sa.Integer(), nullable=False),
        sa.Column("total_distance_meters", sa.Float(), nullable=False),
        sa.Column("coverage_area_sq_meters", sa.Float(), nullable=False),
        sa.Column("excluded_no_fly_zones", sa.Integer(), nullable=False),
        sa.Column("reasoning", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("geojson", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_drone_flight_plans_city"), "drone_flight_plans", ["city"], unique=False
    )
    op.create_index(
        op.f("ix_drone_flight_plans_hotspot_id"),
        "drone_flight_plans",
        ["hotspot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_drone_flight_plans_ward_id"),
        "drone_flight_plans",
        ["ward_id"],
        unique=False,
    )

    op.create_table(
        "sensor_health_assessments",
        sa.Column("station_id", sa.UUID(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("drift_score", sa.Float(), nullable=False),
        sa.Column("drift_direction", sa.String(length=20), nullable=False),
        sa.Column("failure_probability", sa.Float(), nullable=False),
        sa.Column("maintenance_priority", sa.String(length=20), nullable=False),
        sa.Column("maintenance_priority_score", sa.Float(), nullable=False),
        sa.Column("remaining_useful_life_days", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "feature_importance", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "contributing_factors",
            postgresql.ARRAY(sa.String(length=100)),
            nullable=True,
        ),
        sa.Column("reasoning_trace", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "alternative_explanations", postgresql.ARRAY(sa.Text()), nullable=True
        ),
        sa.Column(
            "historical_comparison",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("null_rate", sa.Float(), nullable=False),
        sa.Column("flatlined", sa.Boolean(), nullable=False),
        sa.Column("out_of_range_rate", sa.Float(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(["station_id"], ["monitoring_stations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sensor_health_assessments_assessed_at"),
        "sensor_health_assessments",
        ["assessed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sensor_health_assessments_maintenance_priority"),
        "sensor_health_assessments",
        ["maintenance_priority"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sensor_health_assessments_station_id"),
        "sensor_health_assessments",
        ["station_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("sensor_health_assessments")
    op.drop_table("drone_flight_plans")
    op.drop_table("satellite_observations")
    op.drop_column("enforcement_actions", "evidence_metadata")
