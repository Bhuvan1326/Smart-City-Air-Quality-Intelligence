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
