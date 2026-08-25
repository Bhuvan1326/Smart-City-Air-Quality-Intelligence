from app.schemas.base import BaseSchema


class GreenInfrastructureScoreResponse(BaseSchema):
    ward_id: str
    aqi: int | None
    pollution_risk: str
    exposure_level: str
    traffic_level: str
    green_cover_pct: float | None
    is_green_cover_configured: bool
    priority: str
    priority_score: int
    recommended_intervention: str
    rationale: list[str]


class GreenInfrastructureReportResponse(BaseSchema):
    city: str
    scores: list[GreenInfrastructureScoreResponse]
    methodology: str
    impact_disclaimer: str
    wards_missing_green_cover_data: list[str]
