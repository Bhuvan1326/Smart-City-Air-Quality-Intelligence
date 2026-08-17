from datetime import datetime
from uuid import UUID

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
