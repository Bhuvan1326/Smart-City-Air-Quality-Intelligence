"""Route environmental analysis.

Important scope note: this project has no turn-by-turn routing/directions
engine integrated on the backend (no Mapbox Directions API call, no OSRM).
So "the route" sampled here is a straight-line (great-circle) interpolation
between origin and destination — useful as an environmental-exposure
estimate, but NOT real driving directions. The response is explicit about
this so the frontend never presents it as an actual road route.

For an actual alternative route, a real routing engine would be required;
this module does not fabricate one — see `alternative_route_note` in the
result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.models.monitoring import AQIReading, MonitoringStation, QualityFlag
from app.services.data_freshness import FreshnessStatus, classify_freshness
from app.utils.geo import haversine_km


@dataclass
class RouteSample:
    sequence: int
    latitude: float
    longitude: float
    distance_from_origin_km: float
    nearest_station_name: str | None
    nearest_station_distance_km: float | None
    aqi: int | None
    freshness: FreshnessStatus
    observed_at: datetime | None


@dataclass
class RouteAnalysisResult:
    total_distance_km: float
    samples: list[RouteSample]
    average_aqi: float | None
    peak_aqi: int | None
    peak_sample_index: int | None
    overall_exposure: str  # low / moderate / high / very_high / unknown
    high_pollution_segments: list[int] = field(default_factory=list)
    alternative_route_note: str = (
        "No routing/directions engine is integrated in this deployment, so "
        "a reliable alternative route cannot be calculated here. This "
        "analysis only estimates exposure along the direct path between "
        "your origin and destination."
    )
    routing_data_source: str = "straight_line_estimate"


def _interpolate(lat1: float, lon1: float, lat2: float, lon2: float, t: float) -> tuple[float, float]:
    """Linear interpolation between two points at fraction t (0..1).

    This is a simple planar interpolation, adequate for the short urban
    distances this platform covers — it is not geodesic routing.
    """
    return (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)


_AQI_EXPOSURE_BANDS = [(50, "low"), (150, "moderate"), (250, "high"), (float("inf"), "very_high")]


def _exposure_band(aqi: float) -> str:
    for upper, label in _AQI_EXPOSURE_BANDS:
        if aqi <= upper:
            return label
    return "very_high"


def analyze_route(
    *,
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    stations_with_readings: list[tuple[MonitoringStation, AQIReading]],
    num_samples: int = 6,
) -> RouteAnalysisResult:
    total_distance = haversine_km(origin_lat, origin_lon, dest_lat, dest_lon)

    samples: list[RouteSample] = []
    for i in range(num_samples):
        t = i / (num_samples - 1) if num_samples > 1 else 0.0
        lat, lon = _interpolate(origin_lat, origin_lon, dest_lat, dest_lon, t)

        nearest_station = None
        nearest_distance = None
        nearest_reading = None
        for station, reading in stations_with_readings:
            d = haversine_km(lat, lon, station.latitude, station.longitude)
            if nearest_distance is None or d < nearest_distance:
                nearest_distance = d
                nearest_station = station
                nearest_reading = reading

        aqi = nearest_reading.aqi if nearest_reading else None
        is_synthetic = (
            nearest_reading is not None
            and nearest_reading.quality_flag == QualityFlag.SYNTHETIC
        )
        freshness = (
            classify_freshness(nearest_reading.timestamp, is_synthetic=is_synthetic)
            if nearest_reading is not None
            else FreshnessStatus.UNAVAILABLE
        )

        samples.append(
            RouteSample(
                sequence=i,
                latitude=lat,
                longitude=lon,
                distance_from_origin_km=total_distance * t,
                nearest_station_name=nearest_station.name if nearest_station else None,
                nearest_station_distance_km=round(nearest_distance, 2) if nearest_distance is not None else None,
                aqi=aqi,
                freshness=freshness,
                observed_at=nearest_reading.timestamp if nearest_reading else None,
            )
        )

    known_aqis = [s.aqi for s in samples if s.aqi is not None]
    average_aqi = sum(known_aqis) / len(known_aqis) if known_aqis else None
    peak_aqi = max(known_aqis) if known_aqis else None
    peak_index = None
    if peak_aqi is not None:
        peak_index = next(s.sequence for s in samples if s.aqi == peak_aqi)

    overall_exposure = _exposure_band(average_aqi) if average_aqi is not None else "unknown"

    # A segment is "high pollution" if its AQI is materially worse than the
    # route average (or simply unhealthy in absolute terms) — this flags
    # localized hotspots rather than judging the whole route by one point.
    high_segments = [
        s.sequence
        for s in samples
        if s.aqi is not None and (s.aqi >= 200 or (average_aqi is not None and s.aqi >= average_aqi * 1.4))
    ]

    return RouteAnalysisResult(
        total_distance_km=round(total_distance, 2),
        samples=samples,
        average_aqi=round(average_aqi, 1) if average_aqi is not None else None,
        peak_aqi=peak_aqi,
        peak_sample_index=peak_index,
        overall_exposure=overall_exposure,
        high_pollution_segments=high_segments,
    )
