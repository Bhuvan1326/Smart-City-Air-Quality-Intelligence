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

    vegetation_data_available: bool
    mean_ndvi: float | None
    ndvi_source_type: str | None  # "satellite_observation" | None
    ndvi_observed_date: date | None

    heat_risk: str | None
    base_risk_from_temperature: str | None
    escalated_for_low_vegetation: bool
    cooling_priority: bool
    rationale: list[str]
    methodology: str

    fetched_at: datetime


class HeatWardAssessmentResponse(BaseSchema):
    ward_id: str
    ward_name: str
    latitude: float
    longitude: float

    air_temperature_c: float | None
    air_temperature_source_type: str
    air_temperature_provider: str | None
    air_temperature_observed_at: datetime | None
    apparent_temperature_c: float | None

    vegetation_data_available: bool
    mean_ndvi: float | None
    ndvi_source_type: str | None
    ndvi_observed_date: date | None

    heat_risk: str | None
    cooling_priority: bool


class HeatWardMapResponse(BaseSchema):
    city: str
    wards: list[HeatWardAssessmentResponse]
    methodology: str
    fetched_at: datetime
