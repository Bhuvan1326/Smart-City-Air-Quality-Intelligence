"""Urban Heat-Island Intelligence — heat risk classification and cooling
priority, combining a live current-temperature reading with an optional
satellite vegetation signal.

Data sources (see the two provider modules for their own honesty rules):
- app.services.weather_provider: current air temperature via Open-Meteo —
  a genuine LIVE reading, not a forecast.
- app.services.satellite.sentinel_hub: mean NDVI over a ward's bounding
  box via Sentinel-2 — an OBSERVED satellite value with its own
  (non-real-time) observation date, reused as-is rather than duplicated.

This module does NOT have access to land-surface-temperature (LST)
satellite data or built-up-density figures, so it never reports a
"surface temperature" or "built-up density" value — heat risk here is
CALCULATED from air temperature plus a vegetation-deficit adjustment when
NDVI is available, and the result says explicitly which inputs were used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

METHODOLOGY = (
    "Heat risk is CALCULATED, not measured directly: air temperature is "
    "bucketed into a risk band (loosely aligned with IMD-style heatwave "
    "thresholds for Indian cities), then adjusted upward by one band if "
    "satellite NDVI indicates low vegetation cover (a documented, simplified "
    "heuristic — low vegetation reduces evapotranspirative cooling, but this "
    "is not a calibrated urban-heat-island physical model). This platform "
    "has no land-surface-temperature satellite feed, so no 'surface "
    "temperature' value is ever reported — only air temperature (live) and, "
    "where available, a vegetation signal (satellite-observed, not live)."
)


class HeatRiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    SEVERE = "severe"


_TEMPERATURE_BANDS: list[tuple[float, HeatRiskLevel]] = [
    (30.0, HeatRiskLevel.LOW),
    (35.0, HeatRiskLevel.MODERATE),
    (40.0, HeatRiskLevel.HIGH),
    (float("inf"), HeatRiskLevel.SEVERE),
]

_ESCALATE = {
    HeatRiskLevel.LOW: HeatRiskLevel.MODERATE,
    HeatRiskLevel.MODERATE: HeatRiskLevel.HIGH,
    HeatRiskLevel.HIGH: HeatRiskLevel.SEVERE,
    HeatRiskLevel.SEVERE: HeatRiskLevel.SEVERE,
}

# NDVI below this is treated as "low vegetation" for the escalation rule.
# Healthy urban tree/park cover is typically NDVI > 0.4; sparse/bare urban
# surfaces are usually < 0.2. This threshold is a documented simplification,
# not a calibrated ecological cutoff.
_LOW_NDVI_THRESHOLD = 0.2


@dataclass
class HeatAssessment:
    latitude: float
    longitude: float
    ward_id: str | None
    air_temperature_c: float
    air_temperature_observed_at: datetime
    apparent_temperature_c: float | None
    weather_provider: str
    mean_ndvi: float | None
    ndvi_observed_date: date | None
    vegetation_data_available: bool
    heat_risk: HeatRiskLevel
    base_risk_from_temperature: HeatRiskLevel
    escalated_for_low_vegetation: bool
    cooling_priority: bool
    rationale: list[str]
    methodology: str = field(default=METHODOLOGY)


def _band_for_temperature(temperature_c: float) -> HeatRiskLevel:
    for threshold, level in _TEMPERATURE_BANDS:
        if temperature_c < threshold:
            return level
    return (
        HeatRiskLevel.SEVERE
    )  # pragma: no cover - _TEMPERATURE_BANDS always covers this


def assess_heat_risk(
    *,
    latitude: float,
    longitude: float,
    air_temperature_c: float,
    air_temperature_observed_at: datetime,
    apparent_temperature_c: float | None = None,
    weather_provider: str = "Open-Meteo",
    ward_id: str | None = None,
    mean_ndvi: float | None = None,
    ndvi_observed_date: date | None = None,
) -> HeatAssessment:
    base_risk = _band_for_temperature(air_temperature_c)

    vegetation_data_available = mean_ndvi is not None
    escalate = vegetation_data_available and mean_ndvi < _LOW_NDVI_THRESHOLD
    heat_risk = _ESCALATE[base_risk] if escalate else base_risk

    rationale: list[str] = [
        f"Air temperature {air_temperature_c:.1f}°C places baseline risk at "
        f"'{base_risk.value}'."
    ]
    if vegetation_data_available:
        rationale.append(
            f"Satellite mean NDVI {mean_ndvi:.2f} observed "
            f"{ndvi_observed_date.isoformat() if ndvi_observed_date else 'on file'} "
            + (
                "is below the low-vegetation threshold — risk escalated one band."
                if escalate
                else "does not indicate low vegetation — no escalation applied."
            )
        )
    else:
        rationale.append(
            "No satellite vegetation data available for this location — risk "
            "reflects air temperature only."
        )

    return HeatAssessment(
        latitude=latitude,
        longitude=longitude,
        ward_id=ward_id,
        air_temperature_c=air_temperature_c,
        air_temperature_observed_at=air_temperature_observed_at,
        apparent_temperature_c=apparent_temperature_c,
        weather_provider=weather_provider,
        mean_ndvi=mean_ndvi,
        ndvi_observed_date=ndvi_observed_date,
        vegetation_data_available=vegetation_data_available,
        heat_risk=heat_risk,
        base_risk_from_temperature=base_risk,
        escalated_for_low_vegetation=escalate,
        cooling_priority=heat_risk in (HeatRiskLevel.HIGH, HeatRiskLevel.SEVERE),
        rationale=rationale,
    )
