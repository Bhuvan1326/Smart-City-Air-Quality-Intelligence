"""Authoritative *current* Pune AQI, shared by every feature that needs a
"what is Pune's AQI right now" number (the What-if Simulator, Waste
Circularity, Pollution Ward, etc.) rather than a historical/ward-fixture
average.

Why this module exists: `monitoring_stations.city = 'Pune'` matches BOTH
the six real, OpenAQ-matched `PUNE_LIVE_*` stations (see
`app.services.aqi_providers.pune_stations.REQUIRED_STATIONS`) AND the
legacy `PUNE_001`..`PUNE_008` ward/demo fixtures (see `app.core.seeder`
and `app.workers.tasks.aqi_ingestion.PUNE_STATIONS`), which several other
already-working features (attribution, forecasting, anomaly detection,
satellite, alerts, GIS) still legitimately rely on for their own
(non-"current AQI") purposes. A bare `WHERE city = :city` query — as the
simulator/waste-circularity/ward code previously did — therefore silently
blends synthetic/demo ward-fixture readings into what's presented as
Pune's *current* AQI. This module is the one place that resolves "current
Pune AQI" down to only the six authoritative stations, so every caller
gets the same answer and the same unavailable-handling.

Freshness itself is NOT redefined here — `app.services.data_freshness`
remains the single source of truth for live/recent/stale/demo thresholds.
This module simply restricts *which stations* are eligible before that
freshness policy is applied, and only counts a reading as part of
"current AQI" if it is LIVE or RECENT (i.e. `FreshnessStatus.is_reliable`)
and not synthetic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import MonitoringStation, QualityFlag
from app.repositories.aqi import AQIReadingRepository, MonitoringStationRepository
from app.services.aqi_providers import pune_stations
from app.services.data_freshness import classify_freshness


async def get_pune_live_stations(session: AsyncSession) -> list[MonitoringStation]:
    """The resolved authoritative `PUNE_LIVE_*` station rows only (whichever
    of the six have been matched to a real OpenAQ location so far).

    This is the candidate pool any Pune "nearest station" / "current AQI"
    computation must draw from — e.g. Construction & Dust Intelligence,
    Industrial Pollution Intelligence, and Waste Burning all need "which
    station is closest to this point, and what is its current reading"
    rather than a single citywide average, so they can't reuse
    `get_current_pune_aqi` directly — but they must draw from the same six
    stations, never from `MonitoringStationRepository.get_active_by_city`
    (which also returns the legacy `PUNE_001`..`PUNE_008` ward fixtures).
    """
    station_repo = MonitoringStationRepository(session)
    codes = [spec.station_code for spec in pune_stations.REQUIRED_STATIONS]
    stations_by_code = await station_repo.get_by_station_codes(codes)
    return [
        stations_by_code[spec.station_code]
        for spec in pune_stations.REQUIRED_STATIONS
        if spec.station_code in stations_by_code
    ]


@dataclass
class CurrentPuneAQI:
    # False when NONE of the six authoritative stations currently have a
    # reliable (live/recent, non-synthetic) reading — callers must show an
    # explicit "current data unavailable" state rather than falling back
    # to a stale/demo number.
    available: bool
    avg_aqi: float | None = None
    avg_pm25: float | None = None
    # Station codes that actually contributed a reliable reading, e.g.
    # ["PUNE_LIVE_SPPU", "PUNE_LIVE_HADAPSAR"].
    contributing_stations: list[str] = field(default_factory=list)
    # Ward ids covered by the contributing stations (derived from the
    # authoritative stations' own `ward_id`, never guessed).
    wards: list[str] = field(default_factory=list)
    total_stations: int = 6
    reason: str | None = None  # populated when available is False


async def get_current_pune_aqi(
    session: AsyncSession, *, ward_id: str | None = None
) -> CurrentPuneAQI:
    """Current Pune AQI derived exclusively from the six authoritative
    `PUNE_LIVE_*` stations. Never touches `PUNE_001`..`PUNE_008`.

    If `ward_id` is given, only stations whose (authoritative) `ward_id`
    matches are considered; if that ward has no authoritative station or
    none of its station(s) currently have a reliable reading, this
    returns `available=False` rather than borrowing a citywide number.
    """
    station_repo = MonitoringStationRepository(session)
    reading_repo = AQIReadingRepository(session)

    codes = [spec.station_code for spec in pune_stations.REQUIRED_STATIONS]
    stations_by_code = await station_repo.get_by_station_codes(codes)

    aqi_values: list[float] = []
    pm25_values: list[float] = []
    contributing: list[str] = []
    wards: set[str] = set()
    considered_any_station = False

    for spec in pune_stations.REQUIRED_STATIONS:
        station = stations_by_code.get(spec.station_code)
        if station is None:
            continue  # not yet resolved against a real OpenAQ location
        if ward_id and station.ward_id != ward_id:
            continue
        considered_any_station = True

        reading = await reading_repo.get_latest_by_station(station.id)
        if reading is None:
            continue
        is_synthetic = reading.quality_flag == QualityFlag.SYNTHETIC
        freshness = classify_freshness(reading.timestamp, is_synthetic=is_synthetic)
        if not freshness.is_reliable:
            # Stale/demo/unavailable — never presented as current/live,
            # per the strict OpenAQ freshness policy (requirement 9).
            continue

        if reading.aqi is not None:
            aqi_values.append(float(reading.aqi))
        if reading.pm25 is not None:
            pm25_values.append(float(reading.pm25))
        contributing.append(spec.station_code)
        if station.ward_id:
            wards.add(station.ward_id)

    if not aqi_values:
        reason = (
            f"No authoritative Pune Live station is currently assigned to ward "
            f"{ward_id}."
            if ward_id and not considered_any_station
            else "No authoritative Pune Live station currently has a live or "
            "recent observation."
        )
        return CurrentPuneAQI(available=False, reason=reason)

    return CurrentPuneAQI(
        available=True,
        avg_aqi=sum(aqi_values) / len(aqi_values),
        avg_pm25=(sum(pm25_values) / len(pm25_values)) if pm25_values else None,
        contributing_stations=contributing,
        wards=sorted(wards),
    )
