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
    # India AQI Intelligence: added alongside MonitoringStation.state/
    # country. Optional defaults keep this backward compatible with any
    # existing caller of StationResponse.
    state: str | None = None
    country: str = "India"
    openaq_location_id: int | None = None


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
    # Present once the station has been matched to a real OpenAQ location
    # (has real coordinates/id). None only for a required station that
    # could not be resolved at all yet — see `unresolved` below; in that
    # case `station_name`/`provider` still identify which required
    # station this is, without inventing coordinates for it.
    station: StationResponse | None = None
    station_code: str
    station_name: str
    provider: str | None = None
    reading: AQIReadingResponse | None = None
    aqi_category: str | None = None
    health_message: str | None = None
    trend: str | None = None  # improving, stable, worsening
    # "openaq" (real) | "synthetic" (statistical fallback) | "unavailable"
    # (no current OpenAQ observation — no reading exists at all, never a
    # fabricated one).
    data_source: str
    # Shared live/recent/stale/demo/unavailable classification (see
    # app/services/data_freshness.py) — the frontend badge on each station
    # card. "Live" here always means the observation itself is recent
    # enough, never merely that the API request succeeded.
    freshness: str = "unavailable"
    # Only meaningful for the six-station real-time Pune Live AQI view:
    # True if this station could not be matched to a real OpenAQ location
    # at all (as opposed to being matched but currently reporting no
    # observation). Other callers of this schema always get False.
    unresolved: bool = False


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
    estimated_co2_kg: float | None
    traffic_level: str | None
    traffic_data_source: str | None


class RouteComparisonResponse(BaseSchema):
    routes: list[RouteExposureResultResponse]
    recommended_route_name: str | None
    recommendation_text: str
    routing_data_source: str
    exposure_disclaimer: str
    lowest_co2_route_name: str | None
    fastest_route_name: str | None
    balanced_route_name: str | None
    co2_disclaimer: str
    traffic_disclaimer: str
    category_note: str


class IndiaAQIObservationResponse(BaseSchema):
    """One monitoring station's latest AQI observation, for
    GET /api/v1/aqi/india. Deliberately flat (rather than the nested
    StationResponse + AQIReadingResponse shape LiveAQIResponse uses) to
    match the field-per-observation shape a map/heatmap consumer needs —
    every value is sourced from those same existing models, not a new
    data source.
    """

    station_id: UUID
    station_name: str
    city: str
    state: str | None
    country: str
    latitude: float
    longitude: float
    aqi: int | None
    aqi_category: str | None
    aqi_method: str | None
    pm25: float | None
    pm10: float | None
    no2: float | None
    so2: float | None
    co: float | None
    o3: float | None
    observed_at: datetime
    fetched_at: datetime
    data_source: str
    quality_flag: QualityFlag


def resolve_data_source(quality_flag: QualityFlag | str) -> str:
    """ "openaq" (real) vs "synthetic" (statistical fallback), derived from
    quality_flag exactly as GET /aqi/live computes it inline — shared
    implementation both endpoints use.
    """
    return "synthetic" if quality_flag == QualityFlag.SYNTHETIC else "openaq"


def get_aqi_method(aqi: int | None, pm25: float | None) -> str | None:
    """The AQI methodology behind `AQIReading.aqi`.

    Every reading in this system has its `aqi` computed by the same
    function, app.workers.tasks.aqi_ingestion._calculate_aqi_from_pm25,
    using Indian NAAQS PM2.5 breakpoints — so this always returns that
    label when an AQI value computed from PM2.5 is present, "unknown" if
    an AQI exists without a PM2.5 value to attribute it to, and None when
    there's no AQI at all.
    """
    if aqi is None:
        return None
    if pm25 is None:
        return "unknown"
    return "CPCB_PM25_NAAQS_INTERPOLATED"


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
