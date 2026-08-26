from datetime import date

from app.schemas.base import BaseSchema


class CircularityScoreResponse(BaseSchema):
    ward_id: str
    waste_generation_tons_per_day: float | None
    collection_efficiency_pct: float | None
    recycling_pct: float | None
    composting_pct: float | None
    landfill_pct: float | None
    recovery_rate_pct: float | None
    recovery_rate_includes_recycling: bool
    recovery_rate_includes_composting: bool
    landfill_dependency_pct: float | None
    circularity_score: float | None
    circularity_unavailable_reason: str | None
    data_as_of: date | None
    freshness_label: str
    is_data_configured: bool
    missing_fields: list[str]
    methodology: str


class WasteCircularityCityResponse(BaseSchema):
    city: str
    wards: list[CircularityScoreResponse]
    wards_with_no_data_on_file: list[str]
    methodology: str
