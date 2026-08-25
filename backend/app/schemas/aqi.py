from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.monitoring import QualityFlag
from app.schemas.base import BaseSchema


class StationResponse(BaseSchema):
    id: UUID
    name: str
    station_code: str
    city: str
    ward_id: str | None
    operator: str
    latitude: float
    longitude: float
    is_active: bool
    station_type: str
    last_data_at: datetime | None
    maintenance_score: float


class AQIReadingResponse(BaseSchema):
    id: UUID
    station_id: UUID
    pm25: float | None
    pm10: float | None
    co: float | None
    no2: float | None
    so2: float | None
    o3: float | None
    aqi: int | None
    temperature: float | None
    humidity: float | None
    wind_speed: float | None
    wind_direction: float | None
    timestamp: datetime
    latitude: float
    longitude: float
    quality_flag: QualityFlag


class LiveAQIResponse(BaseSchema):
    station: StationResponse
    reading: AQIReadingResponse
    aqi_category: str
    health_message: str
    trend: str  # improving, stable, worsening
    data_source: str  # "openaq" (real) | "synthetic" (statistical fallback)


class AQIHistoryRequest(BaseSchema):
    station_id: UUID | None = None
    city: str | None = None
    ward_id: str | None = None
    start_time: datetime
    end_time: datetime
    interval: str = "1h"  # 15m, 1h, 6h, 24h


class PollutantRiskResponse(BaseSchema):
    pollutant: str
    label: str
    value: float
    unit: str
    risk_level: str
    reason: str


class HealthRiskResponse(BaseSchema):
    overall_risk: str
    aqi: int | None
    station_id: UUID | None
    ward_id: str | None
    pollutant_risks: list[PollutantRiskResponse]
    precautions: list[str]
    sensitive_group_note: str
    generated_at: datetime
    is_estimate: bool
    disclaimer: str = (
        "This is environmental/health-risk guidance derived from public air "
        "quality breakpoints. It is not a medical diagnosis. If you have "
        "symptoms or a pre-existing condition, consult a healthcare provider."
    )


class LocationRecommendationResponse(BaseSchema):
    rank: int
    station_id: UUID
    station_name: str
    ward_id: str | None
    latitude: float
    longitude: float
    distance_km: float
    aqi: int | None
    aqi_category: str | None
    freshness: str
    reason: str
    observed_at: datetime | None


class RouteSampleResponse(BaseSchema):
    sequence: int
    latitude: float
    longitude: float
    distance_from_origin_km: float
    nearest_station_name: str | None
    nearest_station_distance_km: float | None
    aqi: int | None
    aqi_category: str | None
    freshness: str
    observed_at: datetime | None


class RouteAnalysisResponse(BaseSchema):
    total_distance_km: float
    samples: list[RouteSampleResponse]
    average_aqi: float | None
    peak_aqi: int | None
    peak_sample_index: int | None
    overall_exposure: str
    high_pollution_segments: list[int]
    alternative_route_note: str
    routing_data_source: str
    data_disclaimer: str = (
        "The path shown is a straight-line estimate between your origin and "
        "destination for environmental sampling purposes, not turn-by-turn "
        "driving directions."
    )


class TrafficPeriodStatsResponse(BaseSchema):
    traffic_level: str
    reading_count: int
    avg_aqi: float | None
    avg_pm25: float | None
    avg_pm10: float | None
    avg_no2: float | None


class TrafficPollutionResponse(BaseSchema):
    city: str
    ward_id: str | None
    window_hours: int
    period_stats: list[TrafficPeriodStatsResponse]
    high_vs_low_aqi_ratio: float | None
    observation: str
    traffic_data_source: str
    traffic_data_note: str
    sample_size: int


class WaypointRequest(BaseSchema):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class RouteCandidateRequest(BaseSchema):
    name: str = Field(..., min_length=1, max_length=100)
    waypoints: list[WaypointRequest] = Field(..., min_length=2, max_length=50)
    duration_minutes: float | None = Field(default=None, ge=0, le=1440)


class CompareRoutesRequest(BaseSchema):
    city: str = Field(default="Pune")
    routes: list[RouteCandidateRequest] = Field(..., min_length=1, max_length=5)
    num_samples: int = Field(default=6, ge=2, le=20)


class RouteExposureResultResponse(BaseSchema):
    name: str
    total_distance_km: float
    duration_minutes: float | None
    estimated_aqi_exposure: float | None
    peak_aqi: float | None
    samples_used: int
    freshness_summary: str


class RouteComparisonResponse(BaseSchema):
    routes: list[RouteExposureResultResponse]
    recommended_route_name: str | None
    recommendation_text: str
    routing_data_source: str
    exposure_disclaimer: str


def get_aqi_category(aqi: int) -> tuple[str, str]:
    if aqi <= 50:
        return "Good", "Air quality is satisfactory"
    elif aqi <= 100:
        return "Moderate", "Acceptable air quality"
    elif aqi <= 150:
        return (
            "Unhealthy for Sensitive Groups",
            "Sensitive groups may experience health effects",
        )
    elif aqi <= 200:
        return "Unhealthy", "Everyone may experience health effects"
    elif aqi <= 300:
        return "Very Unhealthy", "Health alert: serious health effects possible"
    else:
        return "Hazardous", "Health emergency conditions"
