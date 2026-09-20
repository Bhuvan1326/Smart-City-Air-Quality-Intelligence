"""The real, authoritative Pune/Pimpri monitoring stations for Live AQI.

This module owns three things:

1. `REQUIRED_STATIONS` — the single canonical spec for exactly the eight
   stations this deployment must treat as the authoritative real-time
   Pune AQI source (Savitribai Phule Pune University, Dhankawadi,
   Hadapsar, Nigdi, Park Street Wakad, Katraj Dairy, Gavalinagar, Bhumkar
   Nagar). Every module that needs the Pune live station set consumes
   this tuple. This is metadata about *which real-world station we're
   looking for*, not a fallback data source — no AQI/pollutant values,
   no OpenAQ location ids and no station coordinates for the newer
   stations live here; those always come from OpenAQ at resolution time.

2. `RETIRED_STATIONS` — stations that used to be in the live set (Alandi,
   Karve Road). They are kept only so their rows can be marked inactive
   and so discovery/matching never revives or re-links them.

3. `match_station(candidates, spec)` — robust matching of that spec
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
from datetime import datetime

PUNE_REGION_CENTER: tuple[float, float] = (18.5204, 73.8567)
REGION_SEARCH_RADIUS_M = 25_000
REGION_SEARCH_LIMIT = 1000
_REGION_SANITY_DISTANCE_M = 35_000
INDIA_COUNTRY_CODE = "IN"


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
    provider: str | None = None
    # Approximate coordinates for this station, used ONLY to (a) seed the
    # OpenAQ search radius and (b) sanity-check candidate matches — never
    # to fabricate a reading or to stand in for a real OpenAQ coordinate.
    approx_lat: float | None = None
    approx_lon: float | None = None
    city: str = "Pune"
    state: str = "Maharashtra"
    country: str = "India"
    strict_name: bool = False

    @property
    def display_provider(self) -> str:
        return self.provider or "OpenAQ"

    @property
    def has_approx_location(self) -> bool:
        return self.approx_lat is not None and self.approx_lon is not None

    @property
    def search_lat(self) -> float:
        return self.approx_lat if self.approx_lat is not None else PUNE_REGION_CENTER[0]

    @property
    def search_lon(self) -> float:
        return self.approx_lon if self.approx_lon is not None else PUNE_REGION_CENTER[1]

    @property
    def search_radius_m(self) -> int:
        return SEARCH_RADIUS_M if self.has_approx_location else REGION_SEARCH_RADIUS_M

    @property
    def search_limit(self) -> int:
        return 100 if self.has_approx_location else REGION_SEARCH_LIMIT

    @property
    def sanity_distance_m(self) -> int:
        return (
            _MAX_SANITY_DISTANCE_M
            if self.has_approx_location
            else _REGION_SANITY_DISTANCE_M
        )


@dataclass(frozen=True)
class RetiredStation:
    station_code: str
    openaq_location_id: int


# Approximate coordinates exist only for the four long-standing stations,
# and are used only for search-radius seeding and sanity checks as
# documented above — the real, authoritative latitude/longitude persisted
# for every station always comes from OpenAQ's own location record once
# matched (see _ensure_pune_station_row in aqi_ingestion.py).
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
        station_code="PUNE_LIVE_NIGDI",
        display_name="Nigdi",
        name_variants=("nigdi",),
        provider="IITM",
        approx_lat=18.6520,
        approx_lon=73.7680,
    ),
    RequiredStation(
        station_code="PUNE_LIVE_PARK_STREET_WAKAD",
        display_name="Park Street Wakad",
        name_variants=("park street wakad", "wakad park street"),
        strict_name=True,
    ),
    RequiredStation(
        station_code="PUNE_LIVE_KATRAJ_DAIRY",
        display_name="Katraj Dairy",
        name_variants=("katraj dairy",),
        strict_name=True,
    ),
    RequiredStation(
        station_code="PUNE_LIVE_GAVALINAGAR",
        display_name="Gavalinagar",
        name_variants=("gavalinagar", "gavali nagar", "gawalinagar", "gawali nagar"),
        strict_name=True,
    ),
    RequiredStation(
        station_code="PUNE_LIVE_BHUMKAR_NAGAR",
        display_name="Bhumkar Nagar",
        name_variants=("bhumkar nagar", "bhumkarnagar"),
        strict_name=True,
    ),
)

RETIRED_STATIONS: tuple[RetiredStation, ...] = (
    RetiredStation(station_code="PUNE_LIVE_ALANDI", openaq_location_id=12042),
    RetiredStation(station_code="PUNE_LIVE_KARVE_ROAD", openaq_location_id=5661),
)

RETIRED_STATION_CODES: frozenset[str] = frozenset(
    retired.station_code for retired in RETIRED_STATIONS
)
RETIRED_OPENAQ_LOCATION_IDS: frozenset[int] = frozenset(
    retired.openaq_location_id for retired in RETIRED_STATIONS
)


def required_station_codes() -> list[str]:
    return [spec.station_code for spec in REQUIRED_STATIONS]


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
        if spec.strict_name:
            if f" {norm_variant} " in f" {norm_candidate} ":
                return True
            continue
        # Containment either direction: OpenAQ names are often
        # "<Place>, Pune - MPCB" or "IITM_<Place>" style compounds.
        if norm_variant in norm_candidate or norm_candidate in norm_variant:
            return True
    return False


def _provider_matches(candidate_owner: str | None, spec: RequiredStation) -> bool:
    if not candidate_owner or not spec.provider:
        return False
    owner = candidate_owner.lower()
    return spec.provider.lower() in owner


def _is_indian_location(candidate: dict) -> bool:
    country = candidate.get("country")
    if not isinstance(country, dict):
        return True
    code = country.get("code")
    if not code:
        return True
    return str(code).upper() == INDIA_COUNTRY_CODE


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    r = 6_371_000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _last_seen(candidate: dict) -> datetime | None:
    """Parse a candidate's own OpenAQ `datetimeLast.utc` field (present on
    real `/v3/locations` results — see the OpenAQ API docs' `Location`
    schema), i.e. when OpenAQ itself last saw a measurement from this
    location. Returns None if absent/unparseable rather than raising —
    this is only ever a secondary matching signal, never required."""
    raw = ((candidate.get("datetimeLast") or {}).get("utc")) or None
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None


def match_station(
    candidates: list[dict],
    spec: RequiredStation,
    *,
    exclude_location_ids: set[int] | None = None,
) -> dict | None:
    """Pick the single OpenAQ `/locations` result (raw dict, as returned by
    the API) that genuinely corresponds to `spec`, or None if no candidate
    clears the bar.

    Matching is deliberately conservative: a candidate must match on name
    (allowing for punctuation/suffix differences) AND, when the OpenAQ
    record exposes an owner/provider field, agree with the expected
    provider. Coordinates are checked next, only as a sanity filter
    against an already name-matched candidate — never used to select a
    candidate by proximity alone (that would be the disallowed "nearest
    station" behaviour). Only once a candidate has cleared name+provider
    +coordinate-sanity does OpenAQ's own `datetimeLast` recency get
    consulted, purely as a tiebreaker among multiple otherwise-equally
    valid candidates for the same physical station (e.g. an old
    decommissioned record and a newer active one sharing the same name) —
    never as a way to select a station that didn't already match on name.

    `exclude_location_ids`, when given, drops candidates with those
    OpenAQ location ids before any matching — used when re-resolving a
    station whose currently-cached location has stopped producing current
    observations, so re-resolution can't just re-pick the same stuck
    location.
    """
    candidates = [
        c
        for c in candidates
        if c.get("id") not in RETIRED_OPENAQ_LOCATION_IDS and _is_indian_location(c)
    ]
    if exclude_location_ids:
        candidates = [c for c in candidates if c.get("id") not in exclude_location_ids]

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
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            return False
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return False
        return (
            _haversine_m(spec.search_lat, spec.search_lon, lat, lon)
            <= spec.sanity_distance_m
        )

    sane = [c for c in name_matches if _within_sanity_distance(c)]
    if not sane:
        # Every name match failed the coordinate sanity check — likely a
        # same/similar-named station elsewhere. Do not guess.
        return None

    if len(sane) == 1:
        return sane[0]

    # Multiple plausible candidates remain even after name+provider+sanity
    # filtering. Prefer whichever is most recently confirmed active by
    # OpenAQ's own `datetimeLast`, since a stale/decommissioned record can
    # otherwise sit indefinitely alongside a newer active one under the
    # same name (this is a tiebreaker among already name-matched
    # candidates, never a way to select by recency alone).
    with_recency = [c for c in sane if _last_seen(c) is not None]
    if with_recency:
        return max(with_recency, key=_last_seen)

    # No candidate exposes a usable `datetimeLast` — fall back to the
    # closest to the approximate point as the final tiebreaker (not the
    # primary matching signal, only a tiebreaker among already-validated
    # candidates).
    def _distance(c: dict) -> float:
        coords = c.get("coordinates") or {}
        return _haversine_m(
            spec.search_lat, spec.search_lon, coords["latitude"], coords["longitude"]
        )

    return min(sane, key=_distance)
