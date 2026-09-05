from datetime import datetime

from app.schemas.base import BaseSchema


class GreenInfrastructureScoreResponse(BaseSchema):
    # Identifies exactly which of the six real Pune stations (see
    # app.services.aqi_providers.pune_stations.REQUIRED_STATIONS) this
    # result is for. station_id is the MonitoringStation row's UUID (as a
    # string) once the station has been matched to a real OpenAQ location;
    # None if it hasn't been resolved yet — never a fabricated id.
    station_id: str | None
    station_code: str
    station_name: str
    operator: str | None
    # The place this result actually describes — currently the station's
    # own name, since the six real-time stations have no deterministic,
    # non-fabricated mapping to the platform's separate ward-fixture
    # geography (see app.models.demographics.WardDemographics, which is
    # keyed to the legacy W01-W08 CAAQMS fixtures, not these stations).
    # Exposing `area` (rather than silently reusing an unrelated ward id)
    # keeps this honest per requirement 4: never claim a station measures
    # a ward it isn't actually located in.
    area: str
    latitude: float | None
    longitude: float | None

    aqi: int | None
    pollution_risk: str | None
    exposure_level: str
    # "low" | "moderate" | "high", or null when no genuine live/configured
    # traffic reading exists for this station (see
    # app.services.traffic_provider — this platform has no live traffic
    # provider, only a labeled demo heuristic, which is never used here).
    traffic_level: str | None
    is_traffic_data_configured: bool
    green_cover_pct: float | None
    is_green_cover_configured: bool

    priority: str | None
    priority_score: int | None
    recommended_intervention: str | None
    rationale: list[str]

    # Provenance — mirrors the fields GET /aqi/live exposes, so the two
    # endpoints can be directly compared (see requirement 20).
    reading_timestamp: datetime | None
    data_source: str  # "OpenAQ" | "stale" | "unavailable"
    is_live: bool
    is_synthetic: bool
    # "ok" (fresh, genuine reading scored) | "stale" (reading exists but is
    # older than the freshness threshold) | "unavailable" (no station match
    # or no valid reading at all).
    status: str


class GreenInfrastructureReportResponse(BaseSchema):
    city: str
    scores: list[GreenInfrastructureScoreResponse]
    methodology: str
    impact_disclaimer: str
    stations_missing_green_cover_data: list[str]
    unavailable_stations: list[str]
