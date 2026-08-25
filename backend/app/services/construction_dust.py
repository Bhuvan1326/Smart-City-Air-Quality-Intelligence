"""Construction & dust pollution intelligence.

Combines existing emission-source records (construction sites, dust
sources — real permit/violation data already in the emission_sources
table) with the nearest station's current PM10/PM2.5 readings to flag
"possible contributing condition," never a confirmed source. Per the
hackathon brief: do not claim construction is the confirmed source of
elevated particulates unless the available data actually supports that
conclusion — this module only ever produces "possible contributing
condition" language, and lists exactly which observations support it so a
human reviewer can judge for themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DustRiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


# PM10 breakpoints, µg/m³ (same convention as health_risk.py / alert thresholds)
_PM10_BREAKPOINTS = [(50, DustRiskLevel.LOW), (150, DustRiskLevel.MODERATE), (float("inf"), DustRiskLevel.HIGH)]


def _pm10_risk(pm10: float) -> DustRiskLevel:
    for upper, level in _PM10_BREAKPOINTS:
        if pm10 <= upper:
            return level
    return DustRiskLevel.HIGH


@dataclass
class ConstructionDustAssessment:
    source_name: str
    source_type: str  # "construction" or "dust"
    ward_id: str | None
    permit_status: str
    violation_count: int
    nearest_station_name: str | None
    nearest_station_distance_km: float | None
    pm10: float | None
    risk_level: DustRiskLevel
    supporting_observations: list[str]
    requires_verification: bool = True


def assess_construction_dust_risk(
    *,
    source_name: str,
    source_type: str,
    ward_id: str | None,
    permit_status: str,
    violation_count: int,
    nearest_station_name: str | None,
    nearest_station_distance_km: float | None,
    pm10: float | None,
    construction_attribution_pct: float | None = None,
    dust_attribution_pct: float | None = None,
) -> ConstructionDustAssessment:
    """Assess one emission source for possible construction/dust contribution.

    Never returns "confirmed" — only a risk level and a list of the specific
    observations that support (or don't support) flagging this site.
    """
    observations: list[str] = []

    if pm10 is None:
        risk = DustRiskLevel.LOW
        observations.append("No recent PM10 reading available near this site.")
    else:
        risk = _pm10_risk(pm10)
        if risk in (DustRiskLevel.MODERATE, DustRiskLevel.HIGH):
            observations.append(f"Elevated PM10 ({pm10:.0f} µg/m³) near this site.")

    if permit_status in ("none", "expired", "suspended"):
        observations.append(f"Permit status: {permit_status} — not currently valid.")
    if violation_count > 0:
        observations.append(f"{violation_count} prior violation(s) on record for this site.")

    relevant_attribution = (
        construction_attribution_pct if source_type == "construction" else dust_attribution_pct
    )
    if relevant_attribution is not None and relevant_attribution >= 20:
        observations.append(
            f"Ward-level attribution model independently estimates "
            f"{relevant_attribution:.0f}% of local pollution from {source_type} sources."
        )

    if nearest_station_distance_km is not None and nearest_station_distance_km > 3.0:
        observations.append(
            f"Nearest monitoring station is {nearest_station_distance_km:.1f} km away — "
            "readings may not reflect conditions right at this site."
        )

    # Escalate risk if the PM10-based band is only moderate but multiple
    # independent signals line up (permit issue + attribution + violations).
    strong_signal_count = sum(
        1
        for cond in (
            permit_status in ("none", "expired", "suspended"),
            violation_count > 0,
            relevant_attribution is not None and relevant_attribution >= 20,
        )
        if cond
    )
    if risk == DustRiskLevel.MODERATE and strong_signal_count >= 2:
        risk = DustRiskLevel.HIGH

    if not observations:
        observations.append("No elevated particulate readings or compliance flags currently on record.")

    return ConstructionDustAssessment(
        source_name=source_name,
        source_type=source_type,
        ward_id=ward_id,
        permit_status=permit_status,
        violation_count=violation_count,
        nearest_station_name=nearest_station_name,
        nearest_station_distance_km=nearest_station_distance_km,
        pm10=pm10,
        risk_level=risk,
        supporting_observations=observations,
    )
