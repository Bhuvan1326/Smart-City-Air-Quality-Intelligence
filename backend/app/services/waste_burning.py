"""Waste-burning detection and circular-economy recommendations.

Combines existing signals — a PM2.5 spike relative to baseline (from the
already-running anomaly detector), proximity to a known biomass-type
emission source, ward-level biomass attribution share, and NASA FIRMS
satellite thermal-hotspot data when configured — into a "possible
waste-burning event" flag. Per the hackathon brief: never automatically
classify an event as confirmed waste burning. `status` is always
"requires_verification" and each triggering signal is listed individually
so a reviewer can judge the evidence.

Circular-economy recommendations (collection, segregation, recycling,
composting, burn prevention) are attached whenever a possible event is
flagged, since they're the appropriate response regardless of whether this
specific event is eventually confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

_PM25_SPIKE_RATIO_THRESHOLD = 1.6  # current vs baseline


class WasteBurningConfidence(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


CIRCULAR_ECONOMY_RECOMMENDATIONS = [
    "Increase waste-collection frequency in this area",
    "Community waste-segregation outreach (wet/dry/hazardous)",
    "Expand access to composting for organic waste",
    "Enforce open-burning prohibition with visible signage and patrols",
    "Connect informal waste pickers to formal recycling channels",
]


@dataclass
class WasteBurningAssessment:
    ward_id: str | None
    detected: str
    supporting_observations: list[str]
    confidence: WasteBurningConfidence
    status: str = "requires_verification"
    circular_economy_recommendations: list[str] = field(default_factory=list)


def assess_waste_burning_risk(
    *,
    ward_id: str | None,
    current_pm25: float | None,
    baseline_pm25: float | None,
    nearest_biomass_source_name: str | None = None,
    nearest_biomass_source_distance_km: float | None = None,
    biomass_attribution_pct: float | None = None,
    satellite_hotspot_nearby: bool = False,
    satellite_configured: bool = False,
) -> WasteBurningAssessment:
    observations: list[str] = []
    signal_count = 0

    pm25_spike = False
    if current_pm25 is not None and baseline_pm25 and baseline_pm25 > 0:
        ratio = current_pm25 / baseline_pm25
        if ratio >= _PM25_SPIKE_RATIO_THRESHOLD:
            pm25_spike = True
            observations.append(
                f"Sudden PM2.5 increase: {current_pm25:.0f} µg/m³ vs a baseline of "
                f"{baseline_pm25:.0f} µg/m³ ({ratio:.1f}x)."
            )
            signal_count += 1

    if nearest_biomass_source_distance_km is not None and nearest_biomass_source_distance_km <= 2.0:
        observations.append(
            f"Known biomass-burning-associated site nearby"
            f"{f' ({nearest_biomass_source_name})' if nearest_biomass_source_name else ''}: "
            f"{nearest_biomass_source_distance_km:.1f} km away."
        )
        signal_count += 1

    if biomass_attribution_pct is not None and biomass_attribution_pct >= 20:
        observations.append(
            f"Ward-level attribution model estimates {biomass_attribution_pct:.0f}% of local "
            "pollution from biomass/open-burning sources."
        )
        signal_count += 1

    if satellite_hotspot_nearby:
        observations.append("NASA FIRMS satellite thermal-anomaly detection nearby (Observed).")
        signal_count += 1
    elif not satellite_configured:
        observations.append(
            "Satellite thermal-hotspot check unavailable — NASA FIRMS is not configured in this deployment."
        )

    if signal_count == 0:
        confidence = WasteBurningConfidence.NONE
        detected = "No waste-burning signal detected"
    elif signal_count == 1:
        confidence = WasteBurningConfidence.LOW
        detected = "Particulate pollution anomaly" if pm25_spike else "Possible waste-burning indicator"
    elif signal_count == 2:
        confidence = WasteBurningConfidence.MODERATE
        detected = "Particulate pollution anomaly with supporting signals"
    else:
        confidence = WasteBurningConfidence.HIGH
        detected = "Particulate pollution anomaly with multiple independent supporting signals"

    recommendations = CIRCULAR_ECONOMY_RECOMMENDATIONS if signal_count > 0 else []

    return WasteBurningAssessment(
        ward_id=ward_id,
        detected=detected,
        supporting_observations=observations,
        confidence=confidence,
        circular_economy_recommendations=recommendations,
    )
