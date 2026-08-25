"""Shared data-freshness classification.

Used anywhere the platform surfaces a "live / recent / stale / demo"
label next to environmental data, so the freshness rules (and their
thresholds) are defined in exactly one place. See also
frontend/components/features/DataFreshnessIndicator.tsx, which mirrors
these thresholds for client-rendered timestamps (e.g. countdown-style
displays) — if you change the thresholds here, update that file too.
"""

from datetime import UTC, datetime
from enum import Enum


class FreshnessStatus(str, Enum):
    LIVE = "live"  # observed in the last 10 minutes
    RECENT = "recent"  # observed in the last 2 hours
    STALE = "stale"  # older than 2 hours
    DEMO = "demo"  # synthetic/fallback data, not a real observation
    UNAVAILABLE = "unavailable"  # no timestamp / no data at all

    @property
    def is_reliable(self) -> bool:
        return self in (FreshnessStatus.LIVE, FreshnessStatus.RECENT)


_LIVE_THRESHOLD_MINUTES = 10
_STALE_THRESHOLD_MINUTES = 120


def classify_freshness(
    observed_at: datetime | None, *, is_synthetic: bool = False
) -> FreshnessStatus:
    if is_synthetic:
        return FreshnessStatus.DEMO
    if observed_at is None:
        return FreshnessStatus.UNAVAILABLE

    now = datetime.now(UTC)
    ts = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=UTC)
    age_minutes = (now - ts).total_seconds() / 60

    if age_minutes < 0:
        # Clock skew guard — treat future timestamps as live rather than crash.
        return FreshnessStatus.LIVE
    if age_minutes <= _LIVE_THRESHOLD_MINUTES:
        return FreshnessStatus.LIVE
    if age_minutes <= _STALE_THRESHOLD_MINUTES:
        return FreshnessStatus.RECENT
    return FreshnessStatus.STALE
