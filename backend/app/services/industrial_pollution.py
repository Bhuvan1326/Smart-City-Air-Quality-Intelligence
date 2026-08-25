"""Industrial pollution intelligence.

Compares current conditions near industrial-type emission sources against
their own historical baseline (same rolling-window convention used by the
anomaly-detection worker), cross-referenced with permit status, violation
history, and ward-level industrial attribution share.

Per the hackathon brief: never identify a specific facility as the
confirmed source of pollution. This module only ever produces "possible
contributing source" language, backed by a list of the specific signals
that support it — same discipline as construction_dust.py and
waste_burning.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.services.health_risk import RiskLevel, assess_health_risk


class DeviationLevel(str, Enum):
    NORMAL = "normal"
    MODERATE = "moderate"
    SIGNIFICANT = "significant"


_DEVIATION_BANDS = [(1.3, DeviationLevel.NORMAL), (1.7, DeviationLevel.MODERATE), (float("inf"), DeviationLevel.SIGNIFICANT)]


def _deviation_level(current: float, baseline: float) -> DeviationLevel:
    if baseline <= 0:
        return DeviationLevel.NORMAL
    ratio = current / baseline
    for upper, level in _DEVIATION_BANDS:
        if ratio <= upper:
            return level
    return DeviationLevel.SIGNIFICANT


@dataclass
class IndustrialZoneAssessment:
    source_name: str
    ward_id: str | None
    current_aqi: int | None
    current_risk: RiskLevel
    historical_baseline_aqi: float | None
    deviation_level: DeviationLevel
    permit_status: str
    violation_count: int
    supporting_observations: list[str]
    status: str
    possible_contributing_source: bool


def assess_industrial_zone(
    *,
    source_name: str,
    ward_id: str | None,
    permit_status: str,
    violation_count: int,
    current_aqi: int | None,
    pm25: float | None = None,
    pm10: float | None = None,
    no2: float | None = None,
    historical_baseline_aqi: float | None = None,
    industrial_attribution_pct: float | None = None,
    nearest_station_distance_km: float | None = None,
) -> IndustrialZoneAssessment:
    risk = assess_health_risk(aqi=current_aqi, pm25=pm25, pm10=pm10, no2=no2)

    deviation = DeviationLevel.NORMAL
    observations: list[str] = []

    if current_aqi is not None and historical_baseline_aqi:
        deviation = _deviation_level(current_aqi, historical_baseline_aqi)
        if deviation != DeviationLevel.NORMAL:
            observations.append(
                f"Current AQI ({current_aqi}) is {deviation.value}ly elevated above the "
                f"historical baseline for this area (~{historical_baseline_aqi:.0f})."
            )
    elif current_aqi is not None:
        observations.append("No historical baseline available for comparison at this site.")

    if permit_status in ("none", "expired", "suspended"):
        observations.append(f"Permit status: {permit_status} — not currently valid.")
    if violation_count > 0:
        observations.append(f"{violation_count} prior violation(s) on record for this site.")
    if industrial_attribution_pct is not None and industrial_attribution_pct >= 20:
        observations.append(
            f"Ward-level attribution model estimates {industrial_attribution_pct:.0f}% of local "
            "pollution from industrial sources."
        )
    if nearest_station_distance_km is not None and nearest_station_distance_km > 3.0:
        observations.append(
            f"Nearest monitoring station is {nearest_station_distance_km:.1f} km away — "
            "readings may not reflect conditions right at this site."
        )

    if not observations:
        observations.append("No elevated deviation or compliance flags currently on record.")

    status = (
        "environmental_anomaly_detected"
        if deviation in (DeviationLevel.MODERATE, DeviationLevel.SIGNIFICANT)
        else "normal"
    )

    possible_contributing_source = deviation != DeviationLevel.NORMAL and (
        permit_status in ("none", "expired", "suspended")
        or violation_count > 0
        or (industrial_attribution_pct is not None and industrial_attribution_pct >= 20)
    )

    return IndustrialZoneAssessment(
        source_name=source_name,
        ward_id=ward_id,
        current_aqi=current_aqi,
        current_risk=risk.overall_risk,
        historical_baseline_aqi=historical_baseline_aqi,
        deviation_level=deviation,
        permit_status=permit_status,
        violation_count=violation_count,
        supporting_observations=observations,
        status=status,
        possible_contributing_source=possible_contributing_source,
    )
