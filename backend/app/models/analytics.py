import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from app.models.base import BaseModel
from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.monitoring import MonitoringStation
    from app.models.user import User


class AnomalyEvent(BaseModel):
    __tablename__ = "anomaly_events"

    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_stations.id"),
        nullable=False,
        index=True,
    )
    ward_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    aqi_spike_value: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_aqi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    probable_cause: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cause_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_resolved: Mapped[bool] = mapped_column(default=False, nullable=False)
    root_cause_timeline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    contributing_sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    geometry: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )

    station: Mapped["MonitoringStation"] = relationship(
        "MonitoringStation", back_populates="anomaly_events"
    )


class OfficerRoute(BaseModel):
    __tablename__ = "officer_routes"

    officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    waypoints: Mapped[dict] = mapped_column(JSONB, nullable=False)
    route_geometry: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326), nullable=True
    )
    optimisation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hotspot_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    traffic_considered: Mapped[bool] = mapped_column(default=True, nullable=False)

    officer: Mapped["User"] = relationship("User", back_populates="routes")


class PolicySnapshot(BaseModel):
    __tablename__ = "policy_snapshots"

    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    policy_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    implemented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    impact_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    comparable_city_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    aqi_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    pm25_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class PollutionAttribution(BaseModel):
    __tablename__ = "pollution_attributions"

    ward_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    vehicular_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    industrial_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    construction_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    biomass_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    secondary_aerosol_pct: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    dust_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    domestic_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    overall_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    contributing_sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    satellite_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    geometry: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=True
    )


class AuditLog(BaseModel):
    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User | None"] = relationship("User", back_populates="audit_logs")


class SatelliteObservation(BaseModel):
    """
    One fetch cycle's worth of satellite-derived indicators for a ward,
    produced by app.workers.tasks.satellite.fetch_satellite_features and
    consumed by the attribution task (app.workers.tasks.attribution) to
    build the satellite_evidence payload on PollutionAttribution records.
    """

    __tablename__ = "satellite_observations"

    ward_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    mean_ndvi: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_ndbi: Mapped[float | None] = mapped_column(Float, nullable=True)
    vegetation_loss_detected: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )
    construction_activity_detected: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )
    thermal_hotspot_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    biomass_burning_hotspots: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    industrial_thermal_hotspots: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    max_fire_radiative_power_mw: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    category_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
