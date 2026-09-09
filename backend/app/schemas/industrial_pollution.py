from uuid import UUID

from app.schemas.base import BaseSchema


class IndustrialZoneResponse(BaseSchema):
    source_id: UUID
    source_name: str
    ward_id: str | None
    latitude: float
    longitude: float
    permit_status: str
    violation_count: int
    current_aqi: int | None
    current_risk: str
    historical_baseline_aqi: float | None
    deviation_level: str
    status: str
    possible_contributing_source: bool
    supporting_observations: list[str]
    # The nearest-station pollutant readings and ward-level industrial
    # attribution share were already being fetched by the endpoint (used
    # internally by assess_industrial_zone to compute current_risk /
    # supporting_observations) but were previously discarded instead of
    # being surfaced to the frontend. Exposing them here lets the UI show
    # real measured PM2.5/PM10/NO2 and a real attribution percentage
    # instead of leaving that data on the floor.
    pm25: float | None = None
    pm10: float | None = None
    no2: float | None = None
    industrial_attribution_pct: float | None = None
    # 0-1 model confidence for the ward-level attribution snapshot this
    # industrial_attribution_pct came from, matching the same
    # overall_confidence field the Pollution Sources page already surfaces
    # (see attribution.overall_confidence / SourcesPage's "Confidence"
    # column) — never a confidence value invented for this page.
    attribution_confidence: float | None = None
    nearest_station_name: str | None = None
    nearest_station_distance_km: float | None = None


class IndustrialPollutionReportResponse(BaseSchema):
    city: str
    zones: list[IndustrialZoneResponse]
    disclaimer: str = (
        "'Possible contributing source' is a flag for further investigation, not a "
        "confirmed finding — it requires both a measured deviation from the site's "
        "own historical baseline AND at least one independent regulatory or "
        "attribution signal. A compliant site with elevated AQI is not flagged as a "
        "source just because it happens to be industrial."
    )
