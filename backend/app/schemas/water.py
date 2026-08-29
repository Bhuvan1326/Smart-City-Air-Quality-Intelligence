from datetime import date, datetime
from uuid import UUID

from app.core.sanitization import sanitize_text
from app.schemas.base import BaseSchema
from pydantic import Field, field_validator


class WaterClimateResponse(BaseSchema):
    city: str
    latitude: float
    longitude: float

    precipitation_mm: float | None
    temperature_c: float | None
    relative_humidity_pct: float | None
    weather_observed_at: datetime | None
    weather_provider: str | None
    weather_available: bool

    reservoir_level_pct: float | None
    water_consumption_mld: float | None
    groundwater_level_m: float | None
    municipal_data_as_of: date | None
    municipal_data_available: bool

    flood_conducive_risk: str | None
    drought_risk: str | None
    water_stress: str | None

    rationale: list[str]
    methodology: str
    fetched_at: datetime


class CityWaterResourceCreate(BaseSchema):
    city: str = Field(..., min_length=1, max_length=100)
    reservoir_level_pct: float | None = Field(default=None, ge=0, le=100)
    water_consumption_mld: float | None = Field(default=None, ge=0, le=100_000)
    groundwater_level_m: float | None = Field(default=None, ge=0, le=1000)
    data_as_of: date | None = Field(default=None)
    source_note: str | None = Field(default=None, max_length=2000)

    @field_validator("city")
    @classmethod
    def sanitize_city(cls, v: str) -> str:
        return sanitize_text(v.strip())

    @field_validator("source_note")
    @classmethod
    def sanitize_note(cls, v: str | None) -> str | None:
        return sanitize_text(v) if v else v


class CityWaterResourceUpdate(BaseSchema):
    reservoir_level_pct: float | None = Field(default=None, ge=0, le=100)
    water_consumption_mld: float | None = Field(default=None, ge=0, le=100_000)
    groundwater_level_m: float | None = Field(default=None, ge=0, le=1000)
    data_as_of: date | None = Field(default=None)
    source_note: str | None = Field(default=None, max_length=2000)


class CityWaterResourceResponse(BaseSchema):
    id: UUID
    city: str
    reservoir_level_pct: float | None
    water_consumption_mld: float | None
    groundwater_level_m: float | None
    data_as_of: date | None
    source_note: str | None
    created_at: datetime
    updated_at: datetime
