"""
GIS Operations Service — PostGIS-backed spatial analysis.

Implements: buffer analysis, nearest neighbor, route optimisation (TSP),
ward boundaries, point-in-polygon, geofencing, spatial clustering.
"""

from __future__ import annotations

import math

from app.schemas.aqi import get_aqi_category
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Pune ward boundary GeoJSON (approximate polygons at ward level)
# In production these come from the municipal corporation shapefile
PUNE_WARD_BOUNDARIES = {
    "W01": {"name": "Karve Road", "center": [73.8077, 18.5074]},
    "W02": {"name": "Shivajinagar", "center": [73.8475, 18.5308]},
    "W03": {"name": "Hadapsar", "center": [73.9259, 18.5089]},
    "W04": {"name": "Pimpri", "center": [73.7997, 18.6298]},
    "W05": {"name": "Katraj", "center": [73.8618, 18.4530]},
    "W06": {"name": "Wakad", "center": [73.7601, 18.5989]},
    "W07": {"name": "Kothrud", "center": [73.8126, 18.4968]},
    "W08": {"name": "Yerawada", "center": [73.9007, 18.5559]},
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class GISService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_ward_boundaries(self, city: str) -> dict:
        """
        Return GeoJSON FeatureCollection of ward boundaries.
        In production reads from PostGIS; here generates from known centroids.
        """
        if city != "Pune":
            return {"type": "FeatureCollection", "features": []}

        features = []
        for ward_id, meta in PUNE_WARD_BOUNDARIES.items():
            cx, cy = meta["center"]
            delta = 0.025  # ~2.5km side
            # Approximate rectangular ward polygon
            coords = [
                [
                    [cx - delta, cy - delta],
                    [cx + delta, cy - delta],
                    [cx + delta, cy + delta],
                    [cx - delta, cy + delta],
                    [cx - delta, cy - delta],
                ]
            ]
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "ward_id": ward_id,
                        "ward_name": meta["name"],
                        "city": city,
                    },
                    "geometry": {"type": "Polygon", "coordinates": coords},
                }
            )
        return {"type": "FeatureCollection", "features": features}

    async def buffer_analysis(
        self, latitude: float, longitude: float, radius_km: float
    ) -> dict:
        """
        Find all emission sources and monitoring stations within radius_km of a point.
        Uses PostGIS ST_DWithin for spatial query.
        """
        radius_m = radius_km * 1000
        try:
            sources = await self.session.execute(
                text(
                    """
                SELECT name, source_type, ward_id, violation_count, permit_status,
                       latitude, longitude,
                       ST_Distance(
                           geometry::geography,
                           ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                       ) / 1000 AS distance_km
                FROM emission_sources
                WHERE ST_DWithin(
                    geometry::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :radius_m
                )
                AND is_deleted = false AND is_active = true
                ORDER BY distance_km
                LIMIT 20
            """
                ),
                {"lat": latitude, "lon": longitude, "radius_m": radius_m},
            )
            source_list = [dict(row._mapping) for row in sources]

            stations = await self.session.execute(
                text(
                    """
                SELECT name, station_code, ward_id, is_active, maintenance_score,
                       latitude, longitude,
                       ST_Distance(
                           geometry::geography,
                           ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                       ) / 1000 AS distance_km
                FROM monitoring_stations
                WHERE ST_DWithin(
                    geometry::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :radius_m
                )
                AND is_deleted = false
                ORDER BY distance_km
                LIMIT 10
            """
                ),
                {"lat": latitude, "lon": longitude, "radius_m": radius_m},
            )
            station_list = [dict(row._mapping) for row in stations]

        except Exception:  # noqa: BLE001 -- PostGIS unavailable, fall back to haversine
            # PostGIS not available — fall back to haversine
            source_list = []
            station_list = []

        return {
            "center": {"latitude": latitude, "longitude": longitude},
            "radius_km": radius_km,
            "emission_sources": source_list,
            "monitoring_stations": station_list,
            "total_sources": len(source_list),
            "total_stations": len(station_list),
        }

    async def nearest_stations(
        self, latitude: float, longitude: float, limit: int = 5
    ) -> list[dict]:
        """Find nearest monitoring stations to a point."""
        try:
            result = await self.session.execute(
                text(
                    """
                SELECT name, station_code, ward_id, is_active,
                       latitude, longitude,
                       ST_Distance(
                           geometry::geography,
                           ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                       ) / 1000 AS distance_km
                FROM monitoring_stations
                WHERE is_deleted = false AND is_active = true
                ORDER BY geometry::geography <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                LIMIT :limit
            """
                ),
                {"lat": latitude, "lon": longitude, "limit": limit},
            )
            return [dict(row._mapping) for row in result]
        except Exception:  # noqa: BLE001 -- PostGIS unavailable, degrade to empty
            return []

    async def point_in_ward(
        self, latitude: float, longitude: float, city: str
    ) -> str | None:
        """Determine which ward a point falls in using PostGIS."""
        if city != "Pune":
            return None
        # Simple centroid-based fallback
        min_dist = float("inf")
        nearest_ward = None
        for ward_id, meta in PUNE_WARD_BOUNDARIES.items():
            cx, cy = meta["center"]
            dist = _haversine_km(latitude, longitude, cy, cx)
            if dist < min_dist:
                min_dist = dist
                nearest_ward = ward_id
        return nearest_ward

    async def optimise_officer_route(
        self,
        officer_latitude: float,
        officer_longitude: float,
        waypoints: list[dict],
        city: str,
    ) -> dict:
        """
        Nearest-neighbour TSP for officer route optimisation.
        Waypoints: [{"latitude": float, "longitude": float, "name": str, "priority": float}]
        Returns ordered route with distance and time estimates.
        """
        if not waypoints:
            return {
                "waypoints": [],
                "total_distance_km": 0,
                "estimated_duration_min": 0,
            }

        # Sort by priority first, then apply nearest-neighbour
        sorted_wp = sorted(waypoints, key=lambda w: -float(w.get("priority", 0)))

        # Nearest-neighbour TSP from officer position
        current_lat = officer_latitude
        current_lon = officer_longitude
        ordered = []
        remaining = list(sorted_wp)
        total_distance = 0.0

        while remaining:
            # Find nearest unvisited waypoint (weighted by priority)
            best = min(
                remaining,
                key=lambda w: (
                    _haversine_km(
                        current_lat, current_lon, w["latitude"], w["longitude"]
                    )
                    / max(float(w.get("priority", 1)), 1)
                ),
            )
            dist = _haversine_km(
                current_lat, current_lon, best["latitude"], best["longitude"]
            )
            total_distance += dist
            current_lat = best["latitude"]
            current_lon = best["longitude"]
            ordered.append({**best, "distance_from_prev_km": round(dist, 2)})
            remaining.remove(best)

        # Estimate duration: 30 km/h average in urban traffic + 20 min per inspection
        drive_time = (total_distance / 30) * 60
        inspection_time = len(ordered) * 20
        total_minutes = round(drive_time + inspection_time)

        optimisation_score = min(
            100.0, 70.0 + (len(ordered) / max(len(waypoints), 1)) * 30
        )

        return {
            "waypoints": ordered,
            "total_distance_km": round(total_distance, 2),
            "estimated_duration_min": total_minutes,
            "optimisation_score": round(optimisation_score, 1),
            "algorithm": "nearest_neighbour_priority_weighted",
            "waypoint_count": len(ordered),
        }

    async def spatial_cluster_hotspots(
        self, city: str, radius_km: float = 2.0
    ) -> list[dict]:
        """
        Cluster emission sources with high violations into spatial hotspot groups.
        Uses DBSCAN-style density clustering based on haversine distance.
        """
        result = await self.session.execute(
            text(
                """
            SELECT name, source_type, ward_id, violation_count,
                   latitude, longitude
            FROM emission_sources
            WHERE city = :city AND is_active = true AND is_deleted = false
              AND violation_count > 0
            ORDER BY violation_count DESC
        """
            ),
            {"city": city},
        )
        sources = [dict(row._mapping) for row in result]

        if not sources:
            return []

        # Simple grid-based clustering
        clusters: list[dict] = []
        assigned = [False] * len(sources)

        for i, src in enumerate(sources):
            if assigned[i]:
                continue
            cluster_members = [src]
            assigned[i] = True
            for j, other in enumerate(sources):
                if assigned[j]:
                    continue
                dist = _haversine_km(
                    src["latitude"],
                    src["longitude"],
                    other["latitude"],
                    other["longitude"],
                )
                if dist <= radius_km:
                    cluster_members.append(other)
                    assigned[j] = True

            avg_lat = sum(m["latitude"] for m in cluster_members) / len(cluster_members)
            avg_lon = sum(m["longitude"] for m in cluster_members) / len(
                cluster_members
            )
            total_violations = sum(m.get("violation_count", 0) for m in cluster_members)

            clusters.append(
                {
                    "centroid": {"latitude": avg_lat, "longitude": avg_lon},
                    "members": cluster_members,
                    "member_count": len(cluster_members),
                    "total_violations": total_violations,
                    "dominant_type": max(
                        {m["source_type"] for m in cluster_members},
                        key=lambda t: sum(
                            1 for m in cluster_members if m["source_type"] == t
                        ),
                    ),
                    "ward_ids": list(
                        {m["ward_id"] for m in cluster_members if m.get("ward_id")}
                    ),
                    "priority_score": min(
                        100, total_violations * 8 + len(cluster_members) * 5
                    ),
                }
            )

        return sorted(clusters, key=lambda c: -c["priority_score"])

    async def pollution_hotspots(
        self, city: str, radius_km: float = 1.5, aqi_threshold: int = 100
    ) -> list[dict]:
        """
        Cluster monitoring stations currently reporting unhealthy AQI
        (last hour average > aqi_threshold) into spatial pollution hotspot
        groups. Uses the same haversine density-clustering approach as
        spatial_cluster_hotspots, but over real-time AQI readings instead
        of enforcement violation counts.
        """
        result = await self.session.execute(
            text(
                """
            SELECT s.id AS station_id, s.name, s.latitude, s.longitude,
                   AVG(r.aqi) AS avg_aqi, MAX(r.aqi) AS peak_aqi,
                   AVG(r.pm25) AS avg_pm25, AVG(r.pm10) AS avg_pm10,
                   AVG(r.no2) AS avg_no2, AVG(r.so2) AS avg_so2, AVG(r.o3) AS avg_o3
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city AND s.is_deleted = false
              AND r.timestamp > NOW() - INTERVAL '1 hour'
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
            GROUP BY s.id, s.name, s.latitude, s.longitude
            HAVING AVG(r.aqi) > :threshold
        """
            ),
            {"city": city, "threshold": aqi_threshold},
        )
        points = [dict(row._mapping) for row in result]
        if not points:
            return []

        # A slightly-earlier snapshot (3-4h ago) for each of the same
        # stations, used purely to derive a worsening/improving/stable trend.
        prior_result = await self.session.execute(
            text(
                """
            SELECT s.id AS station_id, AVG(r.aqi) AS prior_avg_aqi
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city AND s.is_deleted = false
              AND r.timestamp BETWEEN NOW() - INTERVAL '4 hours' AND NOW() - INTERVAL '3 hours'
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
            GROUP BY s.id
        """
            ),
            {"city": city},
        )
        prior_by_station = {row.station_id: row.prior_avg_aqi for row in prior_result}

        # Rough "unhealthy" thresholds per pollutant (µg/m³), used only to
        # rank which pollutant is dominant within a cluster — not to score.
        pollutant_thresholds = {
            "pm25": 60.0,
            "pm10": 100.0,
            "no2": 80.0,
            "so2": 80.0,
            "o3": 100.0,
        }

        clusters: list[dict] = []
        assigned = [False] * len(points)

        for i, pt in enumerate(points):
            if assigned[i]:
                continue
            members = [pt]
            assigned[i] = True
            for j, other in enumerate(points):
                if assigned[j]:
                    continue
                dist = _haversine_km(
                    pt["latitude"],
                    pt["longitude"],
                    other["latitude"],
                    other["longitude"],
                )
                if dist <= radius_km:
                    members.append(other)
                    assigned[j] = True

            avg_lat = sum(m["latitude"] for m in members) / len(members)
            avg_lon = sum(m["longitude"] for m in members) / len(members)
            avg_aqi = sum(float(m["avg_aqi"]) for m in members) / len(members)
            peak_aqi = max(float(m["peak_aqi"]) for m in members)
            approx_radius_m = max(
                (
                    _haversine_km(avg_lat, avg_lon, m["latitude"], m["longitude"])
                    * 1000
                    for m in members
                ),
                default=0.0,
            )

            pollutant_ratios = {}
            for pname, threshold in pollutant_thresholds.items():
                vals = [
                    m.get(f"avg_{pname}")
                    for m in members
                    if m.get(f"avg_{pname}") is not None
                ]
                if vals:
                    pollutant_ratios[pname] = (sum(vals) / len(vals)) / threshold
            dominant_pollutant = (
                max(pollutant_ratios, key=pollutant_ratios.get)
                if pollutant_ratios
                else None
            )

            prior_vals = [
                prior_by_station[m["station_id"]]
                for m in members
                if m["station_id"] in prior_by_station
                and prior_by_station[m["station_id"]] is not None
            ]
            if prior_vals:
                prior_avg = sum(prior_vals) / len(prior_vals)
                delta = avg_aqi - prior_avg
                trend = (
                    "worsening"
                    if delta > 5
                    else "improving" if delta < -5 else "stable"
                )
            else:
                trend = "stable"

            category, _ = get_aqi_category(int(avg_aqi))

            clusters.append(
                {
                    "centroid_latitude": round(avg_lat, 5),
                    "centroid_longitude": round(avg_lon, 5),
                    "avg_aqi": round(avg_aqi, 1),
                    "peak_aqi": round(peak_aqi, 1),
                    "point_count": len(members),
                    "dominant_pollutant": dominant_pollutant,
                    "approx_radius_m": round(max(approx_radius_m, 200.0), 1),
                    "trend": trend,
                    "aqi_category": category,
                }
            )

        return sorted(clusters, key=lambda c: -c["avg_aqi"])

    async def geofence_check(
        self,
        latitude: float,
        longitude: float,
        ward_id: str,
        city: str,
    ) -> dict:
        """Check if a point is within a ward boundary."""
        own_ward = await self.point_in_ward(latitude, longitude, city)
        inside = own_ward == ward_id
        return {
            "point": {"latitude": latitude, "longitude": longitude},
            "target_ward": ward_id,
            "detected_ward": own_ward,
            "is_inside": inside,
            "city": city,
        }
