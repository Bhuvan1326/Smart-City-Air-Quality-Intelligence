"""Urban Energy Intelligence provider.

There is NO universal, free, worldwide real-time city electricity-demand
API (confirmed by inspecting available providers) — so this module never
claims one. What genuinely is available, live, worldwide, on a free tier,
is *grid carbon intensity by geolocation* from Electricity Maps
(https://www.electricitymaps.com/free-tier-api — non-commercial use,
requires a free registered auth-token). That is the one metric this
module can honestly label LIVE.

Provider hierarchy, mirroring app.services.traffic_provider's honesty
rules:

- "live"/"auto": call Electricity Maps' latest-carbon-intensity-by-
  geolocation endpoint. Requires ENERGY_API_KEY + ENERGY_BASE_URL. Never
  raises to the caller — any failure (missing key, timeout, non-200,
  malformed payload) returns None and the caller falls through.
- "auto" then falls back to a local CSV reference dataset
  (ENERGY_CSV_PATH), labeled "latest available — not real-time".
- "csv": CSV-only, no live attempt.
- "demo": a deterministic time-of-day placeholder. Must be selected
  explicitly (ENERGY_PROVIDER=demo) — production modes ("auto"/"live"/
  "csv") NEVER silently fall back to demo values.
- Anything else resolves to UNAVAILABLE with value=None. No value is
  ever fabricated.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import httpx
from app.core.config import settings

_ELECTRICITYMAPS_TIMEOUT_SECONDS = 6.0


class EnergyDataSource(str, Enum):
    LIVE = "live"  # fetched from a live provider this request
    CSV = "csv"  # latest verified value from a local reference dataset
    DEMO = "demo"  # deterministic placeholder — explicitly not measured
    UNAVAILABLE = "unavailable"  # no reliable value obtainable


@dataclass
class EnergyReading:
    metric: str
    value: float | None
    unit: str
    source: EnergyDataSource
    provider: str | None
    observed_at: datetime | None
    note: str


def _demo_grid_carbon_intensity(timestamp: datetime) -> float:
    """Deterministic time-of-day placeholder (gCO2eq/kWh), loosely
    modelled on a coal-heavy grid being dirtier during evening peak
    demand. NOT measured — used only when ENERGY_PROVIDER=demo.
    """
    hour = timestamp.hour
    if 18 <= hour <= 22:
        return 720.0
    if 0 <= hour <= 5:
        return 560.0
    return 650.0


_csv_cache: list[dict] | None = None
_csv_cache_path: str | None = None


def _load_csv(path: str) -> list[dict]:
    global _csv_cache, _csv_cache_path
    if _csv_cache is not None and _csv_cache_path == path:
        return _csv_cache

    rows: list[dict] = []
    p = Path(path)
    if p.exists():
        with p.open(newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

    _csv_cache = rows
    _csv_cache_path = path
    return rows


def _csv_grid_carbon_intensity(
    city: str | None, path: str
) -> tuple[float, datetime] | None:
    """Expected CSV columns: city, timestamp (ISO 8601), gco2_per_kwh.
    Returns the most recent matching row, or None if nothing matches —
    callers must NOT invent a value when this returns None.
    """
    rows = _load_csv(path)
    if not rows:
        return None

    best: tuple[float, datetime] | None = None
    for row in rows:
        row_city = (row.get("city") or "").strip()
        if city and row_city and row_city.lower() != city.lower():
            continue
        raw_value = (row.get("gco2_per_kwh") or "").strip()
        raw_ts = (row.get("timestamp") or "").strip()
        if not raw_value or not raw_ts:
            continue
        try:
            value = float(raw_value)
            ts = datetime.fromisoformat(raw_ts)
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if best is None or ts > best[1]:
            best = (value, ts)
    return best


async def _fetch_live_grid_carbon_intensity(
    latitude: float, longitude: float
) -> tuple[float, datetime] | None:
    """Query Electricity Maps' free-tier latest-carbon-intensity endpoint
    by geolocation. Returns None (never raises) on any failure so callers
    fall back per the provider hierarchy instead of erroring the request.
    """
    if not settings.ENERGY_API_KEY or not settings.ENERGY_BASE_URL:
        return None

    url = f"{settings.ENERGY_BASE_URL.rstrip('/')}/carbon-intensity/latest"
    try:
        async with httpx.AsyncClient(
            timeout=_ELECTRICITYMAPS_TIMEOUT_SECONDS
        ) as client:
            response = await client.get(
                url,
                params={"lat": latitude, "lon": longitude},
                headers={"auth-token": settings.ENERGY_API_KEY},
            )
            if response.status_code != 200:
                return None
            payload = response.json()
    except Exception:  # noqa: BLE001 -- optional live provider, must fail open
        return None

    value = payload.get("carbonIntensity")
    raw_ts = payload.get("datetime")
    if value is None or raw_ts is None:
        return None
    try:
        observed_at = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return float(value), observed_at


async def get_grid_carbon_intensity(
    latitude: float, longitude: float, city: str | None = None
) -> EnergyReading:
    """Provider-hierarchy entry point for grid carbon intensity
    (gCO2eq/kWh): live -> csv (latest verified) -> demo (only if
    explicitly configured) -> unavailable.
    """
    mode = settings.ENERGY_PROVIDER

    if mode in ("auto", "live"):
        live = await _fetch_live_grid_carbon_intensity(latitude, longitude)
        if live is not None:
            value, observed_at = live
            return EnergyReading(
                metric="grid_carbon_intensity",
                value=value,
                unit="gCO2eq/kWh",
                source=EnergyDataSource.LIVE,
                provider="Electricity Maps",
                observed_at=observed_at,
                note="Live grid carbon intensity for this location's electricity zone.",
            )
        if mode == "live":
            return EnergyReading(
                metric="grid_carbon_intensity",
                value=None,
                unit="gCO2eq/kWh",
                source=EnergyDataSource.UNAVAILABLE,
                provider=None,
                observed_at=None,
                note=(
                    "Live energy provider unavailable or not configured "
                    "(set ENERGY_API_KEY/ENERGY_BASE_URL). No value was "
                    "fabricated."
                ),
            )
        # mode == "auto": fall through to csv below

    if mode in ("auto", "csv") and settings.ENERGY_CSV_PATH:
        csv_result = _csv_grid_carbon_intensity(city, settings.ENERGY_CSV_PATH)
        if csv_result is not None:
            value, observed_at = csv_result
            return EnergyReading(
                metric="grid_carbon_intensity",
                value=value,
                unit="gCO2eq/kWh",
                source=EnergyDataSource.CSV,
                provider=f"Local reference dataset ({settings.ENERGY_CSV_PATH})",
                observed_at=observed_at,
                note="Latest available value from a local reference dataset — not real-time.",
            )
        if mode == "csv":
            return EnergyReading(
                metric="grid_carbon_intensity",
                value=None,
                unit="gCO2eq/kWh",
                source=EnergyDataSource.UNAVAILABLE,
                provider=None,
                observed_at=None,
                note=f"No matching row in {settings.ENERGY_CSV_PATH} for this city.",
            )

    if mode == "demo":
        now = datetime.now(UTC)
        return EnergyReading(
            metric="grid_carbon_intensity",
            value=_demo_grid_carbon_intensity(now),
            unit="gCO2eq/kWh",
            source=EnergyDataSource.DEMO,
            provider="Demo model (time-of-day heuristic)",
            observed_at=now,
            note="Explicit demo mode — deterministic placeholder, not a real measurement.",
        )

    return EnergyReading(
        metric="grid_carbon_intensity",
        value=None,
        unit="gCO2eq/kWh",
        source=EnergyDataSource.UNAVAILABLE,
        provider=None,
        observed_at=None,
        note="No live or verified energy data source is configured for this deployment.",
    )
