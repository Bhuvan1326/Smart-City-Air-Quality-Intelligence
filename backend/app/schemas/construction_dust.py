from datetime import datetime
from uuid import UUID

from app.schemas.base import BaseSchema


class ConstructionDustSiteResponse(BaseSchema):
    source_id: UUID
    source_name: str
    source_type: str
    ward_id: str | None
    latitude: float
    longitude: float
    permit_status: str
    violation_count: int
    last_inspected_at: datetime | None
    nearest_station_name: str | None
    nearest_station_distance_km: float | None
    pm10: float | None
    risk_level: str
    supporting_observations: list[str]
    requires_verification: bool = True


class ConstructionDustReportResponse(BaseSchema):
    city: str
    sites: list[ConstructionDustSiteResponse]
    disclaimer: str = (
        "Risk levels here are a heuristic combining PM10 readings, permit status, "
        "and violation history — not a confirmation that a specific site is the "
        "source of pollution. Sites flagged High or Moderate risk require "
        "on-site verification before any enforcement action."
    )
