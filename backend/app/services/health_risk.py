"""Health-risk intelligence derived from AQI/pollutant readings.

This module produces environmental/health-risk *guidance*, not a medical
diagnosis. It is a deterministic rules engine over CPCB-style breakpoints —
no ML, no patient data, no individual health inputs. Every function here is
pure (no I/O) so it can be unit-tested without a database.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


# (upper_bound_inclusive, RiskLevel) breakpoints per pollutant, in the same
# unit the sensors report in (µg/m³, mg/m³ for CO). Sourced from CPCB
# 24-hour "unhealthy" style breakpoints, the same convention used for the
# alert thresholds feature.
_POLLUTANT_BREAKPOINTS: dict[str, list[tuple[float, RiskLevel]]] = {
    "pm25": [(30, RiskLevel.LOW), (60, RiskLevel.MODERATE), (90, RiskLevel.HIGH), (float("inf"), RiskLevel.VERY_HIGH)],
    "pm10": [(50, RiskLevel.LOW), (100, RiskLevel.MODERATE), (250, RiskLevel.HIGH), (float("inf"), RiskLevel.VERY_HIGH)],
    "no2": [(40, RiskLevel.LOW), (80, RiskLevel.MODERATE), (180, RiskLevel.HIGH), (float("inf"), RiskLevel.VERY_HIGH)],
    "co": [(1, RiskLevel.LOW), (2, RiskLevel.MODERATE), (4, RiskLevel.HIGH), (float("inf"), RiskLevel.VERY_HIGH)],
    "o3": [(50, RiskLevel.LOW), (100, RiskLevel.MODERATE), (168, RiskLevel.HIGH), (float("inf"), RiskLevel.VERY_HIGH)],
    "so2": [(40, RiskLevel.LOW), (80, RiskLevel.MODERATE), (380, RiskLevel.HIGH), (float("inf"), RiskLevel.VERY_HIGH)],
}

_AQI_BREAKPOINTS: list[tuple[float, RiskLevel]] = [
    (50, RiskLevel.LOW),
    (150, RiskLevel.MODERATE),
    (250, RiskLevel.HIGH),
    (float("inf"), RiskLevel.VERY_HIGH),
]

_POLLUTANT_LABELS = {
    "pm25": "PM2.5",
    "pm10": "PM10",
    "no2": "NO2",
    "co": "CO",
    "o3": "O3",
    "so2": "SO2",
}

_POLLUTANT_REASONS = {
    "pm25": "Fine particulate matter penetrates deep into the lungs and bloodstream.",
    "pm10": "Coarse particulate matter irritates airways and worsens respiratory conditions.",
    "no2": "Nitrogen dioxide inflames airways and can reduce lung function.",
    "co": "Carbon monoxide reduces the blood's ability to carry oxygen.",
    "o3": "Ground-level ozone irritates the respiratory system, especially during exertion.",
    "so2": "Sulfur dioxide irritates the airways and can trigger bronchoconstriction.",
}

_LEVEL_PRECAUTIONS: dict[RiskLevel, list[str]] = {
    RiskLevel.LOW: [
        "Air quality is generally acceptable for outdoor activity.",
        "No special precautions needed for the general population.",
    ],
    RiskLevel.MODERATE: [
        "Unusually sensitive individuals should consider limiting prolonged outdoor exertion.",
        "Keep an eye on symptoms like coughing or shortness of breath if you spend time outdoors.",
    ],
    RiskLevel.HIGH: [
        "Limit prolonged or heavy outdoor exertion, especially for children, older adults, and people with respiratory or heart conditions.",
        "Consider keeping windows closed during peak pollution hours.",
        "Use a well-fitted mask (e.g. N95) if you must be outdoors for extended periods.",
    ],
    RiskLevel.VERY_HIGH: [
        "Avoid outdoor physical activity where possible.",
        "Sensitive groups should stay indoors with windows closed and air purification if available.",
        "Seek medical attention promptly if you experience breathing difficulty, chest pain, or dizziness.",
    ],
}

_SENSITIVE_GROUP_NOTE = (
    "Children, older adults, pregnant people, and those with asthma, COPD, or heart "
    "disease are more sensitive to air pollution and should take precautions at lower "
    "thresholds than the general population."
)

_LEVEL_ORDER = [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.VERY_HIGH]


def _bucket(value: float, breakpoints: list[tuple[float, RiskLevel]]) -> RiskLevel:
    for upper, level in breakpoints:
        if value <= upper:
            return level
    return breakpoints[-1][1]


@dataclass
class PollutantRisk:
    pollutant: str
    label: str
    value: float
    unit: str
    risk_level: RiskLevel
    reason: str


@dataclass
class HealthRiskAssessment:
    overall_risk: RiskLevel
    aqi: int | None
    pollutant_risks: list[PollutantRisk]
    precautions: list[str]
    sensitive_group_note: str
    generated_at: datetime
    is_estimate: bool  # True if derived from partial/missing pollutant data


_UNITS = {"pm25": "µg/m³", "pm10": "µg/m³", "no2": "µg/m³", "co": "mg/m³", "o3": "µg/m³", "so2": "µg/m³"}


def assess_health_risk(
    *,
    aqi: int | None,
    pm25: float | None = None,
    pm10: float | None = None,
    no2: float | None = None,
    co: float | None = None,
    o3: float | None = None,
    so2: float | None = None,
) -> HealthRiskAssessment:
    """Compute a health-risk assessment from available AQI/pollutant values.

    This is guidance-level reasoning over public breakpoints — it does not
    diagnose or predict any individual's health outcome.
    """
    readings = {"pm25": pm25, "pm10": pm10, "no2": no2, "co": co, "o3": o3, "so2": so2}
    pollutant_risks: list[PollutantRisk] = []
    for key, value in readings.items():
        if value is None:
            continue
        level = _bucket(value, _POLLUTANT_BREAKPOINTS[key])
        pollutant_risks.append(
            PollutantRisk(
                pollutant=key,
                label=_POLLUTANT_LABELS[key],
                value=value,
                unit=_UNITS[key],
                risk_level=level,
                reason=_POLLUTANT_REASONS[key],
            )
        )

    levels: list[RiskLevel] = [p.risk_level for p in pollutant_risks]
    if aqi is not None:
        levels.append(_bucket(aqi, _AQI_BREAKPOINTS))

    if levels:
        overall = max(levels, key=_LEVEL_ORDER.index)
    else:
        overall = RiskLevel.LOW

    is_estimate = aqi is None or len(pollutant_risks) < len(readings)

    return HealthRiskAssessment(
        overall_risk=overall,
        aqi=aqi,
        pollutant_risks=sorted(pollutant_risks, key=lambda p: _LEVEL_ORDER.index(p.risk_level), reverse=True),
        precautions=_LEVEL_PRECAUTIONS[overall],
        sensitive_group_note=_SENSITIVE_GROUP_NOTE,
        generated_at=datetime.now(UTC),
        is_estimate=is_estimate,
    )
