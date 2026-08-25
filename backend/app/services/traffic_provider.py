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

from app.core.config import settings


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
    p = Path(path)
    if p.exists():
        with p.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

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
