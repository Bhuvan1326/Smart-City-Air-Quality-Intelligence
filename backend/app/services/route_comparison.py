"""Smart Mobility Intelligence — pollution-aware route comparison.

Extends app/services/route_analysis.py from single-route exposure sampling
to comparing 2+ named routes and recommending the one with lower estimated
exposure. Each route is defined by the caller as an ordered list of
waypoints (2 or more lat/lon points) — this endpoint never invents route
geometry. If the caller has real routing data (e.g. from a client-side
Mapbox Directions call), they can pass its actual coordinates and duration;
if not, a straight two-point waypoint list is used and the estimate is
labeled accordingly. Distance is always a genuine geometric calculation
over the given waypoints — never fabricated. Duration is only ever
reported if the caller supplies it; this module does not estimate travel
time, since that requires a real routing engine this platform doesn't have.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.monitoring import AQIReading, MonitoringStation, QualityFlag
from app.services.data_freshness import classify_freshness
from app.utils.geo import haversine_km


@dataclass
class Waypoint:
    latitude: float
    longitude: float


@dataclass
class RouteCandidate:
    name: str
    waypoints: list[Waypoint]
    duration_minutes: float | None = None


@dataclass
class RouteExposureResult:
    name: str
    total_distance_km: float
    duration_minutes: float | None
    estimated_aqi_exposure: float | None
    peak_aqi: float | None
    samples_used: int
    freshness_summary: str


@dataclass
class RouteComparisonResult:
    routes: list[RouteExposureResult]
    recommended_route_name: str | None
    recommendation_text: str
    routing_data_source: str = "caller_supplied_waypoints"
    exposure_disclaimer: str = (
        "AQI exposure values are estimates from the nearest monitoring station "
        "along each route's path, not a direct on-route sensor. Duration is only "
        "shown when supplied by the caller — no routing engine estimates travel "
        "time in this platform."
    )


def _cumulative_distances(waypoints: list[Waypoint]) -> tuple[float, list[float]]:
    cumulative = [0.0]
    total = 0.0
    for i in range(1, len(waypoints)):
        d = haversine_km(
            waypoints[i - 1].latitude,
            waypoints[i - 1].longitude,
            waypoints[i].latitude,
            waypoints[i].longitude,
        )
        total += d
        cumulative.append(total)
    return total, cumulative


def _interpolate_along_path(
    waypoints: list[Waypoint], target_km: float, cumulative: list[float]
) -> Waypoint:
    if len(waypoints) == 1 or target_km <= 0:
        return waypoints[0]
    for i in range(1, len(cumulative)):
        if target_km <= cumulative[i]:
            seg_start_km = cumulative[i - 1]
            seg_len = cumulative[i] - seg_start_km
            t = 0.0 if seg_len == 0 else (target_km - seg_start_km) / seg_len
            lat = (
                waypoints[i - 1].latitude
                + (waypoints[i].latitude - waypoints[i - 1].latitude) * t
            )
            lon = (
                waypoints[i - 1].longitude
                + (waypoints[i].longitude - waypoints[i - 1].longitude) * t
            )
            return Waypoint(latitude=lat, longitude=lon)
    return waypoints[-1]


def _sample_exposure(
    route: RouteCandidate,
    stations_with_readings: list[tuple[MonitoringStation, AQIReading]],
    num_samples: int,
) -> RouteExposureResult:
    total_km, cumulative = _cumulative_distances(route.waypoints)

    aqis: list[int] = []
    freshness_counts: dict[str, int] = {
        "live": 0,
        "recent": 0,
        "stale": 0,
        "demo": 0,
        "unavailable": 0,
    }

    n = max(2, num_samples)
    for i in range(n):
        t_km = total_km * (i / (n - 1)) if n > 1 else 0.0
        point = _interpolate_along_path(route.waypoints, t_km, cumulative)

        nearest_reading = None
        nearest_distance = None
        for station, reading in stations_with_readings:
            d = haversine_km(
                point.latitude, point.longitude, station.latitude, station.longitude
            )
            if nearest_distance is None or d < nearest_distance:
                nearest_distance = d
                nearest_reading = reading

        if nearest_reading is not None:
            is_synthetic = nearest_reading.quality_flag == QualityFlag.SYNTHETIC
            freshness = classify_freshness(
                nearest_reading.timestamp, is_synthetic=is_synthetic
            )
            freshness_counts[freshness.value] = (
                freshness_counts.get(freshness.value, 0) + 1
            )
            if nearest_reading.aqi is not None:
                aqis.append(nearest_reading.aqi)
        else:
            freshness_counts["unavailable"] += 1

    avg_aqi = round(sum(aqis) / len(aqis), 1) if aqis else None
    peak_aqi = max(aqis) if aqis else None
    freshness_summary = (
        ", ".join(f"{v} {k}" for k, v in freshness_counts.items() if v > 0) or "no data"
    )

    return RouteExposureResult(
        name=route.name,
        total_distance_km=round(total_km, 2),
        duration_minutes=route.duration_minutes,
        estimated_aqi_exposure=avg_aqi,
        peak_aqi=peak_aqi,
        samples_used=len(aqis),
        freshness_summary=freshness_summary,
    )


def compare_routes(
    routes: list[RouteCandidate],
    stations_with_readings: list[tuple[MonitoringStation, AQIReading]],
    num_samples: int = 6,
) -> RouteComparisonResult:
    results = [_sample_exposure(r, stations_with_readings, num_samples) for r in routes]

    scored = [r for r in results if r.estimated_aqi_exposure is not None]
    if not scored:
        return RouteComparisonResult(
            routes=results,
            recommended_route_name=None,
            recommendation_text="No AQI data available along any route to make a recommendation.",
        )

    best = min(scored, key=lambda r: r.estimated_aqi_exposure)
    if len(scored) == 1:
        recommendation_text = f"{best.name} is the only route with AQI data available."
    else:
        others = [r for r in scored if r.name != best.name]
        comparisons = ", ".join(
            f"{o.estimated_aqi_exposure} for {o.name}" for o in others
        )
        recommendation_text = (
            f"{best.name} has the lowest estimated pollution exposure "
            f"({best.estimated_aqi_exposure} AQI vs {comparisons})."
        )

    return RouteComparisonResult(
        routes=results,
        recommended_route_name=best.name,
        recommendation_text=recommendation_text,
    )
