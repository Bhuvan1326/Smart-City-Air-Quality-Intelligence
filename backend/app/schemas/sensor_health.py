from datetime import datetime
from uuid import UUID

from app.schemas.base import BaseSchema


class SensorHealthAssessmentResponse(BaseSchema):
    id: UUID
    station_id: UUID
    assessed_at: datetime
    drift_score: float
    drift_direction: str
    failure_probability: float
    maintenance_priority: str
    maintenance_priority_score: float
    remaining_useful_life_days: int | None
    confidence: float
    feature_importance: dict | None
    contributing_factors: list[str] | None
    reasoning_trace: list[str] | None
    alternative_explanations: list[str] | None
    historical_comparison: dict | None
    sample_size: int
    null_rate: float
    flatlined: bool
    out_of_range_rate: float


class StationHealthSummary(BaseSchema):
    station_id: UUID
    station_name: str
    ward_id: str | None
    maintenance_score: float
    latest_assessment: SensorHealthAssessmentResponse | None
