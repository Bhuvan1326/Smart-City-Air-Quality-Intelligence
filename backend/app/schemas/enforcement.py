from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.core.sanitization import sanitize_text
from app.models.emission_source import EmissionSourceType
from app.models.enforcement import (ActionStatus, ActionType, AlertChannel,
                                    AlertRiskLevel)
from app.schemas.base import BaseSchema


class ForecastResponse(BaseSchema):
    id: UUID
    city: str
    ward_id: str | None
    forecast_timestamp: datetime
    generated_at: datetime
    aqi_forecast: int
    pm25_forecast: float | None
    confidence_score: float
    confidence_lower: int | None
    confidence_upper: int | None
    model_version: str
    contributing_factors: dict | None
    feature_importance: dict | None
    aqi_category: str


class WardForecastSummary(BaseSchema):
    ward_id: str
    city: str
    current_aqi: int
    forecasts: list[ForecastResponse]
    peak_aqi: int
    peak_at: datetime
    trend: str


class EnforcementActionCreate(BaseSchema):
    source_id: UUID | None = None
    ward_id: str | None = None
    city: str
    action_type: ActionType
    title: str
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    priority_score: float = Field(default=0.0, ge=0.0, le=100.0)

    @field_validator("title")
    @classmethod
    def _sanitize_title(cls, v: str) -> str:
        return sanitize_text(v, max_length=500, field_name="title")

    @field_validator("description")
    @classmethod
    def _sanitize_description(cls, v: str | None) -> str | None:
        return sanitize_text(v, max_length=5000, field_name="description") if v else v


class EvidenceSubmissionRequest(BaseSchema):
    """
    Submitted by the officer PWA's offline inspection form (see
    frontend lib/offline/sync-manager.ts). `client_id` is generated on the
    device when the form is first completed (works offline) and is used as
    an idempotency key: if the same client_id is submitted twice — e.g. the
    background sync retried after a response was lost — it updates the
    same evidence record instead of creating a duplicate.
    """

    client_id: str = Field(max_length=100)
    status: ActionStatus
    notes: str | None = None
    outcome_score: float | None = Field(default=None, ge=0.0, le=100.0)
    photos: list[str] = Field(default_factory=list, max_length=10)
    latitude: float | None = None
    longitude: float | None = None
    captured_at: datetime

    @field_validator("notes")
    @classmethod
    def _sanitize_notes(cls, v: str | None) -> str | None:
        return sanitize_text(v, max_length=5000, field_name="notes") if v else v


class EvidenceSubmissionResponse(BaseSchema):
    action_id: UUID
    client_id: str
    status: ActionStatus
    evidence_urls: list[str]
    photos_saved: int
    was_duplicate: bool


class EnforcementActionUpdate(BaseSchema):
    status: ActionStatus | None = None
    notes: str | None = None
    outcome_score: float | None = None
    evidence_urls: list[str] | None = None

    @field_validator("notes")
    @classmethod
    def _sanitize_notes(cls, v: str | None) -> str | None:
        return sanitize_text(v, max_length=5000, field_name="notes") if v else v


class EnforcementActionResponse(BaseSchema):
    id: UUID
    officer_id: UUID
    source_id: UUID | None
    ward_id: str | None
    city: str
    action_type: ActionType
    status: ActionStatus
    priority_score: float
    title: str
    description: str | None
    notes: str | None
    evidence_urls: list[str] | None
    latitude: float | None
    longitude: float | None
    outcome_score: float | None
    resolved_at: datetime | None
    ai_reasoning: dict | None
    created_at: datetime


class CitizenAlertCreate(BaseSchema):
    ward_id: str
    city: str
    language: str = "en"
    channel: AlertChannel = AlertChannel.PUSH
    risk_level: AlertRiskLevel
    aqi_value: int | None = None
    vulnerability_groups: list[str] | None = None


class CitizenAlertResponse(BaseSchema):
    id: UUID
    ward_id: str
    city: str
    language: str
    channel: AlertChannel
    risk_level: AlertRiskLevel
    message_title: str
    message_text: str
    aqi_value: int | None
    sent_at: datetime | None
    delivery_status: str
    created_at: datetime


class AttributionResponse(BaseSchema):
    ward_id: str
    city: str
    timestamp: datetime
    vehicular_pct: float
    industrial_pct: float
    construction_pct: float
    biomass_pct: float
    secondary_aerosol_pct: float
    dust_pct: float
    domestic_pct: float
    overall_confidence: float
    contributing_sources: dict | None
    model_version: str


class EmissionSourceResponse(BaseSchema):
    id: UUID
    name: str
    source_type: EmissionSourceType
    city: str
    ward_id: str | None
    latitude: float
    longitude: float
    permit_status: str
    last_inspected_at: datetime | None
    violation_count: int
    operator_name: str | None
    is_active: bool


class DashboardOverview(BaseSchema):
    city: str
    timestamp: datetime
    active_stations: int
    avg_aqi: float
    max_aqi: int
    max_aqi_ward: str | None
    unhealthy_wards: int
    active_alerts: int
    pending_enforcements: int
    anomalies_today: int
    aqi_trend_24h: float  # delta from 24h ago
    top_pollutant: str
    air_quality_index_summary: dict[str, int]  # category -> count of wards
