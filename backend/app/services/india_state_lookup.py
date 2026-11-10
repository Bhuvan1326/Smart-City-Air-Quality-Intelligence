from __future__ import annotations

import json
import os
from functools import lru_cache

_GEOJSON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "india_states.geojson"
)


def _outer_rings(geometry: dict):
    t = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if t == "Polygon" and coords:
        yield coords[0]
    elif t == "MultiPolygon":
        for poly in coords:
            if poly:
                yield poly[0]


@lru_cache(maxsize=1)
def _load_boundaries() -> list[tuple[str, list[list]]]:
    with open(_GEOJSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    out: list[tuple[str, list[list]]] = []
    for feature in data.get("features", []):
        name = (feature.get("properties") or {}).get("ST_NM")
        geom = feature.get("geometry") or {}
        if not name:
            continue
        out.append((name, list(_outer_rings(geom))))
    return out


def _ring_contains(ring: list, lon: float, lat: float) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_int = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_int:
                inside = not inside
        j = i
    return inside


def _distance_deg(px: float, py: float, ring: list) -> float:
    best = float("inf")
    for x, y in ring:
        d = (x - px) ** 2 + (y - py) ** 2
        if d < best:
            best = d
    return best**0.5


def lookup_state(
    latitude: float | None,
    longitude: float | None,
    *,
    fallback_km: float | None = 25.0,
) -> str | None:
    if latitude is None or longitude is None:
        return None
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    for name, outers in _load_boundaries():
        if any(_ring_contains(ring, lon, lat) for ring in outers):
            return name
    if fallback_km is None:
        return None
    max_deg = fallback_km / 111.0
    best_name: str | None = None
    best_dist = max_deg
    for name, outers in _load_boundaries():
        for ring in outers:
            d = _distance_deg(lon, lat, ring)
            if d < best_dist:
                best_dist = d
                best_name = name
    return best_name
