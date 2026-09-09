from datetime import date, datetime

from app.schemas.base import BaseSchema


class HeatAssessmentResponse(BaseSchema):
    """Urban heat-risk assessment with per-component provenance.

    air_temperature is a genuine LIVE reading (Open-Meteo, no key needed) —
    when the live call fails, every temperature/risk field is null and
    air_temperature_source_type is "unavailable"; no value is fabricated.
    mean_ndvi, when present, is a SATELLITE OBSERVATION with its own
    (non-real-time) observed date — never conflated with "live". heat_risk
    is CALCULATED from both — see methodology.
    """

    latitude: float
    longitude: float
    ward_id: str | None

    air_temperature_c: float | None
    air_temperature_source_type: str  # "live" | "unavailable"
    air_temperature_provider: str | None
    air_temperature_observed_at: datetime | None
    apparent_temperature_c: float | None
    relative_humidity_pct: float | None
    heat_index_c: float | None

    vegetation_data_available: bool
    mean_ndvi: float | None
    ndvi_source_type: str | None  # "satellite_observation" | None
    ndvi_observed_date: date | None

    heat_risk: str | None
    base_risk_from_temperature: str | None
    escalated_for_low_vegetation: bool
    heat_index_used_for_risk: bool
    cooling_priority: bool
    rationale: list[str]
    methodology: str

    fetched_at: datetime


class HeatHourlyPoint(BaseSchema):
    hour: str  # "2026-09-09T14:00"
    hour_label: str  # "2 PM"
    temperature_c: float
    apparent_temperature_c: float | None
    relative_humidity_pct: float | None
    heat_index_c: float | None
    heat_risk: str


class HeatHourlyResponse(BaseSchema):
    hours: list[HeatHourlyPoint]
    fetched_at: datetime


class HeatForecastDay(BaseSchema):
    date: str  # "2026-09-09"
    date_label: str  # "Tue Sep 09"
    max_temperature_c: float
    apparent_temperature_max_c: float | None
    mean_humidity_pct: float | None
    precipitation_mm: float | None
    heat_risk: str


class HeatForecastResponse(BaseSchema):
    days: list[HeatForecastDay]
    fetched_at: datetime


class WardHeatAssessment(BaseSchema):
    ward_id: str
    bbox: list[float]  # [min_lon, min_lat, max_lon, max_lat]
    center_lat: float
    center_lon: float
    temperature_c: float | None
    heat_risk: str | None
    mean_ndvi: float | None
    cooling_priority: bool


class WardHeatResponse(BaseSchema):
    wards: list[WardHeatAssessment]
    fetched_at: datetime


class HeatHistoryPoint(BaseSchema):
    recorded_at: datetime
    date_label: str  # "Sep 09"
    air_temperature_c: float
    heat_index_c: float | None
    relative_humidity_pct: float | None
    heat_risk: str
    cooling_priority: bool


class HeatHistoryResponse(BaseSchema):
    points: list[HeatHistoryPoint]
    city: str | None
    fetched_at: datetime
