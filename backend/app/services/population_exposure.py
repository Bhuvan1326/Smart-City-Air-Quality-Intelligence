"""Estimated environmental exposure and vulnerability scoring.

Combines pollution severity (from the existing health-risk engine) with
ward population/sensitive-infrastructure counts to estimate where high
pollution overlaps with high population or sensitive public infrastructure.

Deliberately NEVER invents a population figure. If a ward has no
WardDemographics record (population is None), the exposure result is
"unavailable" for the population-weighted score — this module reports that
plainly rather than guessing or defaulting to some assumed density. This is
explicitly an ESTIMATE, not a medical or epidemiological measurement — see
`methodology` on the result, which the API/UI must surface, not bury.

This module reports THREE distinct, separately-surfaced signals rather than
collapsing them into one number:
  - `pollution_risk`      — current AQI/pollutant severity alone (no
                             population weighting at all).
  - `exposure_level`      — pollution severity combined with how many
                             people are on file as living in the ward
                             (population-weighted exposure).
  - `vulnerability_level` — how susceptible the ward's built environment is
                             to pollution impact, independent of today's
                             AQI: density of sensitive sites (schools,
                             hospitals) and lack of green-cover buffer.
`is_high_risk_area` is a convenience flag surfaced alongside these, true
only when both the pollution-weighted exposure AND the structural
vulnerability are elevated — i.e. an area where current pollution overlaps
with a population that is both large/dense on file AND relies on
sensitive infrastructure / lacks green buffering.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.services.health_risk import RiskLevel, assess_health_risk

METHODOLOGY = (
    "Three separate ESTIMATED signals are reported per ward: (1) pollution "
    "risk — current AQI/pollutant severity alone; (2) estimated population "
    "exposure — pollution severity combined with population density and "
    "sensitive-site count for the ward, where population is on file; (3) "
    "estimated vulnerability — sensitive-site density and lack of existing "
    "green cover, independent of today's AQI. Density bands are relative to "
    "this platform's other configured wards, not an absolute standard. A "
    "ward is flagged high-risk only when both estimated population exposure "
    "and estimated vulnerability are elevated. This is NOT a medical or "
    "epidemiological exposure measurement — it is a prioritization "
    "heuristic for identifying where elevated pollution overlaps with "
    "higher population, more sensitive public infrastructure, or less "
    "green buffering."
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


class VulnerabilityLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNAVAILABLE = "unavailable"


@dataclass
class ExposureScore:
    ward_id: str
    aqi: int | None
    pollution_risk: RiskLevel
    primary_pollutant: str | None
    population: int | None
    population_band: PopulationBand | None
    sensitive_sites_count: int | None
    green_cover_pct: float | None
    exposure_level: ExposureLevel
    vulnerability_level: VulnerabilityLevel
    is_population_data_configured: bool
    is_high_risk_area: bool
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


def _vulnerability_level(
    sensitive_sites_count: int | None, green_cover_pct: float | None
) -> VulnerabilityLevel:
    """Structural vulnerability, independent of today's pollution level.

    Combines two admin-entered, authoritative-sourced factors — density of
    sensitive public infrastructure (schools/hospitals/elder care) and lack
    of existing green cover — into a single band. Reports "unavailable"
    rather than a guess when neither factor is on file for the ward.
    """
    if sensitive_sites_count is None and green_cover_pct is None:
        return VulnerabilityLevel.UNAVAILABLE

    factor_total = 0
    factor_count = 0

    if sensitive_sites_count is not None:
        factor_count += 1
        if sensitive_sites_count >= 5:
            factor_total += 3
        elif sensitive_sites_count >= 2:
            factor_total += 2
        else:
            factor_total += 1

    if green_cover_pct is not None:
        factor_count += 1
        if green_cover_pct < 15:
            factor_total += 3
        elif green_cover_pct < 30:
            factor_total += 2
        else:
            factor_total += 1

    average = factor_total / factor_count
    if average >= 2.5:
        return VulnerabilityLevel.HIGH
    if average >= 1.5:
        return VulnerabilityLevel.MODERATE
    return VulnerabilityLevel.LOW


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
    green_cover_pct: float | None = None,
    all_city_populations: list[int] | None = None,
) -> ExposureScore:
    risk = assess_health_risk(
        aqi=aqi, pm25=pm25, pm10=pm10, no2=no2, co=co, o3=o3, so2=so2
    )
    primary_pollutant = risk.pollutant_risks[0].label if risk.pollutant_risks else None
    vulnerability = _vulnerability_level(sensitive_sites_count, green_cover_pct)

    if population is None:
        return ExposureScore(
            ward_id=ward_id,
            aqi=aqi,
            pollution_risk=risk.overall_risk,
            primary_pollutant=primary_pollutant,
            population=None,
            population_band=None,
            sensitive_sites_count=sensitive_sites_count,
            green_cover_pct=green_cover_pct,
            exposure_level=ExposureLevel.UNAVAILABLE,
            vulnerability_level=vulnerability,
            is_population_data_configured=False,
            is_high_risk_area=False,
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

    is_high_risk = level in (ExposureLevel.HIGH, ExposureLevel.VERY_HIGH) and (
        vulnerability == VulnerabilityLevel.HIGH
        or (
            vulnerability == VulnerabilityLevel.MODERATE
            and level == ExposureLevel.VERY_HIGH
        )
    )

    return ExposureScore(
        ward_id=ward_id,
        aqi=aqi,
        pollution_risk=risk.overall_risk,
        primary_pollutant=primary_pollutant,
        population=population,
        population_band=band,
        sensitive_sites_count=sensitive_sites_count,
        green_cover_pct=green_cover_pct,
        exposure_level=level,
        vulnerability_level=vulnerability,
        is_population_data_configured=True,
        is_high_risk_area=is_high_risk,
    )
