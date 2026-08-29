"""Unit tests for civic_duplicate_detection. Uses a fake in-memory
"session" (a minimal stand-in) rather than the real DB, since the query
here is simple enough to fake deterministically and keep this test pure.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.models.civic_issue import CivicIssueCluster
from app.services.civic_duplicate_detection import find_matching_cluster


def _make_session_with_clusters(clusters: list[CivicIssueCluster]) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = clusters
    session.execute = AsyncMock(return_value=result)
    return session


def _cluster(lat: float, lon: float, last_reported_at: datetime) -> CivicIssueCluster:
    return CivicIssueCluster(
        city="Pune",
        ward_id="W01",
        issue_type="pothole",
        centroid_latitude=lat,
        centroid_longitude=lon,
        report_count=1,
        first_reported_at=last_reported_at,
        last_reported_at=last_reported_at,
    )


@pytest.mark.asyncio
async def test_nearby_recent_report_matches_existing_cluster():
    now = datetime.now(UTC)
    existing = _cluster(18.5204, 73.8567, now - timedelta(hours=1))
    session = _make_session_with_clusters([existing])

    match = await find_matching_cluster(
        session,
        city="Pune",
        issue_type="pothole",
        latitude=18.5205,  # ~11m away
        longitude=73.8567,
        now=now,
    )
    assert match is not None
    assert match.cluster is existing


@pytest.mark.asyncio
async def test_far_away_report_does_not_match():
    now = datetime.now(UTC)
    existing = _cluster(18.5204, 73.8567, now - timedelta(hours=1))
    session = _make_session_with_clusters([existing])

    match = await find_matching_cluster(
        session,
        city="Pune",
        issue_type="pothole",
        latitude=18.60,  # far away
        longitude=73.95,
        now=now,
    )
    assert match is None


@pytest.mark.asyncio
async def test_no_existing_clusters_returns_none():
    session = _make_session_with_clusters([])
    match = await find_matching_cluster(
        session,
        city="Pune",
        issue_type="garbage",
        latitude=18.5204,
        longitude=73.8567,
        now=datetime.now(UTC),
    )
    assert match is None


@pytest.mark.asyncio
async def test_closest_cluster_chosen_when_multiple_match():
    now = datetime.now(UTC)
    near = _cluster(18.52041, 73.85671, now)
    far = _cluster(18.52048, 73.85678, now)
    session = _make_session_with_clusters([far, near])

    match = await find_matching_cluster(
        session,
        city="Pune",
        issue_type="pothole",
        latitude=18.5204,
        longitude=73.8567,
        now=now,
    )
    assert match is not None
    assert match.cluster is near
