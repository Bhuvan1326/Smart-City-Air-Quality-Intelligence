from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_hypertable(table_name: str) -> None:
    assert table_name.isidentifier(), f"unsafe table_name for raw SQL: {table_name!r}"
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_extension
                    WHERE extname = 'timescaledb'
                ) THEN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM timescaledb_information.hypertables
                        WHERE hypertable_schema = current_schema()
                          AND hypertable_name = '{table_name}'
                    ) THEN
                        PERFORM public.create_hypertable(
                            CAST('{table_name}' AS regclass),
                            CAST('timestamp' AS name),
                            if_not_exists => TRUE
                        );
                    END IF;
                END IF;
            END
            $$;
            """
        )
    )


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("ward_id", sa.String(50), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preferred_language", sa.String(10), nullable=False, default="en"),
        sa.Column("push_token", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # monitoring_stations
    op.create_table(
        "monitoring_stations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("station_code", sa.String(50), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=True),
        sa.Column("operator", sa.String(255), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "geometry", Geometry(geometry_type="POINT", srid=4326), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elevation_m", sa.Float(), nullable=True),
        sa.Column("station_type", sa.String(50), nullable=False, default="CAAQMS"),
        sa.Column("data_source_url", sa.Text(), nullable=True),
        sa.Column("last_data_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("maintenance_score", sa.Float(), nullable=False, default=1.0),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )
    op.create_index("ix_stations_city", "monitoring_stations", ["city"])
    op.create_index(
        "ix_stations_code", "monitoring_stations", ["station_code"], unique=True
    )
    op.execute(
        "CREATE INDEX ix_stations_geom ON monitoring_stations USING GIST (geometry)"
    )

    # aqi_readings — will be a TimescaleDB hypertable
    op.create_table(
        "aqi_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "station_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("monitoring_stations.id"),
            nullable=False,
        ),
        sa.Column("pm25", sa.Float(), nullable=True),
        sa.Column("pm10", sa.Float(), nullable=True),
        sa.Column("co", sa.Float(), nullable=True),
        sa.Column("no2", sa.Float(), nullable=True),
        sa.Column("so2", sa.Float(), nullable=True),
        sa.Column("o3", sa.Float(), nullable=True),
        sa.Column("aqi", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("humidity", sa.Float(), nullable=True),
        sa.Column("wind_speed", sa.Float(), nullable=True),
        sa.Column("wind_direction", sa.Float(), nullable=True),
        sa.Column("pressure", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", "timestamp"),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("quality_flag", sa.String(20), nullable=False, default="good"),
        sa.Column("raw_data", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )
    op.create_index("ix_aqi_station_time", "aqi_readings", ["station_id", "timestamp"])
    _create_hypertable("aqi_readings")

    # emission_sources
    op.create_table(
        "emission_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column(
            "geometry", Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False
        ),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("permit_status", sa.String(20), nullable=False, default="none"),
        sa.Column("permit_number", sa.String(100), nullable=True),
        sa.Column("permit_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_inspected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("violation_count", sa.Integer(), nullable=False, default=0),
        sa.Column("operator_name", sa.String(255), nullable=True),
        sa.Column("operator_contact", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("stack_height_m", sa.Float(), nullable=True),
        sa.Column("emission_rate_kg_hr", sa.Float(), nullable=True),
        sa.Column("carbon_estimate_ton_yr", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )
    op.execute(
        "CREATE INDEX ix_emission_geom ON emission_sources USING GIST (geometry)"
    )

    # enforcement_actions
    op.create_table(
        "enforcement_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "officer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("emission_sources.id"),
            nullable=True,
        ),
        sa.Column("ward_id", sa.String(50), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, default="pending"),
        sa.Column("priority_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("evidence_urls", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("geospatial_doc", postgresql.JSONB(), nullable=True),
        sa.Column(
            "geometry", Geometry(geometry_type="POINT", srid=4326), nullable=True
        ),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("outcome_score", sa.Float(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("ai_reasoning", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )

    # forecast_grids
    op.create_table(
        "forecast_grids",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=True),
        sa.Column(
            "grid_geometry",
            Geometry(geometry_type="POLYGON", srid=4326),
            nullable=False,
        ),
        sa.Column("forecast_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aqi_forecast", sa.Integer(), nullable=False),
        sa.Column("pm25_forecast", sa.Float(), nullable=True),
        sa.Column("pm10_forecast", sa.Float(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("confidence_lower", sa.Integer(), nullable=True),
        sa.Column("confidence_upper", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("contributing_factors", postgresql.JSONB(), nullable=True),
        sa.Column("feature_importance", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )
    op.execute(
        "CREATE INDEX ix_forecast_geom ON forecast_grids USING GIST (grid_geometry)"
    )
    op.create_index(
        "ix_forecast_city_time", "forecast_grids", ["city", "forecast_timestamp"]
    )

    # citizen_alerts
    op.create_table(
        "citizen_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ward_id", sa.String(50), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("message_title", sa.String(500), nullable=False),
        sa.Column(
            "vulnerability_groups_targeted", postgresql.ARRAY(sa.Text()), nullable=True
        ),
        sa.Column("aqi_value", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_status", sa.String(30), nullable=False, default="pending"),
        sa.Column("delivery_count", sa.Integer(), nullable=False, default=0),
        sa.Column("ai_generated", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )

    # intervention_outcomes
    op.create_table(
        "intervention_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enforcement_actions.id"),
            nullable=False,
        ),
        sa.Column("aqi_before", sa.Float(), nullable=False),
        sa.Column("aqi_after", sa.Float(), nullable=False),
        sa.Column("delta_score", sa.Float(), nullable=False),
        sa.Column("pm25_before", sa.Float(), nullable=True),
        sa.Column("pm25_after", sa.Float(), nullable=True),
        sa.Column("measurement_period_hours", sa.Integer(), nullable=False),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verification_method", sa.String(100), nullable=True),
        sa.Column("carbon_saved_kg", sa.Float(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False, default=0.8),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )

    # anomaly_events
    op.create_table(
        "anomaly_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "station_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("monitoring_stations.id"),
            nullable=False,
        ),
        sa.Column("ward_id", sa.String(50), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aqi_spike_value", sa.Integer(), nullable=False),
        sa.Column("baseline_aqi", sa.Integer(), nullable=True),
        sa.Column("probable_cause", sa.String(255), nullable=True),
        sa.Column("cause_category", sa.String(100), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, default=False),
        sa.Column("root_cause_timeline", postgresql.JSONB(), nullable=True),
        sa.Column("contributing_sources", postgresql.JSONB(), nullable=True),
        sa.Column(
            "geometry", Geometry(geometry_type="POINT", srid=4326), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )

    # officer_routes
    op.create_table(
        "officer_routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "officer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("waypoints", postgresql.JSONB(), nullable=False),
        sa.Column(
            "route_geometry",
            Geometry(geometry_type="LINESTRING", srid=4326),
            nullable=True,
        ),
        sa.Column("optimisation_score", sa.Float(), nullable=True),
        sa.Column("total_distance_km", sa.Float(), nullable=True),
        sa.Column("estimated_duration_min", sa.Integer(), nullable=True),
        sa.Column("hotspot_count", sa.Integer(), nullable=False, default=0),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("traffic_considered", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )

    # policy_snapshots
    op.create_table(
        "policy_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("policy_type", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("impact_score", sa.Float(), nullable=True),
        sa.Column("comparable_city_ref", sa.String(100), nullable=True),
        sa.Column("aqi_delta", sa.Float(), nullable=True),
        sa.Column("pm25_delta", sa.Float(), nullable=True),
        sa.Column("measurement_days", sa.Integer(), nullable=False, default=30),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )

    # pollution_attributions
    op.create_table(
        "pollution_attributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "timestamp"),
        sa.Column("vehicular_pct", sa.Float(), nullable=False, default=0.0),
        sa.Column("industrial_pct", sa.Float(), nullable=False, default=0.0),
        sa.Column("construction_pct", sa.Float(), nullable=False, default=0.0),
        sa.Column("biomass_pct", sa.Float(), nullable=False, default=0.0),
        sa.Column("secondary_aerosol_pct", sa.Float(), nullable=False, default=0.0),
        sa.Column("dust_pct", sa.Float(), nullable=False, default=0.0),
        sa.Column("domestic_pct", sa.Float(), nullable=False, default=0.0),
        sa.Column("overall_confidence", sa.Float(), nullable=False),
        sa.Column("contributing_sources", postgresql.JSONB(), nullable=True),
        sa.Column("satellite_evidence", postgresql.JSONB(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column(
            "geometry", Geometry(geometry_type="POLYGON", srid=4326), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )
    _create_hypertable("pollution_attributions")

    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("request_data", postgresql.JSONB(), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("pollution_attributions")
    op.drop_table("policy_snapshots")
    op.drop_table("officer_routes")
    op.drop_table("anomaly_events")
    op.drop_table("intervention_outcomes")
    op.drop_table("citizen_alerts")
    op.drop_table("forecast_grids")
    op.drop_table("enforcement_actions")
    op.drop_table("emission_sources")
    op.drop_table("aqi_readings")
    op.drop_table("monitoring_stations")
    op.drop_table("users")
