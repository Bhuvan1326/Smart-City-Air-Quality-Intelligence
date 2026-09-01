"""The six real, authoritative Pune monitoring stations for Live AQI.

This module owns two things:

1. `REQUIRED_STATIONS` — the fixed spec for exactly the six stations this
   deployment must treat as the authoritative real-time Pune AQI source
   (Savitribai Phule Pune University, Alandi, Dhankawadi, Hadapsar, Karve
   Road, Nigdi). This is metadata about *which real-world station we're
   looking for*, not a fallback data source — no AQI/pollutant values live
   here.

2. `match_station(candidates, spec)` — robust matching of that spec
   against a list of real OpenAQ `/locations` results, so a station is
   only ever linked to an OpenAQ location that's genuinely that station,
   never a plausible "nearest" location. Matching combines normalized
   name equality/containment, provider/owner keyword agreement, and a
   coordinate sanity check (a secondary confirmation, never the primary
   signal) — a location must clear a name+provider bar before coordinates
   are even considered.

Per requirement 2 of the Pune live-AQI spec, this deliberately does NOT
implement a generic "find the nearest OpenAQ station to this lat/lon"
lookup (that's `openaq.fetch_nearest_reading`, used by the separate
Mumbai/legacy path) — a nearest-station search could silently resolve to
the wrong monitoring station.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RequiredStation:
    # Stable local identifier — used as MonitoringStation.station_code.
    station_code: str
    # Canonical display name for the Live AQI UI.
    display_name: str
    # Alternate names/spellings OpenAQ might use for this same physical
    # station. Matching checks all of these, not just `display_name`.
    name_variants: tuple[str, ...]
    # Expected provider/owner, used as a secondary match signal.
    provider: str  # "MPCB" or "IITM"
    # Approximate coordinates for this station, used ONLY to (a) seed the
    # OpenAQ search radius and (b) sanity-check candidate matches — never
    # to fabricate a reading or to stand in for a real OpenAQ coordinate.
    approx_lat: float
    approx_lon: float
    city: str = "Pune"
    state: str = "Maharashtra"
    country: str = "India"


# Approximate coordinates are public-knowledge locations for these six
# named places in Pune, used only for search-radius seeding and sanity
# checks as documented above — the real, authoritative latitude/longitude
# persisted for each station always comes from OpenAQ's own location
# record once matched (see _ensure_pune_station_row in aqi_ingestion.py).
REQUIRED_STATIONS: tuple[RequiredStation, ...] = (
    RequiredStation(
        station_code="PUNE_LIVE_SPPU",
        display_name="Savitribai Phule Pune University",
        name_variants=(
            "savitribai phule pune university",
            "pune university",
            "sppu",
        ),
        provider="MPCB",
        approx_lat=18.5529,
        approx_lon=73.8228,
    ),
    RequiredStation(
        station_code="PUNE_LIVE_ALANDI",
        display_name="Alandi",
        name_variants=("alandi",),
        provider="IITM",
        approx_lat=18.6780,
        approx_lon=73.9040,
    ),
    RequiredStation(
        station_code="PUNE_LIVE_DHANKAWADI",
        display_name="Dhankawadi",
        name_variants=("dhankawadi", "dhankwadi"),
        provider="IITM",
        approx_lat=18.4600,
        approx_lon=73.8480,
    ),
    RequiredStation(
        station_code="PUNE_LIVE_HADAPSAR",
        display_name="Hadapsar",
        name_variants=("hadapsar",),
        provider="IITM",
        approx_lat=18.5089,
        approx_lon=73.9259,
    ),
    RequiredStation(
        station_code="PUNE_LIVE_KARVE_ROAD",
        display_name="Karve Road",
        name_variants=("karve road", "karveroad", "karve rd"),
        provider="MPCB",
        approx_lat=18.5019,
        approx_lon=73.8225,
    ),
    RequiredStation(
        station_code="PUNE_LIVE_NIGDI",
        display_name="Nigdi",
        name_variants=("nigdi",),
        provider="IITM",
        approx_lat=18.6520,
        approx_lon=73.7680,
    ),
)

# Search radius around each station's approximate coordinates when asking
# OpenAQ "what's near here", generous enough to tolerate the true station
# coordinate being a few km from the public-knowledge approximate point,
# but not so large that it starts pulling in unrelated stations for
# matching to filter through.
SEARCH_RADIUS_M = 12_000

# Sanity-check radius: even after a name+provider match, a candidate must
# be within this distance of the approximate point, or it's rejected as
# probably a same-named-but-different location rather than trusted blindly.
_MAX_SANITY_DISTANCE_M = 30_000


def _normalize(name: str) -> str:
    """Lowercase, strip punctuation/extra whitespace, drop generic station
    words (CAAQMS/monitoring/station/etc.) that OpenAQ or CPCB/MPCB/IITM
    naming conventions add around the actual place name."""
    n = name.lower().strip()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(
        r"\b(caaqms|manual|monitoring|station|aqms|iitm|mpcb|cpcb|air|quality)\b",
        " ",
        n,
    )
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _name_matches(candidate_name: str, spec: RequiredStation) -> bool:
    norm_candidate = _normalize(candidate_name)
    if not norm_candidate:
        return False
    for variant in spec.name_variants:
        norm_variant = _normalize(variant)
        if not norm_variant:
            continue
        if norm_variant == norm_candidate:
            return True
        # Containment either direction: OpenAQ names are often
        # "<Place>, Pune - MPCB" or "IITM_<Place>" style compounds.
        if norm_variant in norm_candidate or norm_candidate in norm_variant:
            return True
    return False


def _provider_matches(candidate_owner: str | None, spec: RequiredStation) -> bool:
    if not candidate_owner:
        return False
    owner = candidate_owner.lower()
    return spec.provider.lower() in owner


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    r = 6_371_000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * r * asin(sqrt(a))


def match_station(candidates: list[dict], spec: RequiredStation) -> dict | None:
    """Pick the single OpenAQ `/locations` result (raw dict, as returned by
    the API) that genuinely corresponds to `spec`, or None if no candidate
    clears the bar.

    Matching is deliberately conservative: a candidate must match on name
    (allowing for punctuation/suffix differences) AND, when the OpenAQ
    record exposes an owner/provider field, agree with the expected
    provider. Coordinates are checked last, only as a sanity filter against
    an already name-matched candidate — never used to select a candidate
    by proximity alone (that would be the disallowed "nearest station"
    behaviour).
    """
    name_matches = [c for c in candidates if _name_matches(c.get("name", ""), spec)]
    if not name_matches:
        return None

    if len(name_matches) > 1:
        provider_matches = [
            c
            for c in name_matches
            if _provider_matches(
                (c.get("owner") or {}).get("name")
                or (c.get("provider") or {}).get("name"),
                spec,
            )
        ]
        if provider_matches:
            name_matches = provider_matches

    def _within_sanity_distance(c: dict) -> bool:
        coords = c.get("coordinates") or {}
        lat, lon = coords.get("latitude"), coords.get("longitude")
        if lat is None or lon is None:
            return False
        return (
            _haversine_m(spec.approx_lat, spec.approx_lon, lat, lon)
            <= _MAX_SANITY_DISTANCE_M
        )

    sane = [c for c in name_matches if _within_sanity_distance(c)]
    if not sane:
        # Every name match failed the coordinate sanity check — likely a
        # same/similar-named station elsewhere. Do not guess.
        return None

    if len(sane) == 1:
        return sane[0]

    # Multiple plausible candidates remain even after name+provider+sanity
    # filtering — pick the closest to the approximate point as the final
    # tiebreaker (not the primary matching signal, only a tiebreaker among
    # already-validated candidates).
    def _distance(c: dict) -> float:
        coords = c.get("coordinates") or {}
        return _haversine_m(
            spec.approx_lat, spec.approx_lon, coords["latitude"], coords["longitude"]
        )

    return min(sane, key=_distance)
