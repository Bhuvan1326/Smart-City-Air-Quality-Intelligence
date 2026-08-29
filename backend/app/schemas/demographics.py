from datetime import date, datetime
from uuid import UUID

from app.core.sanitization import sanitize_text
from app.schemas.base import BaseSchema
from pydantic import Field, field_validator


class WardDemographicsCreate(BaseSchema):
    city: str = Field(..., min_length=1, max_length=100)
    ward_id: str = Field(..., min_length=1, max_length=50)
    population: int | None = Field(default=None, ge=0, le=50_000_000)
    sensitive_sites_count: int | None = Field(default=None, ge=0, le=10_000)
    green_cover_pct: float | None = Field(default=None, ge=0, le=100)
    waste_generation_tons_per_day: float | None = Field(default=None, ge=0, le=100_000)
    waste_collection_efficiency_pct: float | None = Field(default=None, ge=0, le=100)
    waste_recycling_pct: float | None = Field(default=None, ge=0, le=100)
    waste_composting_pct: float | None = Field(default=None, ge=0, le=100)
    waste_landfill_pct: float | None = Field(default=None, ge=0, le=100)
    waste_data_as_of: date | None = Field(default=None)
    source_note: str | None = Field(default=None, max_length=2000)

    @field_validator("city", "ward_id")
    @classmethod
    def sanitize_fields(cls, v: str) -> str:
        return sanitize_text(v.strip())

    @field_validator("source_note")
    @classmethod
    def sanitize_note(cls, v: str | None) -> str | None:
        return sanitize_text(v) if v else v


class WardDemographicsUpdate(BaseSchema):
    population: int | None = Field(default=None, ge=0, le=50_000_000)
    sensitive_sites_count: int | None = Field(default=None, ge=0, le=10_000)
    green_cover_pct: float | None = Field(default=None, ge=0, le=100)
    waste_generation_tons_per_day: float | None = Field(default=None, ge=0, le=100_000)
    waste_collection_efficiency_pct: float | None = Field(default=None, ge=0, le=100)
    waste_recycling_pct: float | None = Field(default=None, ge=0, le=100)
    waste_composting_pct: float | None = Field(default=None, ge=0, le=100)
    waste_landfill_pct: float | None = Field(default=None, ge=0, le=100)
    waste_data_as_of: date | None = Field(default=None)
    source_note: str | None = Field(default=None, max_length=2000)


class WardDemographicsResponse(BaseSchema):
    id: UUID
    city: str
    ward_id: str
    population: int | None
    sensitive_sites_count: int | None
    green_cover_pct: float | None
    waste_generation_tons_per_day: float | None
    waste_collection_efficiency_pct: float | None
    waste_recycling_pct: float | None
    waste_composting_pct: float | None
    waste_landfill_pct: float | None
    waste_data_as_of: date | None
    source_note: str | None
    created_at: datetime
    updated_at: datetime


class ExposureScoreResponse(BaseSchema):
    ward_id: str
    aqi: int | None
    pollution_risk: str
    primary_pollutant: str | None
    population: int | None
    population_band: str | None
    sensitive_sites_count: int | None
    exposure_level: str
    is_population_data_configured: bool


class ExposureMapResponse(BaseSchema):
    city: str
    scores: list[ExposureScoreResponse]
    methodology: str
    wards_missing_population_data: list[str]
