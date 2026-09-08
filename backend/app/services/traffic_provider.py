"""Traffic level provider.

There is no live traffic API integrated in this platform (confirmed by
inspecting the codebase — TRAFFIC_PROVIDER/TRAFFIC_CSV_PATH were declared in
.env.example but never read anywhere until this module). Two providers are
supported, matching that documented configuration:

- "demo" (default): a deterministic time-of-day traffic-level model, using
  the exact same peak-hour thresholds already baked into the synthetic AQI
  generator in app/workers/tasks/aqi_ingestion.py, so the two stay
  consistent. This is NOT measured traffic — it is a scheduling heuristic.
- "csv": reads (timestamp, ward_id, traffic_level) rows from
  settings.TRAFFIC_CSV_PATH when that file exists. If the file is missing
  or a ward/hour has no matching row, this falls back to the demo model —
  and the result is labeled "demo" for that data point, never silently
  presented as CSV-sourced.

Nothing here is ever labeled "live" — that would misrepresent a scheduling
heuristic or a static CSV as a real-time feed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from app.core.config import BASE_DIR, settings


def resolve_csv_path(path: str) -> Path:
    """Resolve TRAFFIC_CSV_PATH the same way regardless of process cwd
    (uvicorn from backend/, pytest from repo root, or Docker's /app),
    anchoring relative paths to BASE_DIR. Absolute paths pass through.
    """
    p = Path(path)
    return p if p.is_absolute() else (BASE_DIR / p)


class TrafficLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class TrafficDataSource(str, Enum):
    DEMO = "demo"
    CSV = "csv"


@dataclass
class TrafficReading:
    level: TrafficLevel
    source: TrafficDataSource
    note: str


def _demo_traffic_level(timestamp: datetime) -> TrafficLevel:
    """Same peak-hour thresholds used in aqi_ingestion._generate_realistic_reading."""
    hour = timestamp.hour
    if (7 <= hour <= 10) or (17 <= hour <= 20):
        return TrafficLevel.HIGH
    if 0 <= hour <= 5:
        return TrafficLevel.LOW
    return TrafficLevel.MODERATE


_csv_cache: dict[str, list[dict]] | None = None
_csv_cache_path: str | None = None


def _load_csv(path: str) -> list[dict]:
    global _csv_cache, _csv_cache_path
    if _csv_cache is not None and _csv_cache_path == path:
        return _csv_cache

    rows: list[dict] = []
    p = resolve_csv_path(path)
    if p.exists():
        with p.open(newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

    _csv_cache = rows
    _csv_cache_path = path
    return rows


def _csv_traffic_level(
    timestamp: datetime, ward_id: str | None, path: str
) -> TrafficLevel | None:
    """Look up a matching (ward_id, hour) row in the CSV. Expected columns:
    ward_id, hour (0-23), level (low/moderate/high). Returns None if no
    matching row is found — callers should fall back to the demo model.
    """
    rows = _load_csv(path)
    if not rows:
        return None

    for row in rows:
        row_ward = row.get("ward_id", "").strip()
        row_hour = row.get("hour", "").strip()
        row_level = row.get("level", "").strip().lower()
        if not row_level:
            continue
        if row_ward and ward_id and row_ward != ward_id:
            continue
        if row_hour and row_hour.isdigit() and int(row_hour) != timestamp.hour:
            continue
        if row_level in (TrafficLevel.LOW, TrafficLevel.MODERATE, TrafficLevel.HIGH):
            return TrafficLevel(row_level)
    return None


def get_traffic_reading(
    timestamp: datetime, ward_id: str | None = None
) -> TrafficReading:
    """Return a labeled traffic-level estimate for a given time/ward.

    Always returns a result (never raises) — CSV misses fall back to the
    demo model rather than leaving a gap, but the fallback is labeled
    accordingly so it's never confused with a real CSV-sourced value.
    """
    if settings.TRAFFIC_PROVIDER == "csv" and settings.TRAFFIC_CSV_PATH:
        level = _csv_traffic_level(timestamp, ward_id, settings.TRAFFIC_CSV_PATH)
        if level is not None:
            return TrafficReading(
                level=level,
                source=TrafficDataSource.CSV,
                note=f"From {settings.TRAFFIC_CSV_PATH}",
            )
        return TrafficReading(
            level=_demo_traffic_level(timestamp),
            source=TrafficDataSource.DEMO,
            note="No matching row in traffic CSV for this ward/hour — using time-of-day demo model",
        )

    return TrafficReading(
        level=_demo_traffic_level(timestamp),
        source=TrafficDataSource.DEMO,
        note="No live traffic provider configured — deterministic time-of-day model, not measured traffic",
    )


_EXPECTED_CSV_COLUMNS = {"ward_id", "hour", "level"}


@dataclass
class TrafficProviderStatus:
    configured: bool
    note: str


def get_traffic_provider_status() -> TrafficProviderStatus:
    """Report whether a real traffic provider is actively configured and
    usable, for the Data Sources / Transparency page. Re-derives status
    from the same settings and CSV resolution get_traffic_reading() uses,
    so it can never drift from what the running application is doing.
    """
    provider = settings.TRAFFIC_PROVIDER

    if provider == "csv":
        raw_path = settings.TRAFFIC_CSV_PATH
        if not raw_path:
            return TrafficProviderStatus(
                configured=False,
                note=(
                    "TRAFFIC_PROVIDER=csv but TRAFFIC_CSV_PATH is not set — "
                    "there is no file to read, so traffic falls back to the "
                    "synthetic demo time-of-day model."
                ),
            )

        resolved = resolve_csv_path(raw_path)
        if not resolved.exists():
            return TrafficProviderStatus(
                configured=False,
                note=(
                    f"TRAFFIC_PROVIDER=csv but TRAFFIC_CSV_PATH "
                    f"({raw_path!r}, resolved to {resolved}) does not exist "
                    "on this backend/container — traffic falls back to the "
                    "synthetic demo time-of-day model."
                ),
            )

        try:
            with resolved.open(newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = {
                    (c or "").strip().lower() for c in (reader.fieldnames or [])
                }
                first_row = next(reader, None)
        except OSError as exc:
            return TrafficProviderStatus(
                configured=False,
                note=(
                    f"TRAFFIC_PROVIDER=csv but {resolved} could not be read "
                    f"({exc.strerror or exc}) — traffic falls back to the "
                    "synthetic demo time-of-day model."
                ),
            )

        if not _EXPECTED_CSV_COLUMNS.issubset(fieldnames):
            return TrafficProviderStatus(
                configured=False,
                note=(
                    f"TRAFFIC_PROVIDER=csv but {resolved} is missing one or "
                    f"more expected columns ({sorted(_EXPECTED_CSV_COLUMNS)}) "
                    "— traffic falls back to the synthetic demo time-of-day "
                    "model."
                ),
            )

        if first_row is None:
            return TrafficProviderStatus(
                configured=False,
                note=(
                    f"TRAFFIC_PROVIDER=csv but {resolved} has no data rows — "
                    "traffic falls back to the synthetic demo time-of-day "
                    "model."
                ),
            )

        return TrafficProviderStatus(
            configured=True,
            note=(
                f"TRAFFIC_PROVIDER=csv — reading ward/hour/level rows from "
                f"{raw_path}. Rows without a matching ward/hour still fall "
                "back to the demo model for that data point only."
            ),
        )

    if provider == "demo":
        return TrafficProviderStatus(
            configured=False,
            note=(
                "No pluggable live traffic provider is configured "
                "(TRAFFIC_PROVIDER=demo). Traffic influence on AQI and "
                "forecasts is a synthetic time-of-day multiplier "
                "(morning/evening peak factors) built directly into the "
                "ingestion and forecast pipelines. No paid traffic API is "
                "used or required."
            ),
        )

    return TrafficProviderStatus(
        configured=False,
        note=(
            f"TRAFFIC_PROVIDER={provider!r} is not a recognized value "
            "(expected 'demo' or 'csv') — traffic falls back to the "
            "synthetic demo time-of-day model."
        ),
    )
