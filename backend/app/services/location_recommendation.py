"""Location recommendation — ranks nearby monitoring stations by air quality.

Reuses the existing GIS nearest-neighbour lookup (app.gis.operations) and
AQI repository rather than introducing a new data source. No environmental
measurement is fabricated: if a station has no recent reading it is
excluded, and any reading sourced from the synthetic fallback (see
QualityFlag.SYNTHETIC) is labeled as demo data rather than presented as
live.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.monitoring import AQIReading, MonitoringStation, QualityFlag
from app.services.data_freshness import FreshnessStatus, classify_freshness
from app.utils.geo import haversine_km


@dataclass
class LocationRecommendation:
    station: MonitoringStation
    reading: AQIReading
    distance_km: float
    aqi: int | None
    freshness: FreshnessStatus
    reason: str
    rank: int


def _build_reason(
    aqi: int | None, distance_km: float, freshness: FreshnessStatus
) -> str:
    parts = []
    if aqi is not None:
        if aqi <= 50:
            parts.append(f"Air quality here is good (AQI {aqi})")
        elif aqi <= 100:
            parts.append(f"Air quality here is moderate (AQI {aqi})")
        else:
            parts.append(f"Air quality here is AQI {aqi}")
    else:
        parts.append("No current AQI reading")

    parts.append(f"{distance_km:.1f} km away")

    if freshness == FreshnessStatus.DEMO:
        parts.append("demo data")
    elif freshness == FreshnessStatus.STALE:
        parts.append("data may be outdated")

    return " · ".join(parts)


def rank_locations(
    candidates: list[tuple[MonitoringStation, AQIReading]],
    *,
    origin_lat: float,
    origin_lon: float,
    limit: int = 5,
) -> list[LocationRecommendation]:
    """Rank stations for "find a cleaner place nearby" style recommendations.

    Ranking favors lower AQI first, using distance as a tiebreaker so two
    similarly-clean locations don't recommend a far-away one over a nearby
    one. Readings with no AQI value are ranked last (never fabricated).
    """
    scored: list[LocationRecommendation] = []
    for station, reading in candidates:
        distance_km = haversine_km(
            origin_lat, origin_lon, station.latitude, station.longitude
        )
        is_synthetic = reading.quality_flag == QualityFlag.SYNTHETIC
        freshness = classify_freshness(reading.timestamp, is_synthetic=is_synthetic)
        scored.append(
            LocationRecommendation(
                station=station,
                reading=reading,
                distance_km=distance_km,
                aqi=reading.aqi,
                freshness=freshness,
                reason=_build_reason(reading.aqi, distance_km, freshness),
                rank=0,
            )
        )

    def sort_key(item: LocationRecommendation):
        # None AQI sorts last; otherwise ascending AQI, then ascending distance.
        aqi_key = item.aqi if item.aqi is not None else 10_000
        return (aqi_key, item.distance_km)

    scored.sort(key=sort_key)
    for i, item in enumerate(scored[:limit], start=1):
        item.rank = i
    return scored[:limit]
