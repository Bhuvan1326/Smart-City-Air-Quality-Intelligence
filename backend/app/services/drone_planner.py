"""
Drone Inspection Planning.

Given one or more hotspot polygons (e.g. wards flagged by the Pollution
Attribution Agent, or emission sources with high violation counts), this
module:

  1. Generates a boustrophedon ("lawnmower") coverage path over each
     hotspot's bounding area, spaced by the camera swath width so the whole
     area is photographed.
  2. Clips the path around any configured no-fly zones (buffered polygons —
     e.g. airports, hospitals, defence installations).
  3. Splits the path into battery-limited sorties: given a max flight time
     and cruise speed, the full coverage path is chunked into legs the
     drone can actually fly on one battery, each returning to the launch
     point.
  4. Exports everything as GeoJSON (FeatureCollection) for direct use on
     the frontend Leaflet/Mapbox map.

All geometry here uses plain latitude/longitude arithmetic with a local
equirectangular approximation (fine at city scale, ~10km hotspots) rather
than pulling in a full geodesy library — keeps this dependency-free and
easy to unit test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core.config import settings

_EARTH_RADIUS_M = 6371000.0


def _meters_per_degree(lat: float) -> tuple[float, float]:
    """Returns (meters per degree longitude, meters per degree latitude) at this latitude."""
    lat_rad = math.radians(lat)
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(lat_rad)
    return m_per_deg_lon, m_per_deg_lat


@dataclass
class Waypoint:
    latitude: float
    longitude: float
    order: int
    is_return_to_base: bool = False


@dataclass
class DroneSortie:
    sortie_number: int
    waypoints: list[Waypoint]
    estimated_duration_minutes: float
    estimated_distance_meters: float


@dataclass
class DroneFlightPlanResult:
    hotspot_id: str
    launch_point: tuple[float, float]  # (lat, lon)
    sorties: list[DroneSortie] = field(default_factory=list)
    total_waypoints: int = 0
    total_distance_meters: float = 0.0
    coverage_area_sq_meters: float = 0.0
    excluded_no_fly_zones: int = 0
    reasoning: list[str] = field(default_factory=list)

    def to_geojson(self) -> dict:
        features = []
        for sortie in self.sorties:
            coords = [[wp.longitude, wp.latitude] for wp in sortie.waypoints]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "sortie_number": sortie.sortie_number,
                        "estimated_duration_minutes": sortie.estimated_duration_minutes,
                        "estimated_distance_meters": round(
                            sortie.estimated_distance_meters, 1
                        ),
                        "waypoint_count": len(sortie.waypoints),
                    },
                }
            )
            for wp in sortie.waypoints:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [wp.longitude, wp.latitude],
                        },
                        "properties": {
                            "sortie_number": sortie.sortie_number,
                            "order": wp.order,
                            "is_return_to_base": wp.is_return_to_base,
                        },
                    }
                )
        return {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "hotspot_id": self.hotspot_id,
                "total_sorties": len(self.sorties),
                "total_waypoints": self.total_waypoints,
                "total_distance_meters": round(self.total_distance_meters, 1),
                "coverage_area_sq_meters": round(self.coverage_area_sq_meters, 1),
                "excluded_no_fly_zones": self.excluded_no_fly_zones,
            },
        }


def _point_in_no_fly_zone(
    lat: float, lon: float, no_fly_zones: list[tuple[float, float, float]]
) -> bool:
    """no_fly_zones: list of (center_lat, center_lon, radius_meters)."""
    for zone_lat, zone_lon, radius_m in no_fly_zones:
        m_per_lon, m_per_lat = _meters_per_degree(zone_lat)
        dx = (lon - zone_lon) * m_per_lon
        dy = (lat - zone_lat) * m_per_lat
        if math.hypot(dx, dy) <= radius_m + settings.DRONE_NO_FLY_BUFFER_METERS:
            return True
    return False


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


class DronePlanner:
    def plan_coverage(
        self,
        hotspot_id: str,
        bbox: tuple[float, float, float, float],  # (min_lat, min_lon, max_lat, max_lon)
        *,
        launch_point: tuple[float, float] | None = None,
        no_fly_zones: list[tuple[float, float, float]] | None = None,
        swath_meters: float | None = None,
        max_flight_minutes: float | None = None,
        cruise_speed_mps: float | None = None,
    ) -> DroneFlightPlanResult:
        min_lat, min_lon, max_lat, max_lon = bbox
        swath = swath_meters or settings.DRONE_CAMERA_SWATH_METERS
        max_minutes = max_flight_minutes or settings.DRONE_MAX_FLIGHT_MINUTES
        speed = cruise_speed_mps or settings.DRONE_CRUISE_SPEED_MPS
        no_fly_zones = no_fly_zones or []

        launch = launch_point or ((min_lat + max_lat) / 2, min_lon)

        center_lat = (min_lat + max_lat) / 2
        m_per_lon, m_per_lat = _meters_per_degree(center_lat)
        width_m = (max_lon - min_lon) * m_per_lon
        height_m = (max_lat - min_lat) * m_per_lat

        reasoning = [
            f"Coverage area ≈{width_m:.0f}m x {height_m:.0f}m, swath={swath:.0f}m → "
            f"{max(1, math.ceil(height_m / swath))} lawnmower passes."
        ]

        # ── Boustrophedon coverage path ─────────────────────────────────────
        lat_step_deg = swath / m_per_lat
        raw_waypoints: list[tuple[float, float]] = []
        row_lat = min_lat
        row_index = 0
        excluded_count = 0
        while row_lat <= max_lat + 1e-9:
            lon_start, lon_end = (
                (min_lon, max_lon) if row_index % 2 == 0 else (max_lon, min_lon)
            )
            for lon in (lon_start, lon_end):
                if _point_in_no_fly_zone(row_lat, lon, no_fly_zones):
                    excluded_count += 1
                    continue
                raw_waypoints.append((row_lat, lon))
            row_lat += lat_step_deg
            row_index += 1

        if not raw_waypoints:
            reasoning.append(
                "Entire coverage area falls within no-fly buffers — no flight plan generated."
            )
            return DroneFlightPlanResult(
                hotspot_id=hotspot_id,
                launch_point=launch,
                excluded_no_fly_zones=excluded_count,
                reasoning=reasoning,
            )

        # ── Battery-aware sortie splitting ──────────────────────────────────
        max_distance_m = speed * max_minutes * 60
        sorties: list[DroneSortie] = []
        current_leg: list[tuple[float, float]] = [launch]
        current_distance = 0.0
        sortie_number = 1

        def _finalize_leg():
            nonlocal current_leg, current_distance, sortie_number
            if len(current_leg) <= 1:
                return
            # Return to base.
            back_distance = _haversine_meters(*current_leg[-1], *launch)
            current_leg.append(launch)
            total_distance = current_distance + back_distance
            waypoints = [
                Waypoint(
                    latitude=lat,
                    longitude=lon,
                    order=i,
                    is_return_to_base=(i == len(current_leg) - 1),
                )
                for i, (lat, lon) in enumerate(current_leg)
            ]
            sorties.append(
                DroneSortie(
                    sortie_number=sortie_number,
                    waypoints=waypoints,
                    estimated_duration_minutes=round(total_distance / speed / 60, 1),
                    estimated_distance_meters=total_distance,
                )
            )
            sortie_number += 1

        prev_point = launch
        unreachable_count = 0
        for point in raw_waypoints:
            leg_distance = _haversine_meters(*prev_point, *point)
            return_distance = _haversine_meters(*point, *launch)

            # If even a fresh sortie (empty leg) can't reach this point and
            # return home, it's outside the drone's range entirely at this
            # battery budget — skip it rather than silently violate the
            # battery constraint.
            fresh_leg_distance = _haversine_meters(*launch, *point)
            if fresh_leg_distance + return_distance > max_distance_m:
                unreachable_count += 1
                continue

            # If adding this point (and then returning home) would exceed
            # battery range, close out the current sortie and start a new
            # one from base.
            if (
                current_distance + leg_distance + return_distance > max_distance_m
                and len(current_leg) > 1
            ):
                _finalize_leg()
                current_leg = [launch]
                current_distance = 0.0
                prev_point = launch
                leg_distance = _haversine_meters(*prev_point, *point)

            current_leg.append(point)
            current_distance += leg_distance
            prev_point = point

        _finalize_leg()

        total_waypoints = sum(len(s.waypoints) for s in sorties)
        total_distance = sum(s.estimated_distance_meters for s in sorties)
        reasoning.append(
            f"Split into {len(sorties)} sortie(s) within a {max_minutes:.0f}-minute battery budget "
            f"at {speed:.1f} m/s cruise speed."
        )
        if excluded_count:
            reasoning.append(
                f"{excluded_count} candidate waypoint(s) excluded by no-fly zone buffers."
            )
        if unreachable_count:
            reasoning.append(
                f"{unreachable_count} candidate waypoint(s) are farther from the launch point than the "
                f"{max_minutes:.0f}-minute battery budget allows even on a dedicated sortie — increase "
                "max_flight_minutes, add a closer launch point, or accept partial coverage."
            )

        return DroneFlightPlanResult(
            hotspot_id=hotspot_id,
            launch_point=launch,
            sorties=sorties,
            total_waypoints=total_waypoints,
            total_distance_meters=total_distance,
            coverage_area_sq_meters=width_m * height_m,
            excluded_no_fly_zones=excluded_count,
            reasoning=reasoning,
        )
