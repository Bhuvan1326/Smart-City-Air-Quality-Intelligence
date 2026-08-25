from app.schemas.base import BaseSchema


class WasteBurningEventResponse(BaseSchema):
    ward_id: str | None
    station_name: str | None
    current_pm25: float | None
    baseline_pm25: float | None
    detected: str
    supporting_observations: list[str]
    confidence: str
    status: str
    circular_economy_recommendations: list[str]


class WasteBurningReportResponse(BaseSchema):
    city: str
    events: list[WasteBurningEventResponse]
    satellite_configured: bool
    disclaimer: str = (
        "Events here are never automatically confirmed as waste burning — each is a "
        "possible indicator requiring on-site or further verification. Confidence "
        "reflects how many independent signals (PM2.5 spike, known biomass site "
        "proximity, attribution model, satellite thermal detection) align."
    )
