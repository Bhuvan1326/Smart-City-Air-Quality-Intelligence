from datetime import datetime
from typing import Literal

from app.schemas.base import BaseSchema


class DataFreshnessKPI(BaseSchema):
    """K1 (docs/week-1/kpi-definitions.md): share of active stations whose latest
    NON-synthetic reading is within the freshness threshold."""

    city: str
    as_of: datetime
    threshold_minutes: int  # K1 freshness threshold (fresh = age <= this)
    live_threshold_minutes: int
    stations_total: int
    stations_live: int  # age <= live threshold (see live_threshold_minutes)
    stations_recent: int  # live threshold < age <= threshold_minutes
    stations_stale: int  # age > threshold_minutes
    # No usable observation: never reported, only synthetic/invalid readings, or
    # an implausible future timestamp.
    stations_unavailable: int
    stations_synthetic_only: int
    fresh_pct: float | None  # None when there are no stations (not 0 %)
    median_age_minutes: float | None
    status: Literal["ok", "no_stations", "no_live_data"]
    definition: str
    caveats: list[str]
