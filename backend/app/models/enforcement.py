import uuid
from datetime import datetime
from enum import Enum

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ActionType(str, Enum):
    INSPECTION = "inspection"
    NOTICE = "notice"
    SHUTDOWN = "shutdown"
    FINE = "fine"
    WARNING = "warning"
    SEAL = "seal"


class ActionStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"


class EnforcementAction(BaseModel):
    __tablename__ = "enforcement_actions"

    officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emission_sources.id"), nullable=True, index=True
    )
    ward_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action_type: Mapped[ActionType] = mapped_column(String(30), nullable=False)
    status: Mapped[ActionStatus] = mapped_column(
        String(30), default=ActionStatus.PENDING, nullable=False, index=True
    )
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_urls: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)
    geospatial_doc: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    geometry: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_reasoning: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evidence_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    officer: Mapped["User"] = relationship(
        "User", back_populates="enforcement_actions", foreign_keys=[officer_id]
    )
    source: Mapped["EmissionSource | None"] = relationship(
        "EmissionSource", back_populates="enforcement_actions"
    )
    outcome: Mapped["InterventionOutcome | None"] = relationship(
        "InterventionOutcome", back_populates="action", uselist=False
    )


class ForecastGrid(BaseModel):
    __tablename__ = "forecast_grids"

    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ward_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    grid_geometry: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=False
    )
    forecast_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    aqi_forecast: Mapped[int] = mapped_column(Integer, nullable=False)
    pm25_forecast: Mapped[float | None] = mapped_column(Float, nullable=True)
    pm10_forecast: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_lower: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_upper: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    contributing_factors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    feature_importance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class AlertRiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"
    SEVERE = "severe"


class AlertChannel(str, Enum):
    PUSH = "push"
    IVR = "ivr"
    DISPLAY = "display"
    SMS = "sms"
    EMAIL = "email"


class CitizenAlert(BaseModel):
    __tablename__ = "citizen_alerts"

    ward_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    channel: Mapped[AlertChannel] = mapped_column(
        String(20), nullable=False, default=AlertChannel.PUSH
    )
    risk_level: Mapped[AlertRiskLevel] = mapped_column(String(20), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    message_title: Mapped[str] = mapped_column(String(500), nullable=False)
    vulnerability_groups_targeted: Mapped[list | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    aqi_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )
    delivery_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_generated: Mapped[bool] = mapped_column(default=True, nullable=False)


class InterventionOutcome(BaseModel):
    __tablename__ = "intervention_outcomes"

    action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enforcement_actions.id"),
        nullable=False,
        unique=True,
    )
    aqi_before: Mapped[float] = mapped_column(Float, nullable=False)
    aqi_after: Mapped[float] = mapped_column(Float, nullable=False)
    delta_score: Mapped[float] = mapped_column(Float, nullable=False)
    pm25_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    pm25_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_period_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    verification_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    carbon_saved_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)

    action: Mapped["EnforcementAction"] = relationship(
        "EnforcementAction", back_populates="outcome"
    )


class DroneFlightPlan(BaseModel):
    """Persisted output of app.services.drone_planner.DronePlanner, for a given hotspot."""

    __tablename__ = "drone_flight_plans"

    hotspot_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ward_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    launch_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    launch_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    total_sorties: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_waypoints: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_distance_meters: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    coverage_area_sq_meters: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    excluded_no_fly_zones: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    reasoning: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)
    geojson: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="planned", nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
