"""Estimated environmental exposure scoring.

Combines pollution severity (from the existing health-risk engine) with
ward population/sensitive-infrastructure counts to estimate where high
pollution overlaps with high population or sensitive public infrastructure.

Deliberately NEVER invents a population figure. If a ward has no
WardDemographics record (population is None), the exposure result is
"unavailable" for the population-weighted score — this module reports that
plainly rather than guessing or defaulting to some assumed density. This is
explicitly an ESTIMATE, not a medical or epidemiological measurement — see
`methodology` on the result, which the API/UI must surface, not bury.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.services.health_risk import RiskLevel, assess_health_risk

METHODOLOGY = (
    "Estimated environmental exposure = pollution severity level (from current "
    "AQI/pollutant readings) combined with population density and sensitive-site "
    "count for the ward, where both are available. Density bands are relative to "
    "this platform's other configured wards, not an absolute standard. This is "
    "NOT a medical or epidemiological exposure measurement — it is a "
    "prioritization heuristic for identifying where elevated pollution overlaps "
    "with higher population or more sensitive public infrastructure."
)


class ExposureLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"
    UNAVAILABLE = "unavailable"


class PopulationBand(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


@dataclass
class ExposureScore:
    ward_id: str
    aqi: int | None
    pollution_risk: RiskLevel
    primary_pollutant: str | None
    population: int | None
    population_band: PopulationBand | None
    sensitive_sites_count: int | None
    exposure_level: ExposureLevel
    is_population_data_configured: bool
    methodology: str = METHODOLOGY


_POLLUTION_SCORE = {
    RiskLevel.LOW: 1,
    RiskLevel.MODERATE: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.VERY_HIGH: 4,
}
_POPULATION_SCORE = {
    PopulationBand.LOW: 1,
    PopulationBand.MODERATE: 2,
    PopulationBand.HIGH: 3,
}


def _population_band(population: int, all_populations: list[int]) -> PopulationBand:
    if len(all_populations) < 2:
        if population >= 100_000:
            return PopulationBand.HIGH
        if population >= 30_000:
            return PopulationBand.MODERATE
        return PopulationBand.LOW

    sorted_pops = sorted(all_populations)
    n = len(sorted_pops)
    lower_third = sorted_pops[n // 3]
    upper_third = sorted_pops[(2 * n) // 3]
    if population >= upper_third:
        return PopulationBand.HIGH
    if population >= lower_third:
        return PopulationBand.MODERATE
    return PopulationBand.LOW


def score_exposure(
    *,
    ward_id: str,
    aqi: int | None,
    pm25: float | None = None,
    pm10: float | None = None,
    no2: float | None = None,
    co: float | None = None,
    o3: float | None = None,
    so2: float | None = None,
    population: int | None = None,
    sensitive_sites_count: int | None = None,
    all_city_populations: list[int] | None = None,
) -> ExposureScore:
    risk = assess_health_risk(
        aqi=aqi, pm25=pm25, pm10=pm10, no2=no2, co=co, o3=o3, so2=so2
    )
    primary_pollutant = risk.pollutant_risks[0].label if risk.pollutant_risks else None

    if population is None:
        return ExposureScore(
            ward_id=ward_id,
            aqi=aqi,
            pollution_risk=risk.overall_risk,
            primary_pollutant=primary_pollutant,
            population=None,
            population_band=None,
            sensitive_sites_count=sensitive_sites_count,
            exposure_level=ExposureLevel.UNAVAILABLE,
            is_population_data_configured=False,
        )

    band = _population_band(population, all_city_populations or [population])
    combined = _POLLUTION_SCORE[risk.overall_risk] + _POPULATION_SCORE[band]
    if sensitive_sites_count and sensitive_sites_count >= 3:
        combined += 1

    if combined <= 2:
        level = ExposureLevel.LOW
    elif combined <= 4:
        level = ExposureLevel.MODERATE
    elif combined <= 6:
        level = ExposureLevel.HIGH
    else:
        level = ExposureLevel.VERY_HIGH

    return ExposureScore(
        ward_id=ward_id,
        aqi=aqi,
        pollution_risk=risk.overall_risk,
        primary_pollutant=primary_pollutant,
        population=population,
        population_band=band,
        sensitive_sites_count=sensitive_sites_count,
        exposure_level=level,
        is_population_data_configured=True,
    )
