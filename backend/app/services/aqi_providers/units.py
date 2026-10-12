"""Unit normalisation for provider pollutant readings (Week 2, D3).

Documented internal unit convention (the contract used by AQIReading and by the
CPCB breakpoint tables in workers/tasks/aqi_ingestion.py):

    pm25, pm10, no2, so2, o3 : ug/m3
    co                       : mg/m3      (CPCB CO breakpoints are in mg/m3)

Providers report other units (OpenAQ v3 `parameter.units` can be ug/m3, ppm,
ppb, mg/m3 ...). Conversion happens ONLY here, at the provider boundary.
Gas ppb/ppm -> mass concentration uses 25 degC and 1 atm (molar volume
24.45 L/mol), the convention OpenAQ itself documents. Unknown/unsupported
units are rejected (None) rather than guessed, because a CO value in ug/m3
interpreted as mg/m3 would be ~1000x too large.
"""

from dataclasses import dataclass

MOLAR_VOLUME_L_PER_MOL = 24.45  # 25 degC, 1 atm
MOLECULAR_WEIGHT = {"no2": 46.0055, "so2": 64.066, "o3": 47.9982, "co": 28.0101}
PARTICULATE = ("pm25", "pm10")
GASES = tuple(MOLECULAR_WEIGHT)

# Physical-plausibility ceilings in the INTERNAL units. Values above these (or
# below 0) are treated as invalid sensor output, not as extreme pollution.
MAX_PLAUSIBLE = {
    "pm25": 2000.0,
    "pm10": 5000.0,
    "no2": 5000.0,
    "so2": 5000.0,
    "o3": 2000.0,
    "co": 500.0,
}


@dataclass(frozen=True)
class Normalised:
    value: float | None
    reason: str | None = None  # populated only when value is None
    assumed_units: bool = False  # True if units were absent and PM assumed ug/m3


def canonical_unit(raw: str | None) -> str | None:
    if raw is None:
        return None
    u = raw.strip().lower().replace("µ", "u").replace("μ", "u")
    u = u.replace("³", "3").replace("^", "").replace(" ", "")
    aliases = {
        "ug/m3": "ug/m3",
        "mg/m3": "mg/m3",
        "ng/m3": "ng/m3",
        "ppm": "ppm",
        "ppb": "ppb",
    }
    return aliases.get(u)


def normalise_reading(param: str, value: float, units: str | None) -> Normalised:
    """Convert `value` for pollutant `param` from `units` into internal units."""
    if value != value or value in (float("inf"), float("-inf")):
        return Normalised(None, "non_finite")
    if value < 0:
        return Normalised(None, "negative")

    unit = canonical_unit(units)
    assumed = False
    if unit is None:
        if units not in (None, "") and units.strip():
            return Normalised(None, f"unsupported_units:{units}")
        if param in PARTICULATE:
            unit, assumed = "ug/m3", True  # OpenAQ documents PM as ug/m3
        else:
            return Normalised(None, "units_missing_for_gas")

    if param in PARTICULATE:
        factor = {"ug/m3": 1.0, "mg/m3": 1000.0, "ng/m3": 0.001}.get(unit)
        if factor is None:
            return Normalised(None, f"invalid_units_for_{param}:{unit}")
        out = value * factor
    elif param in GASES:
        mw = MOLECULAR_WEIGHT[param]
        if unit == "ug/m3":
            ug = value
        elif unit == "mg/m3":
            ug = value * 1000.0
        elif unit == "ng/m3":
            ug = value / 1000.0
        elif unit == "ppb":
            ug = value * mw / MOLAR_VOLUME_L_PER_MOL
        elif unit == "ppm":
            ug = value * 1000.0 * mw / MOLAR_VOLUME_L_PER_MOL
        else:  # pragma: no cover - canonical_unit() is exhaustive
            return Normalised(None, f"unsupported_units:{unit}")
        out = ug / 1000.0 if param == "co" else ug
    else:
        return Normalised(None, f"unknown_parameter:{param}")

    if out > MAX_PLAUSIBLE[param]:
        return Normalised(None, "above_plausible_maximum")
    return Normalised(out, None, assumed)
