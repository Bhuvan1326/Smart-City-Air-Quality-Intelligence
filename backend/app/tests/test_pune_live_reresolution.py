from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.aqi_providers import pune_stations
from app.tests.test_helpers import make_db_session
from app.workers.tasks import aqi_ingestion

HADAPSAR_SPEC = next(
    s for s in pune_stations.REQUIRED_STATIONS if s.station_code == "PUNE_LIVE_HADAPSAR"
)


# ─── pune_stations.match_station: recency + exclusion ───────────────────


def test_match_station_prefers_more_recently_active_duplicate():
    """When two candidates both match on name+provider+coordinates (a
    genuine OpenAQ duplicate: an old decommissioned record and a newer
    active one sharing the same station name), the one OpenAQ itself
    last saw data from more recently must win — not an arbitrary/
    distance-only tiebreak that could pick the dead one forever."""
    old_but_closer = {
        "id": 111,
        "name": "Hadapsar, Pune - IITM",
        "owner": {"name": "IITM"},
        "coordinates": {"latitude": 18.5089, "longitude": 73.9259},
        "datetimeLast": {"utc": "2022-07-21T04:45:00Z"},
    }
    active_but_farther = {
        "id": 222,
        "name": "Hadapsar, Pune - IITM",
        "owner": {"name": "IITM"},
        "coordinates": {"latitude": 18.5150, "longitude": 73.9300},
        "datetimeLast": {"utc": "2026-09-08T14:30:00Z"},
    }
    match = pune_stations.match_station(
        [old_but_closer, active_but_farther], HADAPSAR_SPEC
    )
    assert match is not None
    assert match["id"] == 222


def test_match_station_falls_back_to_distance_without_recency_data():
    """Existing behavior is preserved when no candidate exposes
    `datetimeLast` at all: nearest to the approximate point still wins."""
    near = {
        "id": 1,
        "name": "Hadapsar, Pune - IITM",
        "owner": {"name": "IITM"},
        "coordinates": {"latitude": 18.5089, "longitude": 73.9259},
    }
    far = {
        "id": 2,
        "name": "Hadapsar, Pune - IITM",
        "owner": {"name": "IITM"},
        "coordinates": {"latitude": 18.5300, "longitude": 73.9400},
    }
    match = pune_stations.match_station([far, near], HADAPSAR_SPEC)
    assert match is not None
    assert match["id"] == 1


def test_match_station_recency_never_overrides_a_name_mismatch():
    """A candidate with a very recent `datetimeLast` but a name that
    doesn't correspond to the required station at all must still be
    rejected outright — recency is only ever a tiebreaker among
    candidates that already passed name+provider+sanity matching."""
    candidates = [
        {
            "id": 1,
            "name": "Completely Unrelated Location",
            "owner": {"name": "IITM"},
            "coordinates": {"latitude": 18.5089, "longitude": 73.9259},
            "datetimeLast": {"utc": "2026-09-08T14:30:00Z"},
        }
    ]
    assert pune_stations.match_station(candidates, HADAPSAR_SPEC) is None


def test_match_station_malformed_datetime_last_is_ignored_not_fatal():
    """An unparseable `datetimeLast` on one candidate must not crash
    matching — that candidate is simply treated as having no recency
    signal, falling through to the distance tiebreak against the other."""
    malformed = {
        "id": 1,
        "name": "Hadapsar, Pune - IITM",
        "owner": {"name": "IITM"},
        "coordinates": {"latitude": 18.5089, "longitude": 73.9259},
        "datetimeLast": {"utc": "not-a-real-timestamp"},
    }
    other = {
        "id": 2,
        "name": "Hadapsar, Pune - IITM",
        "owner": {"name": "IITM"},
        "coordinates": {"latitude": 18.5300, "longitude": 73.9400},
    }
    match = pune_stations.match_station([malformed, other], HADAPSAR_SPEC)
    assert match is not None
    assert match["id"] == 1  # nearer of the two once neither has usable recency


def test_match_station_exclude_location_ids_drops_stuck_candidate():
    stuck = {
        "id": 555,
        "name": "Hadapsar, Pune - IITM",
        "owner": {"name": "IITM"},
        "coordinates": {"latitude": 18.5089, "longitude": 73.9259},
    }
    assert (
        pune_stations.match_station([stuck], HADAPSAR_SPEC, exclude_location_ids={555})
        is None
    )

    alternative = {
        "id": 777,
        "name": "Hadapsar, Pune - IITM",
        "owner": {"name": "IITM"},
        "coordinates": {"latitude": 18.5090, "longitude": 73.9260},
    }
    match = pune_stations.match_station(
        [stuck, alternative], HADAPSAR_SPEC, exclude_location_ids={555}
    )
    assert match is not None
    assert match["id"] == 777


@pytest.mark.parametrize(
    "spec", pune_stations.REQUIRED_STATIONS, ids=lambda s: s.station_code
)
def test_match_station_matches_each_required_station_by_its_own_name(spec):
    """Sanity check across all six required stations, not just Hadapsar —
    each one's own display name (as OpenAQ would plausibly render it,
    suffixed with its expected provider) must match its own spec."""
    candidate = {
        "id": 1,
        "name": f"{spec.display_name}, Pune - {spec.provider}",
        "owner": {"name": spec.provider},
        "coordinates": {"latitude": spec.approx_lat, "longitude": spec.approx_lon},
    }
    match = pune_stations.match_station([candidate], spec)
    assert match is not None
    assert match["id"] == 1


# ─── ingestion: re-resolution after a stuck OpenAQ location ────────────


@pytest.mark.asyncio
async def test_ingest_one_pune_station_reresolves_after_cooldown_elapses():
    """The actual fix: a station stuck on a dead OpenAQ location for
    longer than the configured cooldown must be re-matched to a
    DIFFERENT location and successfully ingest from it in the same run,
    rather than polling the dead one forever."""
    session = make_db_session()
    stale_since = datetime.now(UTC) - timedelta(hours=25)
    existing_station = SimpleNamespace(
        id="station-uuid",
        station_code=HADAPSAR_SPEC.station_code,
        openaq_location_id=555,
        name="Hadapsar",
        latitude=18.5089,
        longitude=73.9259,
        openaq_location_stale_since=stale_since,
    )
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = existing_station
    latest_result = MagicMock()
    latest_result.scalar_one_or_none.return_value = None
    update_result = MagicMock()
    session.execute = AsyncMock(
        side_effect=[lookup_result, latest_result, update_result]
    )
    session.flush = AsyncMock()

    new_candidate = {
        "id": 777,
        "name": "Hadapsar, Pune - IITM",
        "owner": {"name": "IITM"},
        "coordinates": {"latitude": 18.5089, "longitude": 73.9259},
    }
    live = SimpleNamespace(
        pm25=60.0,
        pm10=100.0,
        no2=18.0,
        so2=4.0,
        co=1.0,
        o3=12.0,
        temperature=27.0,
        humidity=44.0,
        wind_speed=2.0,
        wind_direction=200.0,
        openaq_location_id=777,
        openaq_location_name="Hadapsar, Pune - IITM",
        distance_meters=0.0,
        observed_at=datetime.now(UTC),
    )

    fetch_calls: list[int] = []

    async def fake_fetch(location_id, name):
        fetch_calls.append(location_id)
        return live if location_id == 777 else None

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
            new=AsyncMock(return_value=[new_candidate]),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.pune_stations.match_station",
            return_value=new_candidate,
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(side_effect=fake_fetch),
        ),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, HADAPSAR_SPEC)

    assert outcome == "inserted"
    assert existing_station.openaq_location_id == 777
    assert existing_station.openaq_location_stale_since is None
    assert fetch_calls == [777]


@pytest.mark.asyncio
async def test_ingest_one_pune_station_does_not_reresolve_within_cooldown():
    """A station that's only recently started failing (well within the
    re-resolution cooldown) must keep polling its existing location —
    the comparatively expensive search endpoint must not be hit on
    every single tick."""
    session = make_db_session()
    stale_since = datetime.now(UTC) - timedelta(hours=1)
    existing_station = SimpleNamespace(
        id="station-uuid",
        station_code=HADAPSAR_SPEC.station_code,
        openaq_location_id=555,
        name="Hadapsar",
        latitude=18.5089,
        longitude=73.9259,
        openaq_location_stale_since=stale_since,
    )
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = existing_station
    session.execute = AsyncMock(return_value=lookup_result)

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
            new=AsyncMock(),
        ) as mock_search,
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=None),
        ) as mock_fetch,
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, HADAPSAR_SPEC)

    mock_search.assert_not_called()
    mock_fetch.assert_awaited_once_with(555, "Hadapsar")
    assert outcome == "no_current_observation"
    assert existing_station.openaq_location_id == 555
    assert existing_station.openaq_location_stale_since is not None


@pytest.mark.asyncio
async def test_ingest_one_pune_station_reresolution_no_better_candidate_keeps_old_location():
    """Cooldown elapsed, but nothing better is currently available —
    must keep the existing location (never fabricate, never guess) and
    restart the cooldown clock rather than re-searching every tick."""
    session = make_db_session()
    stale_since = datetime.now(UTC) - timedelta(hours=30)
    existing_station = SimpleNamespace(
        id="station-uuid",
        station_code=HADAPSAR_SPEC.station_code,
        openaq_location_id=555,
        name="Hadapsar",
        latitude=18.5089,
        longitude=73.9259,
        openaq_location_stale_since=stale_since,
    )
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = existing_station
    session.execute = AsyncMock(return_value=lookup_result)

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=None),
        ),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, HADAPSAR_SPEC)

    assert outcome == "no_current_observation"
    assert existing_station.openaq_location_id == 555
    assert existing_station.openaq_location_stale_since > stale_since


@pytest.mark.asyncio
async def test_ingest_one_pune_station_clears_stale_marker_on_recovery():
    """A station that was marked failing but this run produced a
    genuinely current reading must have its stale marker cleared, even
    though the cooldown never elapsed — a future transient gap should
    start its own fresh cooldown, not inherit an old one."""
    session = make_db_session()
    stale_since = datetime.now(UTC) - timedelta(hours=1)
    existing_station = SimpleNamespace(
        id="station-uuid",
        station_code=HADAPSAR_SPEC.station_code,
        openaq_location_id=555,
        name="Hadapsar",
        latitude=18.5089,
        longitude=73.9259,
        openaq_location_stale_since=stale_since,
    )
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = existing_station
    latest_result = MagicMock()
    latest_result.scalar_one_or_none.return_value = None
    update_result = MagicMock()
    session.execute = AsyncMock(
        side_effect=[lookup_result, latest_result, update_result]
    )
    session.flush = AsyncMock()

    live = SimpleNamespace(
        pm25=50.0,
        pm10=80.0,
        no2=10.0,
        so2=3.0,
        co=1.0,
        o3=10.0,
        temperature=25.0,
        humidity=50.0,
        wind_speed=2.0,
        wind_direction=180.0,
        openaq_location_id=555,
        openaq_location_name="Hadapsar",
        distance_meters=0.0,
        observed_at=datetime.now(UTC),
    )
    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
        new=AsyncMock(return_value=live),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, HADAPSAR_SPEC)

    assert outcome == "inserted"
    assert existing_station.openaq_location_stale_since is None


@pytest.mark.asyncio
async def test_ingest_one_pune_station_sets_stale_marker_on_first_failure():
    """A station with no stale marker yet (e.g. an ORM row created
    before this cooldown tracking existed) that fails must have the
    marker set for the first time, so a future persistent failure can
    eventually trigger re-resolution."""
    session = make_db_session()
    existing_station = SimpleNamespace(
        id="station-uuid",
        station_code=HADAPSAR_SPEC.station_code,
        openaq_location_id=555,
        name="Hadapsar",
        latitude=18.5089,
        longitude=73.9259,
        # openaq_location_stale_since intentionally absent.
    )
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = existing_station
    session.execute = AsyncMock(return_value=lookup_result)

    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
        new=AsyncMock(return_value=None),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, HADAPSAR_SPEC)

    assert outcome == "no_current_observation"
    assert existing_station.openaq_location_stale_since is not None


@pytest.mark.asyncio
async def test_ingest_one_pune_station_reresolution_integrity_error_reports_conflict():
    """If re-resolution finds a candidate that another required station
    already owns, the unique-constraint violation must be handled the
    same conservative way as initial resolution: a full rollback and a
    clear conflict outcome, never a crash or a fabricated reading."""
    session = make_db_session()
    stale_since = datetime.now(UTC) - timedelta(hours=30)
    existing_station = SimpleNamespace(
        id="station-uuid",
        station_code=HADAPSAR_SPEC.station_code,
        openaq_location_id=555,
        name="Hadapsar",
        latitude=18.5089,
        longitude=73.9259,
        openaq_location_stale_since=stale_since,
    )
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = existing_station
    session.execute = AsyncMock(return_value=lookup_result)
    session.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    session.rollback = AsyncMock()

    new_candidate = {
        "id": 888,
        "name": "Hadapsar, Pune - IITM",
        "owner": {"name": "IITM"},
        "coordinates": {"latitude": 18.5089, "longitude": 73.9259},
    }
    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
            new=AsyncMock(return_value=[new_candidate]),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.pune_stations.match_station",
            return_value=new_candidate,
        ),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, HADAPSAR_SPEC)

    assert outcome == "unresolved_location_id_conflict"
    session.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_one_pune_station_rejects_match_missing_coordinates():
    """A matched OpenAQ location with no usable coordinates can't be
    placed on the map or trusted — must report unresolved rather than
    persist a half-real station row."""
    session = make_db_session()
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=lookup_result)

    bad_candidate = {
        "id": 42,
        "name": "Hadapsar, Pune - IITM",
        "owner": {"name": "IITM"},
        # No "coordinates" key at all.
    }
    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
            new=AsyncMock(return_value=[bad_candidate]),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.pune_stations.match_station",
            return_value=bad_candidate,
        ),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, HADAPSAR_SPEC)

    assert outcome == "unresolved_invalid_location_data"
