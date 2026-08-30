"""India AQI Intelligence — query service layer.

Backs GET /api/v1/aqi/india and GET /api/v1/aqi/india/states. Thin
orchestration layer over the *existing* MonitoringStationRepository /
AQIReadingRepository — no new SQL beyond
`MonitoringStationRepository.search_by_geography`/`distinct_states`, and
reuses `AQIReadingRepository.get_latest_by_station` (already used by
GET /aqi/live) for the "latest reading per station" lookup.

Scope: this module *queries* whatever India-tagged station data exists in
the database. That's the existing Pune/Mumbai fixtures (country="India" —
see migration 019_monitoring_station_state_country) plus, once
`app.workers.tasks.aqi_ingestion.discover_and_ingest_india_locations` has
run, any OpenAQ-discovered India-wide stations it persisted. This module
has no ingestion logic of its own — it only ever reflects the database, so
coverage grows automatically as ingestion runs, never padded with
fabricated placeholder rows.

Known limitation (documented, not hidden): `category` and `source` filters
depend on each station's *latest reading*, which isn't a queryable column
on MonitoringStation. Pagination happens at the station-query level
(bounded, indexed, safe) and category/source filtering is applied to that
page's results afterward — so `total` reflects station-level filters
(country/state/city/bbox) only. Accurate today given the current dataset
size; revisit (e.g. denormalize latest-AQI/category onto the station row)
once India-wide ingestion makes the station count large enough to matter.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import MonitoringStation, QualityFlag
from app.repositories.aqi import AQIReadingRepository, MonitoringStationRepository
from app.schemas.aqi import (
    IndiaAQIObservationResponse,
    get_aqi_category,
    get_aqi_method,
    resolve_data_source,
)

INDIA_COUNTRY = "India"

VALID_AQI_CATEGORIES = {
    "good",
    "moderate",
    "unhealthy for sensitive groups",
    "unhealthy",
    "very unhealthy",
    "hazardous",
}

VALID_DATA_SOURCES = {"openaq", "synthetic"}


class InvalidIndiaAQIFilterError(ValueError):
    """Raised for a filter combination the endpoint should reject with a
    400, as opposed to an unexpected/internal error."""


@dataclass(frozen=True)
class IndiaAQIFilters:
    state: str | None = None
    city: str | None = None
    category: str | None = None
    source: str | None = None
    min_lat: float | None = None
    min_lon: float | None = None
    max_lat: float | None = None
    max_lon: float | None = None
    page: int = 1
    page_size: int = 50

    def __post_init__(self) -> None:
        if self.page < 1:
            raise InvalidIndiaAQIFilterError("page must be >= 1")
        if not (1 <= self.page_size <= 200):
            raise InvalidIndiaAQIFilterError("limit must be between 1 and 200")

        if (
            self.category is not None
            and self.category.lower() not in VALID_AQI_CATEGORIES
        ):
            raise InvalidIndiaAQIFilterError(
                f"Unknown category '{self.category}'. Valid values: "
                f"{sorted(VALID_AQI_CATEGORIES)}"
            )
        if self.source is not None and self.source.lower() not in VALID_DATA_SOURCES:
            raise InvalidIndiaAQIFilterError(
                f"Unknown source '{self.source}'. Valid values: "
                f"{sorted(VALID_DATA_SOURCES)}"
            )

        bbox_fields = (self.min_lat, self.min_lon, self.max_lat, self.max_lon)
        bbox_provided = [f is not None for f in bbox_fields]
        if any(bbox_provided) and not all(bbox_provided):
            raise InvalidIndiaAQIFilterError(
                "bbox requires all four of min_lat, min_lon, max_lat, max_lon"
            )
        if all(bbox_provided):
            if not (-90 <= self.min_lat <= 90) or not (-90 <= self.max_lat <= 90):
                raise InvalidIndiaAQIFilterError("Latitude must be between -90 and 90")
            if not (-180 <= self.min_lon <= 180) or not (-180 <= self.max_lon <= 180):
                raise InvalidIndiaAQIFilterError(
                    "Longitude must be between -180 and 180"
                )
            if self.min_lat > self.max_lat:
                raise InvalidIndiaAQIFilterError("min_lat must be <= max_lat")
            if self.min_lon > self.max_lon:
                raise InvalidIndiaAQIFilterError("min_lon must be <= max_lon")


async def _build_observation(
    station: MonitoringStation, reading
) -> IndiaAQIObservationResponse | None:
    if reading is None:
        return None

    category = get_aqi_category(reading.aqi)[0] if reading.aqi is not None else None

    return IndiaAQIObservationResponse(
        station_id=station.id,
        station_name=station.name,
        city=station.city,
        state=station.state,
        country=station.country,
        latitude=station.latitude,
        longitude=station.longitude,
        aqi=reading.aqi,
        aqi_category=category,
        aqi_method=get_aqi_method(reading.aqi, reading.pm25),
        pm25=reading.pm25,
        pm10=reading.pm10,
        no2=reading.no2,
        so2=reading.so2,
        co=reading.co,
        o3=reading.o3,
        observed_at=reading.timestamp,
        # AQIReading.created_at (TimestampMixin) is when this platform
        # persisted the reading — exactly "fetched_at". Reused rather than
        # adding a duplicate column.
        fetched_at=reading.created_at,
        data_source=resolve_data_source(reading.quality_flag),
        quality_flag=QualityFlag(reading.quality_flag),
    )


async def get_india_aqi_observations(
    session: AsyncSession, filters: IndiaAQIFilters
) -> tuple[list[IndiaAQIObservationResponse], int]:
    """Returns (observations, total) for the given filters.

    `total` counts stations matching the geography filters (country/state/
    city/bbox) — see the module docstring's "known limitation" note
    regarding category/source filtering happening after this count.
    """
    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)

    stations, total = await station_repo.search_by_geography(
        country=INDIA_COUNTRY,
        state=filters.state,
        city=filters.city,
        min_lat=filters.min_lat,
        min_lon=filters.min_lon,
        max_lat=filters.max_lat,
        max_lon=filters.max_lon,
        skip=(filters.page - 1) * filters.page_size,
        limit=filters.page_size,
    )

    observations: list[IndiaAQIObservationResponse] = []
    for station in stations:
        reading = await reading_repo.get_latest_by_station(station.id)
        obs = await _build_observation(station, reading)
        if obs is None:
            continue

        if filters.category is not None and (
            obs.aqi_category is None
            or obs.aqi_category.lower() != filters.category.lower()
        ):
            continue
        if (
            filters.source is not None
            and obs.data_source.lower() != filters.source.lower()
        ):
            continue

        observations.append(obs)

    return observations, total


async def get_india_states(session: AsyncSession) -> list[str]:
    """Distinct states actually present among India-tagged stations —
    backs GET /api/v1/aqi/india/states. Always the real database contents,
    never a static/invented list of India's states.
    """
    station_repo = MonitoringStationRepository(session)
    return await station_repo.distinct_states(country=INDIA_COUNTRY)
