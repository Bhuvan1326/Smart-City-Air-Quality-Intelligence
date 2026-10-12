"""K1 data-freshness KPI (Week 2, D3 groundwork).

Formula (docs/week-1/kpi-definitions.md):
    fresh_pct = 100 * (stations_live + stations_recent) / stations_total
where, per ACTIVE station in the city, the latest reading with
quality_flag NOT IN ('synthetic', 'invalid') is classified by
app.services.data_freshness.classify_freshness (LIVE <= live threshold, RECENT <= 120 min, else STALE;
future timestamps beyond tolerance and missing readings are UNAVAILABLE).
Synthetic readings never count as live, and a station that only has synthetic
data is reported separately.
"""

from datetime import UTC, datetime
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import AQIReading, MonitoringStation
from app.schemas.kpi import DataFreshnessKPI
from app.services.data_freshness import (
    _LIVE_THRESHOLD_MINUTES,
    _STALE_THRESHOLD_MINUTES,
    FreshnessStatus,
    classify_freshness,
)

DEFINITION = (
    "Share of active stations whose latest non-synthetic reading is at most "
    f"{_STALE_THRESHOLD_MINUTES} minutes old (reading timestamp = provider "
    "observation time)."
)


async def compute_data_freshness_kpi(
    session: AsyncSession, city: str, now: datetime | None = None
) -> DataFreshnessKPI:
    now = now or datetime.now(UTC)
    stations = (
        (
            await session.execute(
                select(MonitoringStation.id).where(
                    MonitoringStation.city == city,
                    MonitoringStation.is_active.is_(True),
                    MonitoringStation.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    latest: dict = {}
    synthetic_stations: set = set()
    if stations:
        rows = (
            await session.execute(
                select(AQIReading.station_id, func.max(AQIReading.timestamp))
                .where(
                    AQIReading.station_id.in_(stations),
                    AQIReading.is_deleted.is_(False),
                    AQIReading.quality_flag.not_in(["synthetic", "invalid"]),
                )
                .group_by(AQIReading.station_id)
            )
        ).all()
        latest = {sid: ts for sid, ts in rows}
        synth = (
            (
                await session.execute(
                    select(AQIReading.station_id)
                    .where(
                        AQIReading.station_id.in_(stations),
                        AQIReading.quality_flag == "synthetic",
                        AQIReading.is_deleted.is_(False),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        synthetic_stations = {s for s in synth if s not in latest}

    live = recent = stale = unavailable = 0
    ages: list[float] = []
    for sid in stations:
        ts = latest.get(sid)
        state = (
            classify_freshness(ts, now=now)
            if ts is not None
            else FreshnessStatus.UNAVAILABLE
        )
        if state == FreshnessStatus.LIVE:
            live += 1
        elif state == FreshnessStatus.RECENT:
            recent += 1
        elif state == FreshnessStatus.STALE:
            stale += 1
        else:
            unavailable += 1
        has_age = state in (
            FreshnessStatus.LIVE,
            FreshnessStatus.RECENT,
            FreshnessStatus.STALE,
        )
        if ts is not None and has_age:
            ages.append(max(0.0, (now - ts).total_seconds() / 60))

    total = len(stations)
    status = (
        "no_stations"
        if total == 0
        else ("no_live_data" if live + recent == 0 else "ok")
    )
    return DataFreshnessKPI(
        city=city,
        as_of=now,
        threshold_minutes=_STALE_THRESHOLD_MINUTES,
        live_threshold_minutes=_LIVE_THRESHOLD_MINUTES,
        stations_total=total,
        stations_live=live,
        stations_recent=recent,
        stations_stale=stale,
        stations_unavailable=unavailable,
        stations_synthetic_only=len(synthetic_stations),
        fresh_pct=round(100 * (live + recent) / total, 1) if total else None,
        median_age_minutes=round(median(ages), 1) if ages else None,
        status=status,
        definition=DEFINITION,
        caveats=[
            "Readings stored before the Week 2 D1 fix were stamped with fetch time, "
            "not observation time, and can overstate freshness.",
            "Synthetic (seeded) readings are excluded and never counted as live.",
        ],
    )
