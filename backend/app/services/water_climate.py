"""Water–Climate Intelligence.

Two genuinely different kinds of input, kept explicitly separate per the
platform's provenance rules:

A. LIVE weather/climate signal — current precipitation, temperature, and
   humidity via app.services.weather_provider (Open-Meteo, reused from
   Urban Heat Intelligence, not duplicated). A real live reading.

B. Admin-entered municipal water data — reservoir level, consumption,
   groundwater depth — from app.models.water_resource.CityWaterResource.
   There is no universal free real-time municipal-water API (the same
   conclusion already reached for energy/waste), so these figures follow
   the same integrity rule as WardDemographics: no seeded default, source
   cited, and a metric that isn't on file is excluded rather than assumed.

Flood-conducive-conditions and drought risk are CALCULATED from whichever
of (A) and (B) are actually available — never fabricated when a required
input is missing. Neither is a hydrological/flood-forecast model; both are
disclosed as simplified, documented heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

METHODOLOGY = (
    "Flood-conducive-conditions is CALCULATED from live current-hour "
    "precipitation intensity only — it is a simplified, documented "
    "heuristic (not the IMD's official 24-hour rainfall classification, "
    "and not a hydrological flood-forecast model): >=15 mm/hr 'severe', "
    ">=7.5 mm/hr 'high', >=2.5 mm/hr 'moderate', otherwise 'low'. Drought "
    "risk and water stress are CALCULATED from the admin-entered reservoir "
    "level only (reservoir_level_pct < 20% 'severe', < 40% 'high', < 60% "
    "'moderate', otherwise 'low') and are reported Unavailable when no "
    "reservoir figure is on file — never assumed from rainfall alone, "
    "since this platform has no reservoir-inflow model. No 'rainfall "
    "anomaly' is computed: this platform has no historical climatological "
    "normal to compare against."
)


class RiskBand(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    SEVERE = "severe"


def _flood_band(precipitation_mm: float) -> RiskBand:
    if precipitation_mm >= 15.0:
        return RiskBand.SEVERE
    if precipitation_mm >= 7.5:
        return RiskBand.HIGH
    if precipitation_mm >= 2.5:
        return RiskBand.MODERATE
    return RiskBand.LOW


def _reservoir_band(reservoir_level_pct: float) -> RiskBand:
    # Lower reservoir level -> higher drought/water-stress risk.
    if reservoir_level_pct < 20.0:
        return RiskBand.SEVERE
    if reservoir_level_pct < 40.0:
        return RiskBand.HIGH
    if reservoir_level_pct < 60.0:
        return RiskBand.MODERATE
    return RiskBand.LOW


@dataclass
class WaterClimateAssessment:
    city: str
    latitude: float
    longitude: float

    precipitation_mm: float | None
    temperature_c: float | None
    relative_humidity_pct: float | None
    weather_observed_at: datetime | None
    weather_provider: str | None
    weather_available: bool

    reservoir_level_pct: float | None
    water_consumption_mld: float | None
    groundwater_level_m: float | None
    municipal_data_as_of: date | None
    municipal_data_available: bool

    flood_conducive_risk: RiskBand | None
    drought_risk: RiskBand | None
    water_stress: RiskBand | None

    rationale: list[str]
    methodology: str = field(default=METHODOLOGY)


def assess_water_climate(
    *,
    city: str,
    latitude: float,
    longitude: float,
    precipitation_mm: float | None = None,
    temperature_c: float | None = None,
    relative_humidity_pct: float | None = None,
    weather_observed_at: datetime | None = None,
    weather_provider: str | None = None,
    reservoir_level_pct: float | None = None,
    water_consumption_mld: float | None = None,
    groundwater_level_m: float | None = None,
    municipal_data_as_of: date | None = None,
) -> WaterClimateAssessment:
    weather_available = precipitation_mm is not None
    municipal_data_available = reservoir_level_pct is not None

    rationale: list[str] = []

    flood_conducive_risk: RiskBand | None = None
    if weather_available:
        flood_conducive_risk = _flood_band(precipitation_mm)
        rationale.append(
            f"Current precipitation {precipitation_mm:.1f} mm/hr places "
            f"flood-conducive-conditions at '{flood_conducive_risk.value}'."
        )
    else:
        rationale.append(
            "Live precipitation data unavailable — no flood-conducive-"
            "conditions assessment could be calculated."
        )

    drought_risk: RiskBand | None = None
    water_stress: RiskBand | None = None
    if municipal_data_available:
        drought_risk = _reservoir_band(reservoir_level_pct)
        water_stress = drought_risk  # same reservoir-derived band in this simple model
        rationale.append(
            f"Reservoir level {reservoir_level_pct:.0f}% places drought risk "
            f"and water stress at '{drought_risk.value}'"
            + (
                f" (as of {municipal_data_as_of.isoformat()})."
                if municipal_data_as_of
                else " (no data-as-of date on file)."
            )
        )
    else:
        rationale.append(
            "No admin-entered reservoir level on file for this city — "
            "drought risk and water stress are Unavailable, not assumed "
            "from rainfall alone."
        )

    return WaterClimateAssessment(
        city=city,
        latitude=latitude,
        longitude=longitude,
        precipitation_mm=precipitation_mm,
        temperature_c=temperature_c,
        relative_humidity_pct=relative_humidity_pct,
        weather_observed_at=weather_observed_at,
        weather_provider=weather_provider,
        weather_available=weather_available,
        reservoir_level_pct=reservoir_level_pct,
        water_consumption_mld=water_consumption_mld,
        groundwater_level_m=groundwater_level_m,
        municipal_data_as_of=municipal_data_as_of,
        municipal_data_available=municipal_data_available,
        flood_conducive_risk=flood_conducive_risk,
        drought_risk=drought_risk,
        water_stress=water_stress,
        rationale=rationale,
    )
