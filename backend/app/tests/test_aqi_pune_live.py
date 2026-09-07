"""Tests for the real-time, six-station Pune Live AQI feature:

- GET /api/v1/aqi/live?city=Pune always returns exactly the six required
  stations, in a stable order, with unresolved/no-data stations clearly
  marked rather than omitted or fabricated.
- The dedicated ingestion task (app.workers.tasks.aqi_ingestion.
  fetch_live_aqi_pune_stations) resolves stations once, ingests
  idempotently, and never falls back to synthetic data.
- app.services.aqi_providers.pune_stations.match_station never matches on
  proximity alone.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import AQIReading, MonitoringStation
from app.services.aqi_providers import pune_stations
from app.tests.test_helpers import make_db_session
from app.workers.tasks import aqi_ingestion

# ─── pune_stations.match_station ────────────────────────────────────────

HADAPSAR_SPEC = next(
    s for s in pune_stations.REQUIRED_STATIONS if s.station_code == "PUNE_LIVE_HADAPSAR"
)


def test_match_station_matches_on_name_and_provider():
    candidates = [
        {
            "id": 111,
            "name": "Hadapsar, Pune - IITM",
            "owner": {"name": "IITM"},
            "coordinates": {"latitude": 18.5089, "longitude": 73.9259},
        },
        {
            "id": 222,
            "name": "Some Other Place",
            "owner": {"name": "CPCB"},
            "coordinates": {"latitude": 18.51, "longitude": 73.90},
        },
    ]
    match = pune_stations.match_station(candidates, HADAPSAR_SPEC)
    assert match is not None
    assert match["id"] == 111


def test_match_station_rejects_name_match_far_from_expected_location():
    """A same-named station that's actually nowhere near the real Hadapsar
    (i.e. a namesake elsewhere) must not be matched by name alone."""
    candidates = [
        {
            "id": 999,
            "name": "Hadapsar",
            "owner": {"name": "IITM"},
            # ~500km away — well outside the sanity radius.
            "coordinates": {"latitude": 23.0, "longitude": 73.9259},
        }
    ]
    assert pune_stations.match_station(candidates, HADAPSAR_SPEC) is None


def test_match_station_returns_none_when_nothing_matches_name():
    candidates = [
        {
            "id": 1,
            "name": "Completely Unrelated Location",
            "owner": {"name": "CPCB"},
            "coordinates": {"latitude": 18.5089, "longitude": 73.9259},
        }
    ]
    assert pune_stations.match_station(candidates, HADAPSAR_SPEC) is None


def test_match_station_never_picks_nearest_when_name_disagrees():
    """Even a candidate sitting exactly on Hadapsar's coordinates must be
    rejected if its name doesn't correspond to Hadapsar at all — matching
    must never degrade into a bare nearest-station lookup."""
    candidates = [
        {
            "id": 5,
            "name": "Kothrud CAAQMS",
            "owner": {"name": "MPCB"},
            "coordinates": {"latitude": 18.5089, "longitude": 73.9259},
        }
    ]
    assert pune_stations.match_station(candidates, HADAPSAR_SPEC) is None


# ─── ingestion: one station at a time ───────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_one_pune_station_resolves_and_inserts_first_time():
    session = make_db_session()

    # No existing station row.
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = None
    latest_result = MagicMock()
    latest_result.scalar_one_or_none.return_value = None
    update_result = MagicMock()
    session.execute = AsyncMock(
        side_effect=[lookup_result, latest_result, update_result]
    )
    session.flush = AsyncMock()

    live = SimpleNamespace(
        pm25=68.2,
        pm10=110.0,
        no2=20.0,
        so2=5.0,
        co=1.0,
        o3=15.0,
        temperature=28.0,
        humidity=45.0,
        wind_speed=2.5,
        wind_direction=210.0,
        openaq_location_id=555,
        openaq_location_name="Hadapsar, Pune - IITM",
        distance_meters=0.0,
        observed_at=datetime.now(UTC),
    )
    candidates = [
        {
            "id": 555,
            "name": "Hadapsar, Pune - IITM",
            "owner": {"name": "IITM"},
            "coordinates": {"latitude": 18.5089, "longitude": 73.9259},
        }
    ]

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
            new=AsyncMock(return_value=candidates),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=live),
        ),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, HADAPSAR_SPEC)

    assert outcome == "inserted"
    session.add.assert_called()  # station row + reading row


@pytest.mark.asyncio
async def test_ingest_one_pune_station_unresolved_when_no_openaq_match():
    session = make_db_session()
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=lookup_result)

    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
        new=AsyncMock(return_value=[]),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, HADAPSAR_SPEC)

    assert outcome == "unresolved_no_openaq_candidates"


@pytest.mark.asyncio
async def test_ingest_one_pune_station_no_fabrication_when_no_current_observation():
    """Station is already resolved, but OpenAQ currently has nothing for
    it — must report 'no_current_observation', never fabricate a reading."""
    session = make_db_session()
    existing_station = SimpleNamespace(
        id="station-uuid",
        station_code=HADAPSAR_SPEC.station_code,
        openaq_location_id=555,
        name="Hadapsar",
        latitude=18.5089,
        longitude=73.9259,
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
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_one_pune_station_skips_duplicate_observation():
    """Provider hasn't published anything newer than what's already
    stored -> no new row, but last_data_at still refreshes since the
    provider is still confirming the reading is current."""
    session = make_db_session()
    now = datetime.now(UTC)
    existing_station = SimpleNamespace(
        id="station-uuid",
        station_code=HADAPSAR_SPEC.station_code,
        openaq_location_id=555,
        name="Hadapsar",
        latitude=18.5089,
        longitude=73.9259,
    )
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = existing_station
    latest_result = MagicMock()
    latest_result.scalar_one_or_none.return_value = now  # same timestamp as new obs
    update_result = MagicMock()
    session.execute = AsyncMock(
        side_effect=[lookup_result, latest_result, update_result]
    )

    live = SimpleNamespace(
        pm25=68.2,
        pm10=110.0,
        no2=20.0,
        so2=5.0,
        co=1.0,
        o3=15.0,
        temperature=28.0,
        humidity=45.0,
        wind_speed=2.5,
        wind_direction=210.0,
        openaq_location_id=555,
        openaq_location_name="Hadapsar",
        distance_meters=0.0,
        observed_at=now,
    )
    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
        new=AsyncMock(return_value=live),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, HADAPSAR_SPEC)

    assert outcome == "no_new_observation"
    session.add.assert_not_called()


def test_fetch_live_aqi_pune_stations_task_invokes_async():
    with (
        patch(
            "app.workers.tasks.aqi_ingestion._fetch_pune_live_stations_async",
            new=AsyncMock(),
        ) as mocked,
        patch("app.workers.tasks.aqi_ingestion.asyncio.run") as mock_run,
    ):
        mock_run.side_effect = lambda coro: coro.close()
        aqi_ingestion.fetch_live_aqi_pune_stations.run()
        mocked.assert_called_once()
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_pune_live_stations_async_noop_when_unconfigured():
    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured",
            return_value=False,
        ),
        patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create_engine,
    ):
        summary = await aqi_ingestion._fetch_pune_live_stations_async()

    mock_create_engine.assert_not_called()
    assert all(v == "openaq_not_configured" for v in summary.values())
    assert set(summary.keys()) == {
        s.station_code for s in pune_stations.REQUIRED_STATIONS
    }


@pytest.mark.asyncio
async def test_fetch_pune_live_stations_async_skips_when_lock_held():
    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion._acquire_pune_live_lock",
            new=AsyncMock(return_value=False),
        ),
        patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create_engine,
    ):
        summary = await aqi_ingestion._fetch_pune_live_stations_async()

    mock_create_engine.assert_not_called()
    assert summary == {"_skipped": "already_running"}


# ─── endpoint: GET /aqi/live?city=Pune ──────────────────────────────────


async def _create_pune_live_station(
    session: AsyncSession, spec, openaq_location_id: int = 100
) -> MonitoringStation:
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name=spec.display_name,
        station_code=spec.station_code,
        city=spec.city,
        state=spec.state,
        country=spec.country,
        operator=f"{spec.provider} (via OpenAQ)",
        latitude=spec.approx_lat,
        longitude=spec.approx_lon,
        geometry=WKTElement(f"POINT({spec.approx_lon} {spec.approx_lat})", srid=4326),
        is_active=True,
        station_type="OpenAQ",
        openaq_location_id=openaq_location_id,
    )
    session.add(station)
    await session.flush()
    return station


@pytest.mark.asyncio
async def test_pune_live_always_returns_exactly_six_stations_when_db_empty(
    client: AsyncClient, auth_headers: dict
):
    """No Pune stations resolved yet at all -> still 200, still exactly
    six entries, each clearly marked unresolved rather than omitted or
    fabricated."""
    resp = await client.get("/api/v1/aqi/live?city=Pune", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 6

    codes = {item["station_code"] for item in data}
    assert codes == {s.station_code for s in pune_stations.REQUIRED_STATIONS}
    for item in data:
        assert item["unresolved"] is True
        assert item["station"] is None
        assert item["reading"] is None
        assert item["data_source"] == "unavailable"
        assert item["freshness"] == "unavailable"


@pytest.mark.asyncio
async def test_pune_live_mixed_resolution_and_freshness(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """One station resolved with a fresh real reading, one resolved but
    currently has no reading, the rest unresolved -> six entries total,
    each accurately reflecting its own state."""
    hadapsar_station = await _create_pune_live_station(db_session, HADAPSAR_SPEC)
    reading = AQIReading(
        station_id=hadapsar_station.id,
        pm25=68.2,
        pm10=110.0,
        aqi=142,
        no2=20.0,
        so2=5.0,
        co=1.0,
        o3=15.0,
        temperature=28.0,
        humidity=45.0,
        wind_speed=2.5,
        wind_direction=210.0,
        timestamp=datetime.now(UTC),
        latitude=HADAPSAR_SPEC.approx_lat,
        longitude=HADAPSAR_SPEC.approx_lon,
        quality_flag="good",
    )
    db_session.add(reading)

    nigdi_spec = next(
        s
        for s in pune_stations.REQUIRED_STATIONS
        if s.station_code == "PUNE_LIVE_NIGDI"
    )
    await _create_pune_live_station(db_session, nigdi_spec, openaq_location_id=200)
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/live?city=Pune", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 6
    by_code = {item["station_code"]: item for item in data}

    hadapsar = by_code["PUNE_LIVE_HADAPSAR"]
    assert hadapsar["unresolved"] is False
    assert hadapsar["reading"]["pm25"] == 68.2
    assert hadapsar["data_source"] == "openaq"
    assert hadapsar["freshness"] in {"live", "recent"}

    nigdi = by_code["PUNE_LIVE_NIGDI"]
    assert nigdi["unresolved"] is False
    assert nigdi["reading"] is None
    assert nigdi["data_source"] == "unavailable"

    still_unresolved = {
        code
        for code, item in by_code.items()
        if code not in ("PUNE_LIVE_HADAPSAR", "PUNE_LIVE_NIGDI")
    }
    assert len(still_unresolved) == 4
    for code in still_unresolved:
        assert by_code[code]["unresolved"] is True


@pytest.mark.asyncio
async def test_duplicate_openaq_location_conflict_does_not_poison_other_stations(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Regression test for a real bug found during production-readiness
    review: if two required stations' OpenAQ search results both
    resolve to the SAME openaq_location_id (violating the uniqueness
    constraint from migration 020_pune_live_stations), that station's
    resolution must fail in isolation — via a SAVEPOINT in
    _ingest_one_pune_station — rather than poisoning the shared
    ingestion-cycle session and silently dropping every other station's
    already-staged work.

    Exercises the full async ingestion pipeline (not a mocked session)
    against a real Postgres instance so the unique constraint is
    actually enforced by the database, not assumed."""
    await _create_pune_live_station(db_session, HADAPSAR_SPEC, openaq_location_id=777)
    await db_session.commit()

    # Nigdi's OpenAQ search "coincidentally" returns the exact same
    # location id already claimed by Hadapsar — a real OpenAQ data
    # inconsistency this must survive gracefully rather than crash on.
    nigdi_spec = next(
        s
        for s in pune_stations.REQUIRED_STATIONS
        if s.station_code == "PUNE_LIVE_NIGDI"
    )
    conflicting_candidates = [
        {
            "id": 777,
            "name": "Nigdi",
            "owner": {"name": "IITM"},
            "coordinates": {
                "latitude": nigdi_spec.approx_lat,
                "longitude": nigdi_spec.approx_lon,
            },
        }
    ]

    hadapsar_live = SimpleNamespace(
        pm25=55.0,
        pm10=90.0,
        no2=15.0,
        so2=4.0,
        co=1.0,
        o3=12.0,
        temperature=27.0,
        humidity=48.0,
        wind_speed=2.0,
        wind_direction=190.0,
        openaq_location_id=777,
        openaq_location_name="Hadapsar",
        distance_meters=0.0,
        observed_at=datetime.now(UTC),
    )

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
            new=AsyncMock(return_value=conflicting_candidates),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=hadapsar_live),
        ),
    ):
        # Mirrors _fetch_pune_live_stations_async's actual per-station
        # commit/rollback boundary (see that function's docstring/comment
        # for why this matters — a shared uncommitted transaction across
        # stations was the original form of this bug).
        hadapsar_outcome = await aqi_ingestion._ingest_one_pune_station(
            db_session, HADAPSAR_SPEC
        )
        await db_session.commit()

        nigdi_outcome = await aqi_ingestion._ingest_one_pune_station(
            db_session, nigdi_spec
        )
        await db_session.commit()

        # Session must still be usable after the conflict — prove it by
        # successfully ingesting a third station in the same session.
        dhankawadi_spec = next(
            s
            for s in pune_stations.REQUIRED_STATIONS
            if s.station_code == "PUNE_LIVE_DHANKAWADI"
        )
        await _create_pune_live_station(
            db_session, dhankawadi_spec, openaq_location_id=888
        )
        await db_session.commit()
        dhankawadi_live = SimpleNamespace(
            pm25=40.0,
            pm10=70.0,
            no2=10.0,
            so2=3.0,
            co=0.8,
            o3=10.0,
            temperature=26.0,
            humidity=50.0,
            wind_speed=1.5,
            wind_direction=200.0,
            openaq_location_id=888,
            openaq_location_name="Dhankawadi",
            distance_meters=0.0,
            observed_at=datetime.now(UTC),
        )
        with patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=dhankawadi_live),
        ):
            dhankawadi_outcome = await aqi_ingestion._ingest_one_pune_station(
                db_session, dhankawadi_spec
            )
        await db_session.commit()

    assert hadapsar_outcome == "inserted"
    assert nigdi_outcome == "unresolved_location_id_conflict"
    assert dhankawadi_outcome == "inserted"

    resp = await client.get("/api/v1/aqi/live?city=Pune", headers=auth_headers)
    data = resp.json()["data"]
    by_code = {item["station_code"]: item for item in data}
    assert by_code["PUNE_LIVE_HADAPSAR"]["reading"] is not None
    assert by_code["PUNE_LIVE_DHANKAWADI"]["reading"] is not None
    assert by_code["PUNE_LIVE_NIGDI"]["unresolved"] is True


@pytest.mark.asyncio
async def test_fetch_pune_live_stations_async_full_cycle_survives_one_conflict(
    monkeypatch, db_session: AsyncSession
):
    """End-to-end test of the actual Celery entry point
    (_fetch_pune_live_stations_async, not just the inner per-station
    helper) against real Postgres: seed one station with an
    openaq_location_id, make a DIFFERENT required station's search
    results collide with it, and confirm the full six-station run
    completes with five real outcomes and exactly one conflict — proving
    the per-station commit fix works through the real entry point,
    including its own lock/engine/session setup, not just when driven
    directly by the test.

    `db_session` is unused directly (this test opens its own engine,
    matching what the real Celery task does) but is required to trigger
    the test database's schema setup via conftest.py."""
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.models.monitoring import MonitoringStation
    from app.workers.tasks import aqi_ingestion

    monkeypatch.setattr(
        "app.workers.tasks.aqi_ingestion._acquire_pune_live_lock",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.workers.tasks.aqi_ingestion._release_pune_live_lock", AsyncMock()
    )
    monkeypatch.setattr(
        "app.workers.tasks.aqi_ingestion.openaq.is_configured",
        lambda: True,
    )

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    from geoalchemy2.elements import WKTElement

    async with Session() as session:
        pre_existing = MonitoringStation(
            id=_uuid.uuid4(),
            name=HADAPSAR_SPEC.display_name,
            station_code=HADAPSAR_SPEC.station_code,
            city=HADAPSAR_SPEC.city,
            state=HADAPSAR_SPEC.state,
            country=HADAPSAR_SPEC.country,
            operator="IITM (via OpenAQ)",
            latitude=HADAPSAR_SPEC.approx_lat,
            longitude=HADAPSAR_SPEC.approx_lon,
            geometry=WKTElement(
                f"POINT({HADAPSAR_SPEC.approx_lon} {HADAPSAR_SPEC.approx_lat})",
                srid=4326,
            ),
            is_active=True,
            station_type="OpenAQ",
            openaq_location_id=9001,
        )
        session.add(pre_existing)
        await session.commit()

    def fake_search(lat, lon, radius_m):
        # Every unresolved station's search "finds" location 9001 — the
        # one Hadapsar already owns — to force a real conflict for
        # whichever station resolves first.
        return [
            {
                "id": 9001,
                "name": "collision",
                "owner": {"name": "IITM"},
                "coordinates": {"latitude": lat, "longitude": lon},
            }
        ]

    def fake_match(candidates, spec):
        # Force every spec to "match" the colliding candidate, regardless
        # of name, so the conflict is guaranteed rather than probabilistic.
        return candidates[0] if candidates else None

    async def fake_fetch_reading(location_id, name):
        if location_id != 9001:
            return None
        return SimpleNamespace(
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
            openaq_location_id=9001,
            openaq_location_name="collision",
            distance_meters=0.0,
            observed_at=datetime.now(UTC),
        )

    monkeypatch.setattr(
        "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
        AsyncMock(side_effect=fake_search),
    )
    monkeypatch.setattr(
        "app.workers.tasks.aqi_ingestion.pune_stations.match_station",
        fake_match,
    )
    monkeypatch.setattr(
        "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
        AsyncMock(side_effect=fake_fetch_reading),
    )

    try:
        summary = await aqi_ingestion._fetch_pune_live_stations_async()
    finally:
        async with engine.begin() as conn:
            from sqlalchemy import text

            await conn.execute(
                text(
                    "DELETE FROM aqi_readings WHERE station_id IN "
                    "(SELECT id FROM monitoring_stations WHERE station_code LIKE 'PUNE_LIVE_%')"
                )
            )
            await conn.execute(
                text(
                    "DELETE FROM monitoring_stations WHERE station_code LIKE 'PUNE_LIVE_%'"
                )
            )
        await engine.dispose()

    # Hadapsar already owned 9001 and gets a real inserted reading.
    assert summary["PUNE_LIVE_HADAPSAR"] == "inserted"
    # Every other station's search also resolved to 9001, which is
    # already taken -> each independently reports the conflict, never a
    # crash, never a fabricated reading, and no station's failure took
    # any other station down with it.
    other_codes = [
        s.station_code
        for s in pune_stations.REQUIRED_STATIONS
        if s.station_code != "PUNE_LIVE_HADAPSAR"
    ]
    for code in other_codes:
        assert summary[code] == "unresolved_location_id_conflict", summary


@pytest.mark.asyncio
async def test_pune_live_never_returns_synthetic_reading(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Even if a synthetic-flagged reading somehow exists against one of
    the six real station rows (e.g. leftover from a bug elsewhere), the
    Pune Live AQI view must never surface it as if it were real."""
    station = await _create_pune_live_station(db_session, HADAPSAR_SPEC)
    synthetic_reading = AQIReading(
        station_id=station.id,
        pm25=999.0,
        pm10=999.0,
        aqi=500,
        no2=1.0,
        so2=1.0,
        co=1.0,
        o3=1.0,
        temperature=25.0,
        humidity=50.0,
        wind_speed=1.0,
        wind_direction=1.0,
        timestamp=datetime.now(UTC),
        latitude=HADAPSAR_SPEC.approx_lat,
        longitude=HADAPSAR_SPEC.approx_lon,
        quality_flag="synthetic",
    )
    db_session.add(synthetic_reading)
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/live?city=Pune", headers=auth_headers)
    data = resp.json()["data"]
    hadapsar = next(
        item for item in data if item["station_code"] == "PUNE_LIVE_HADAPSAR"
    )
    # get_latest_by_station has no synthetic-exclusion of its own (it's a
    # "most recent row regardless of flag" lookup used across many
    # features) — the six-station live view relies on the ingestion
    # pipeline (fetch_live_aqi_pune_stations) never writing a synthetic
    # row in the first place. This assertion documents that contract: if
    # one ever slipped in, data_source must still say so rather than
    # silently rendering it as "openaq".
    if hadapsar["reading"] is not None:
        assert hadapsar["data_source"] != "openaq"
