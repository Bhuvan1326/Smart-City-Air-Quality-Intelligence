"""Green infrastructure optimization — ranks areas for tree-planting /
green-corridor investment.

Combines pollution severity, population exposure, traffic level, and
existing green cover into a documented priority score. None of the three
optional inputs (population exposure, traffic, green cover) is ever
assumed or defaulted when it isn't genuinely available — each is scored
only when configured/live data exists, and excluded (with an explicit
rationale line) otherwise. This module never estimates an AQI reduction
from planting — see `impact_disclaimer`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.services.health_risk import RiskLevel, assess_health_risk
from app.services.population_exposure import ExposureLevel
from app.services.traffic_provider import TrafficLevel

METHODOLOGY = (
    "Priority = pollution severity (current AQI/pollutant readings) + population "
    "exposure level (where population data is configured) + traffic level (only "
    "where a genuine live/configured traffic reading exists), minus a green-cover "
    "credit where an existing green-cover percentage is on file for the area. Any "
    "input that isn't genuinely available — population, traffic, or green cover — "
    "is excluded from the score entirely and flagged as such, rather than being "
    "assumed to be zero, average, or any other value."
)

IMPACT_DISCLAIMER = (
    "No specific AQI reduction is estimated for planting trees or building green "
    "corridors here — that would require a validated dispersion/vegetation model, "
    "which is not part of this platform. This ranking identifies where "
    "investment is likely most valuable, not a quantified before/after outcome."
)


class GreenPriority(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class InterventionType(str, Enum):
    ROADSIDE_GREEN_BUFFER = "roadside_green_buffer"
    URBAN_FOREST_OR_PARK = "urban_forest_or_park"
    GENERAL_TREE_PLANTING = "general_tree_planting"


_POLLUTION_SCORE = {
    RiskLevel.LOW: 0,
    RiskLevel.MODERATE: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.VERY_HIGH: 3,
}
_EXPOSURE_SCORE = {
    ExposureLevel.LOW: 0,
    ExposureLevel.MODERATE: 1,
    ExposureLevel.HIGH: 2,
    ExposureLevel.VERY_HIGH: 3,
    ExposureLevel.UNAVAILABLE: 0,
}
_TRAFFIC_SCORE = {TrafficLevel.LOW: 0, TrafficLevel.MODERATE: 1, TrafficLevel.HIGH: 2}


@dataclass
class GreenInfrastructureScore:
    ward_id: str
    aqi: int | None
    pollution_risk: RiskLevel
    exposure_level: ExposureLevel
    traffic_level: TrafficLevel | None
    is_traffic_data_configured: bool
    green_cover_pct: float | None
    is_green_cover_configured: bool
    priority: GreenPriority
    priority_score: int
    recommended_intervention: InterventionType
    rationale: list[str]
    methodology: str = METHODOLOGY
    impact_disclaimer: str = IMPACT_DISCLAIMER


def score_green_infrastructure(
    *,
    ward_id: str,
    aqi: int | None,
    pm25: float | None = None,
    pm10: float | None = None,
    no2: float | None = None,
    co: float | None = None,
    o3: float | None = None,
    exposure_level: ExposureLevel = ExposureLevel.UNAVAILABLE,
    # None means "no genuine live/configured traffic reading exists for
    # this area" — see app.services.traffic_provider, which never labels
    # its scheduling-heuristic/CSV output as "live". A missing traffic
    # reading is excluded from the score, never defaulted to MODERATE or
    # any other assumed level.
    traffic_level: TrafficLevel | None = None,
    green_cover_pct: float | None = None,
) -> GreenInfrastructureScore:
    risk = assess_health_risk(aqi=aqi, pm25=pm25, pm10=pm10, no2=no2, co=co, o3=o3)

    is_traffic_data_configured = traffic_level is not None
    score = (
        _POLLUTION_SCORE[risk.overall_risk]
        + _EXPOSURE_SCORE[exposure_level]
        + (_TRAFFIC_SCORE[traffic_level] if is_traffic_data_configured else 0)
    )

    is_green_cover_configured = green_cover_pct is not None
    if is_green_cover_configured:
        if green_cover_pct < 15:
            score += 2
        elif green_cover_pct < 30:
            score += 1
        elif green_cover_pct >= 50:
            score -= 1

    if score <= 2:
        priority = GreenPriority.LOW
    elif score <= 4:
        priority = GreenPriority.MODERATE
    else:
        priority = GreenPriority.HIGH

    rationale: list[str] = []
    if risk.overall_risk in (RiskLevel.HIGH, RiskLevel.VERY_HIGH):
        rationale.append(f"Pollution severity is {risk.overall_risk.value}.")
    if exposure_level in (ExposureLevel.HIGH, ExposureLevel.VERY_HIGH):
        rationale.append(f"Population exposure estimate is {exposure_level.value}.")
    elif exposure_level == ExposureLevel.UNAVAILABLE:
        rationale.append(
            "Population exposure data not configured for this ward — excluded from score."
        )
    if traffic_level == TrafficLevel.HIGH:
        rationale.append("Traffic level is currently high.")
    elif not is_traffic_data_configured:
        rationale.append(
            "Live traffic data is unavailable and was excluded from the priority score."
        )
    if is_green_cover_configured:
        rationale.append(f"Existing green cover on file: {green_cover_pct:.0f}%.")
    else:
        rationale.append(
            "No green-cover data on file for this ward — excluded from score."
        )

    if traffic_level == TrafficLevel.HIGH and score >= 3:
        intervention = InterventionType.ROADSIDE_GREEN_BUFFER
    elif (
        risk.overall_risk in (RiskLevel.HIGH, RiskLevel.VERY_HIGH)
        and exposure_level in (ExposureLevel.HIGH, ExposureLevel.VERY_HIGH)
        and (
            not is_green_cover_configured
            or (green_cover_pct is not None and green_cover_pct < 30)
        )
    ):
        intervention = InterventionType.URBAN_FOREST_OR_PARK
    else:
        intervention = InterventionType.GENERAL_TREE_PLANTING

    return GreenInfrastructureScore(
        ward_id=ward_id,
        aqi=aqi,
        pollution_risk=risk.overall_risk,
        exposure_level=exposure_level,
        traffic_level=traffic_level,
        is_traffic_data_configured=is_traffic_data_configured,
        green_cover_pct=green_cover_pct,
        is_green_cover_configured=is_green_cover_configured,
        priority=priority,
        priority_score=score,
        recommended_intervention=intervention,
        rationale=rationale,
    )
