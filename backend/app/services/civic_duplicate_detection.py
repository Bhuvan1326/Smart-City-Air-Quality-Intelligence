"""Duplicate/recurring civic issue detection.

Matches a new report against existing open CivicIssueCluster rows by:
issue_type match + geospatial proximity (haversine, reused from
app.utils.geo — the same helper used by route_comparison.py) + a time
window. Image similarity is NOT implemented (this platform has no
vision-embedding/similarity infrastructure) — this is disclosed here
rather than silently skipped, so the duplicate-detection coverage isn't
overstated.

A match attaches the new report to the existing cluster (incrementing
report_count) instead of creating an independent cluster. No match
creates a brand-new single-report cluster.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models.civic_issue import CivicIssueCluster
from app.utils.geo import haversine_km
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

DUPLICATE_RADIUS_KM = 0.05  # 50 metres
DUPLICATE_TIME_WINDOW_HOURS = 6

METHODOLOGY = (
    f"A new report is matched to an existing open cluster when it shares "
    f"the same issue_type and is within {DUPLICATE_RADIUS_KM * 1000:.0f}m "
    f"and {DUPLICATE_TIME_WINDOW_HOURS}h of the cluster's last report. "
    "Image similarity is NOT used — this platform has no image-embedding "
    "infrastructure, so that signal is disclosed as absent rather than "
    "silently skipped."
)


@dataclass
class DuplicateMatch:
    cluster: CivicIssueCluster
    distance_km: float


async def find_matching_cluster(
    session: AsyncSession,
    *,
    city: str,
    issue_type: str,
    latitude: float,
    longitude: float,
    now: datetime,
) -> DuplicateMatch | None:
    cutoff = now - timedelta(hours=DUPLICATE_TIME_WINDOW_HOURS)
    result = await session.execute(
        select(CivicIssueCluster).where(
            CivicIssueCluster.city == city,
            CivicIssueCluster.issue_type == issue_type,
            CivicIssueCluster.is_deleted.is_(False),
            CivicIssueCluster.last_reported_at >= cutoff,
        )
    )
    candidates = result.scalars().all()

    best: DuplicateMatch | None = None
    for cluster in candidates:
        distance_km = haversine_km(
            latitude, longitude, cluster.centroid_latitude, cluster.centroid_longitude
        )
        if distance_km <= DUPLICATE_RADIUS_KM:
            if best is None or distance_km < best.distance_km:
                best = DuplicateMatch(cluster=cluster, distance_km=distance_km)
    return best
