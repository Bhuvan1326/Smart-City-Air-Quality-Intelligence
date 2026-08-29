"""City Sustainability Score — a single composite indicator aggregating
this platform's existing environmental and civic services into one
city-level number.

This module does not introduce a new data pipeline or a new scoring
architecture. It is a thin aggregator that calls into the repositories
and services the project already has (AQI readings, the carbon
estimator, the energy provider, urban heat, and the ward/water/civic
models) and combines their results.

Data-truthfulness rule (same as every other module in this codebase —
see app/services/energy_provider.py and app/models/demographics.py for
the canonical statements of this rule): a component is only ever scored
from real, on-record data. When a city genuinely has no data for a
component, that component's score is `None` and its classification is
`UNAVAILABLE` — it is never defaulted to 0, 50, 100, or any other
placeholder, and it is excluded from the overall-score denominator
rather than being counted against the city.

Nine components make up the score:

    air_quality          - CALCULATED from live AQI readings (last hour)
    energy               - grid carbon intensity via the energy provider
    carbon               - CALCULATED from on-record emission sources
    waste_circularity    - admin-entered ward waste diversion figures
    water                - admin-entered city reservoir level
    heat                 - CALCULATED from recent observed air temperature
    green_infrastructure - admin-entered ward green-cover figures
    civic_performance    - CALCULATED from civic issue resolution outcomes
    mobility             - UNAVAILABLE (see note below)

Mobility is always reported UNAVAILABLE: the repository's traffic/route
services (app.services.traffic_provider, app.services.route_comparison)
operate per-corridor or per-route, not as a city-wide aggregate, and
there is no model or repository query that produces a single city-level
mobility figure. Rather than invent one, this module honestly reports
mobility as unavailable — see PHASE 5 of the original brief.

Weighting: all nine components are weighted equally. This is a
transparent, documented heuristic (there is no authoritative published
weighting scheme for this composite), not an empirically calibrated
weighting. Only components with a real score contribute to the
weighted average; unavailable components are excluded from both the
numerator and the denominator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.models.civic_issue import CivicIssue, CivicIssueStatus
from app.models.demographics import WardDemographics
from app.models.monitoring import MonitoringStation
from app.models.water_resource import CityWaterResource
from app.repositories.aqi import AQIReadingRepository
from app.services.carbon_estimator import CarbonEstimatorService
from app.services.energy_provider import (EnergyDataSource,
                                          get_grid_carbon_intensity)
from app.services.urban_heat import HeatRiskLevel, assess_heat_risk
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

METHODOLOGY = (
    "Composite of nine equally-weighted components, each 0-100 where higher "
    "is more sustainable. Only components with genuine on-record data "
    "contribute to the overall score; unavailable components are excluded "
    "from the average rather than counted as zero. This weighting and the "
    "per-component normalization bands are a documented, transparent "
    "heuristic, not a calibrated or externally-published methodology — see "
    "each component's `note` for its specific derivation."
)

# Every component the score reports on, in a fixed display order. This is
# also where indicators_total (9) comes from.
_COMPONENT_NAMES: tuple[str, ...] = (
    "air_quality",
    "energy",
    "carbon",
    "waste_circularity",
    "water",
    "heat",
    "green_infrastructure",
    "civic_performance",
    "mobility",
)

_AQI_CEILING = 300.0  # CPCB/US-AQI "hazardous" ceiling used only to normalize 0-100
_ENERGY_CEILING_GCO2_PER_KWH = 900.0  # coal-heavy-grid ceiling, used only to normalize
_CARBON_CEILING_TON_PER_YEAR = 5000.0  # heuristic city-scale ceiling for normalization

_HEAT_RISK_SCORE = {
    HeatRiskLevel.LOW: 100.0,
    HeatRiskLevel.MODERATE: 70.0,
    HeatRiskLevel.HIGH: 40.0,
    HeatRiskLevel.SEVERE: 10.0,
}

_RESOLVED_STATUSES = {CivicIssueStatus.RESOLVED.value, CivicIssueStatus.CLOSED.value}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


@dataclass
class SustainabilityComponent:
    name: str
    score: float | None
    classification: str  # OBSERVED | CALCULATED | ESTIMATED | HISTORICAL | UNAVAILABLE
    note: str


@dataclass
class CitySustainabilityScore:
    city: str
    overall_score: float | None
    indicators_available: int
    indicators_total: int
    components: list[SustainabilityComponent]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    methodology: str = METHODOLOGY


def _unavailable(name: str, note: str) -> SustainabilityComponent:
    return SustainabilityComponent(
        name=name, score=None, classification="UNAVAILABLE", note=note
    )


async def _score_air_quality(
    session: AsyncSession, city: str
) -> SustainabilityComponent:
    avg_aqi = await AQIReadingRepository(session).get_city_average_aqi(city)
    if avg_aqi is None:
        return _unavailable(
            "air_quality",
            "No AQI readings in the last hour for this city.",
        )
    score = _clamp(100.0 - (avg_aqi / _AQI_CEILING) * 100.0)
    return SustainabilityComponent(
        name="air_quality",
        score=round(score, 1),
        classification="CALCULATED",
        note=(
            f"Derived from the last-hour city-average AQI ({avg_aqi:.0f}), "
            f"linearly normalized against a {_AQI_CEILING:.0f} AQI ceiling "
            "(heuristic, not a calibrated health index)."
        ),
    )


async def _representative_station(
    session: AsyncSession, city: str
) -> MonitoringStation | None:
    result = await session.execute(
        select(MonitoringStation)
        .where(
            MonitoringStation.city == city,
            MonitoringStation.is_active.is_(True),
            MonitoringStation.is_deleted.is_(False),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _score_energy(session: AsyncSession, city: str) -> SustainabilityComponent:
    station = await _representative_station(session, city)
    if station is None:
        return _unavailable(
            "energy",
            "No monitoring station on record for this city, so no location "
            "is available to query grid carbon intensity for.",
        )

    reading = await get_grid_carbon_intensity(
        station.latitude, station.longitude, city=city
    )
    if reading.value is None or reading.source == EnergyDataSource.UNAVAILABLE:
        return _unavailable(
            "energy",
            reading.note,
        )

    score = _clamp(100.0 - (reading.value / _ENERGY_CEILING_GCO2_PER_KWH) * 100.0)
    classification = {
        EnergyDataSource.LIVE: "OBSERVED",
        EnergyDataSource.CSV: "HISTORICAL",
        EnergyDataSource.DEMO: "ESTIMATED",
    }.get(reading.source, "ESTIMATED")
    return SustainabilityComponent(
        name="energy",
        score=round(score, 1),
        classification=classification,
        note=(
            f"Grid carbon intensity {reading.value:.0f} gCO2eq/kWh "
            f"({reading.note}), linearly normalized against a "
            f"{_ENERGY_CEILING_GCO2_PER_KWH:.0f} gCO2eq/kWh heuristic ceiling."
        ),
    )


async def _score_carbon(session: AsyncSession, city: str) -> SustainabilityComponent:
    estimate = await CarbonEstimatorService(session).estimate_city_emissions(city)
    if not estimate.get("source_breakdown"):
        return _unavailable(
            "carbon",
            "No active emission sources on record for this city.",
        )
    ton_per_year = estimate["total_co2_ton_per_year"]
    score = _clamp(100.0 - (ton_per_year / _CARBON_CEILING_TON_PER_YEAR) * 100.0)
    return SustainabilityComponent(
        name="carbon",
        score=round(score, 1),
        classification="CALCULATED",
        note=(
            f"Calculated from {len(estimate['source_breakdown'])} on-record "
            f"emission-source categories totalling {ton_per_year:.0f} "
            f"tCO2/year ({estimate['emission_factor_source']}), normalized "
            f"against a {_CARBON_CEILING_TON_PER_YEAR:.0f} tCO2/year "
            "heuristic ceiling."
        ),
    )


async def _ward_demographics_for_city(
    session: AsyncSession, city: str
) -> list[WardDemographics]:
    result = await session.execute(
        select(WardDemographics).where(
            WardDemographics.city == city,
            WardDemographics.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


async def _score_waste_circularity(
    session: AsyncSession, city: str
) -> SustainabilityComponent:
    wards = await _ward_demographics_for_city(session, city)
    diversion_pcts: list[float] = []
    for ward in wards:
        recycling = ward.waste_recycling_pct
        composting = ward.waste_composting_pct
        if recycling is None and composting is None:
            continue
        diversion_pcts.append((recycling or 0.0) + (composting or 0.0))

    if not diversion_pcts:
        return _unavailable(
            "waste_circularity",
            "No ward has admin-entered waste recycling/composting figures "
            "on record for this city.",
        )
    avg_diversion = sum(diversion_pcts) / len(diversion_pcts)
    return SustainabilityComponent(
        name="waste_circularity",
        score=round(_clamp(avg_diversion), 1),
        classification="OBSERVED",
        note=(
            f"City-average waste diverted from landfill (recycling + "
            f"composting) across {len(diversion_pcts)} ward(s) with "
            "admin-entered figures on record."
        ),
    )


async def _score_water(session: AsyncSession, city: str) -> SustainabilityComponent:
    result = await session.execute(
        select(CityWaterResource).where(CityWaterResource.city == city)
    )
    resource = result.scalar_one_or_none()
    if resource is None or resource.reservoir_level_pct is None:
        return _unavailable(
            "water",
            "No admin-entered reservoir level on record for this city.",
        )
    return SustainabilityComponent(
        name="water",
        score=round(_clamp(resource.reservoir_level_pct), 1),
        classification="OBSERVED",
        note=(
            "Reservoir level percentage as admin-entered from "
            f"{resource.source_note or 'the city water board'}"
            + (
                f" (as of {resource.data_as_of.isoformat()})"
                if resource.data_as_of
                else ""
            )
            + "."
        ),
    )


async def _score_heat(session: AsyncSession, city: str) -> SustainabilityComponent:
    station = await _representative_station(session, city)
    if station is None:
        return _unavailable(
            "heat",
            "No monitoring station on record for this city.",
        )

    since = datetime.now(UTC) - timedelta(hours=1)
    result = await session.execute(
        text(
            """
            SELECT AVG(r.temperature) AS avg_temp, MAX(r.timestamp) AS latest
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city
              AND r.temperature IS NOT NULL
              AND r.timestamp > :since
              AND r.is_deleted = false
              AND r.quality_flag != 'invalid'
            """
        ),
        {"city": city, "since": since},
    )
    row = result.first()
    if row is None or row.avg_temp is None:
        return _unavailable(
            "heat",
            "No recent temperature readings on record for this city.",
        )

    assessment = assess_heat_risk(
        latitude=station.latitude,
        longitude=station.longitude,
        air_temperature_c=float(row.avg_temp),
        air_temperature_observed_at=row.latest or datetime.now(UTC),
        ward_id=station.ward_id,
    )
    score = _HEAT_RISK_SCORE[assessment.heat_risk]
    return SustainabilityComponent(
        name="heat",
        score=score,
        classification="CALCULATED",
        note=(
            f"Heat risk '{assessment.heat_risk.value}' calculated from a "
            f"{float(row.avg_temp):.1f}\u00b0C last-hour average station "
            "temperature; no satellite vegetation signal was available for "
            "this call."
        ),
    )


async def _score_green_infrastructure(
    session: AsyncSession, city: str
) -> SustainabilityComponent:
    wards = await _ward_demographics_for_city(session, city)
    values = [w.green_cover_pct for w in wards if w.green_cover_pct is not None]
    if not values:
        return _unavailable(
            "green_infrastructure",
            "No ward has an admin-entered green-cover figure on record for "
            "this city.",
        )
    avg_green_cover = sum(values) / len(values)
    return SustainabilityComponent(
        name="green_infrastructure",
        score=round(_clamp(avg_green_cover), 1),
        classification="OBSERVED",
        note=(
            f"City-average green cover percentage across {len(values)} "
            "ward(s) with admin-entered figures on record."
        ),
    )


async def _score_civic_performance(
    session: AsyncSession, city: str
) -> SustainabilityComponent:
    result = await session.execute(
        select(CivicIssue.status).where(
            CivicIssue.city == city,
            CivicIssue.is_deleted.is_(False),
        )
    )
    statuses = [row[0] for row in result.all()]
    if not statuses:
        return _unavailable(
            "civic_performance",
            "No civic issues on record for this city.",
        )
    resolved = sum(1 for s in statuses if s in _RESOLVED_STATUSES)
    resolution_rate = (resolved / len(statuses)) * 100.0
    return SustainabilityComponent(
        name="civic_performance",
        score=round(_clamp(resolution_rate), 1),
        classification="CALCULATED",
        note=(
            f"{resolved}/{len(statuses)} on-record civic issues resolved or " "closed."
        ),
    )


def _score_mobility() -> SustainabilityComponent:
    return _unavailable(
        "mobility",
        "No city-wide mobility aggregate exists in this platform — "
        "app.services.traffic_provider and app.services.route_comparison "
        "operate per-corridor/per-route, not as a single city-level figure. "
        "Reported unavailable rather than approximated.",
    )


async def compute_city_sustainability_score(
    session: AsyncSession, city: str
) -> CitySustainabilityScore:
    """Aggregate this platform's existing services into one composite
    city sustainability score. Never fabricates a value for a component
    the city genuinely has no data for — see module docstring.
    """
    components = [
        await _score_air_quality(session, city),
        await _score_energy(session, city),
        await _score_carbon(session, city),
        await _score_waste_circularity(session, city),
        await _score_water(session, city),
        await _score_heat(session, city),
        await _score_green_infrastructure(session, city),
        await _score_civic_performance(session, city),
        _score_mobility(),
    ]

    available = [c for c in components if c.score is not None]
    overall_score = (
        round(sum(c.score for c in available) / len(available), 1)
        if available
        else None
    )

    return CitySustainabilityScore(
        city=city,
        overall_score=overall_score,
        indicators_available=len(available),
        indicators_total=len(_COMPONENT_NAMES),
        components=components,
    )
