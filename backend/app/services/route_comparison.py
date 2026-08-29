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

Low-Emission Mobility (Feature 4): each route also gets an ESTIMATED CO2
figure (distance x the same documented vehicular emission factor already
used in app.services.carbon_estimator — reused, not duplicated) and a
traffic-level label from app.services.traffic_provider (also reused). Per
that module's own honesty rules, traffic here is NEVER "live" — it is a
demo/CSV-sourced estimate, and that is stated explicitly in the output
rather than implied. compare_routes() then reports, alongside the existing
lowest-exposure ("cleanest") pick, which route has the lowest estimated
CO2 and (only when duration was supplied) which is fastest and which is
the best balanced compromise — never fabricating a category it can't
support with the data it has.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.models.monitoring import AQIReading, MonitoringStation, QualityFlag
from app.services.carbon_estimator import EMISSION_FACTOR_SOURCE, EMISSION_FACTORS
from app.services.data_freshness import classify_freshness
from app.services.traffic_provider import get_traffic_reading
from app.utils.geo import haversine_km

# Simplified, documented congestion adjustment applied to the base
# per-km emission factor: low-speed/stop-start driving in heavier traffic
# burns more fuel per km than free-flowing traffic. This is a coarse
# heuristic (not a physically calibrated model) — always labeled ESTIMATED.
_CONGESTION_CO2_MULTIPLIER = {
    "low": 1.0,
    "moderate": 1.1,
    "high": 1.3,
}


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
    estimated_co2_kg: float | None = None
    traffic_level: str | None = None
    traffic_data_source: str | None = None


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
    lowest_co2_route_name: str | None = None
    fastest_route_name: str | None = None
    balanced_route_name: str | None = None
    co2_disclaimer: str = (
        f"CO2 is ESTIMATED as distance x a documented per-km vehicular emission "
        f"factor ({EMISSION_FACTOR_SOURCE}), adjusted by a simplified traffic-"
        f"congestion multiplier — not a measured tailpipe value."
    )
    traffic_disclaimer: str = (
        "No live traffic provider is configured for this deployment (see "
        "app/services/traffic_provider.py) — traffic levels here are a "
        "time-of-day model or CSV reference, never a real-time feed."
    )
    category_note: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self.category_note:
            self.category_note = (
                "Categories are only reported when the underlying data supports "
                "them: 'cleanest' requires AQI exposure data, 'lowest CO2' "
                "requires distance, 'fastest' requires caller-supplied duration "
                "for every route being compared."
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

    traffic_reading = get_traffic_reading(datetime.now(UTC))
    congestion_multiplier = _CONGESTION_CO2_MULTIPLIER.get(
        traffic_reading.level.value, 1.0
    )
    co2_per_km = EMISSION_FACTORS["vehicular"]["co2_per_vehicle_km"]
    estimated_co2_kg = round(total_km * co2_per_km * congestion_multiplier, 3)

    return RouteExposureResult(
        name=route.name,
        total_distance_km=round(total_km, 2),
        duration_minutes=route.duration_minutes,
        estimated_aqi_exposure=avg_aqi,
        peak_aqi=peak_aqi,
        samples_used=len(aqis),
        freshness_summary=freshness_summary,
        estimated_co2_kg=estimated_co2_kg,
        traffic_level=traffic_reading.level.value,
        traffic_data_source=traffic_reading.source.value,
    )


def compare_routes(
    routes: list[RouteCandidate],
    stations_with_readings: list[tuple[MonitoringStation, AQIReading]],
    num_samples: int = 6,
) -> RouteComparisonResult:
    results = [_sample_exposure(r, stations_with_readings, num_samples) for r in routes]

    scored = [r for r in results if r.estimated_aqi_exposure is not None]
    if not scored:
        recommended_route_name = None
        recommendation_text = (
            "No AQI data available along any route to make a recommendation."
        )
    else:
        best = min(scored, key=lambda r: r.estimated_aqi_exposure)
        recommended_route_name = best.name
        if len(scored) == 1:
            recommendation_text = (
                f"{best.name} is the only route with AQI data available."
            )
        else:
            others = [r for r in scored if r.name != best.name]
            comparisons = ", ".join(
                f"{o.estimated_aqi_exposure} for {o.name}" for o in others
            )
            recommendation_text = (
                f"{best.name} has the lowest estimated pollution exposure "
                f"({best.estimated_aqi_exposure} AQI vs {comparisons})."
            )

    co2_scored = [r for r in results if r.estimated_co2_kg is not None]
    lowest_co2_route_name = (
        min(co2_scored, key=lambda r: r.estimated_co2_kg).name if co2_scored else None
    )

    duration_scored = [r for r in results if r.duration_minutes is not None]
    fastest_route_name = (
        min(duration_scored, key=lambda r: r.duration_minutes).name
        if len(duration_scored) == len(results) and results
        else None
    )

    balanced_route_name = _pick_balanced_route(results, fastest_route_name is not None)

    return RouteComparisonResult(
        routes=results,
        recommended_route_name=recommended_route_name,
        recommendation_text=recommendation_text,
        lowest_co2_route_name=lowest_co2_route_name,
        fastest_route_name=fastest_route_name,
        balanced_route_name=balanced_route_name,
    )


def _normalize(values: dict[str, float]) -> dict[str, float]:
    """Min-max normalize to [0, 1], where 0 is best (lowest value)."""
    lo, hi = min(values.values()), max(values.values())
    if hi == lo:
        return {name: 0.0 for name in values}
    return {name: (v - lo) / (hi - lo) for name, v in values.items()}


def _pick_balanced_route(
    results: list[RouteExposureResult], include_duration: bool
) -> str | None:
    """A route only qualifies for 'balanced' if it has every criterion being
    weighted — never scoring a route on data it's missing.
    """
    exposure = {
        r.name: r.estimated_aqi_exposure
        for r in results
        if r.estimated_aqi_exposure is not None
    }
    co2 = {
        r.name: r.estimated_co2_kg for r in results if r.estimated_co2_kg is not None
    }
    duration = (
        {r.name: r.duration_minutes for r in results if r.duration_minutes is not None}
        if include_duration
        else {}
    )

    eligible_names = set(exposure) & set(co2)
    if include_duration:
        eligible_names &= set(duration)
    if not eligible_names:
        return None

    exposure_norm = _normalize({n: exposure[n] for n in eligible_names})
    co2_norm = _normalize({n: co2[n] for n in eligible_names})
    duration_norm = (
        _normalize({n: duration[n] for n in eligible_names}) if include_duration else {}
    )

    def score(name: str) -> float:
        parts = [exposure_norm[name], co2_norm[name]]
        if include_duration:
            parts.append(duration_norm[name])
        return sum(parts) / len(parts)

    return min(eligible_names, key=score)
