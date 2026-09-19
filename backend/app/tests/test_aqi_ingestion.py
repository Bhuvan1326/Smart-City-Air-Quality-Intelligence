from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.tests.test_helpers import make_db_session, make_session_cm
from app.workers.tasks import aqi_ingestion


def test_calculate_aqi_from_pm25_within_and_above_breakpoints():
    assert aqi_ingestion._calculate_aqi_from_pm25(15.0) < 51
    assert aqi_ingestion._calculate_aqi_from_pm25(600.0) == 500


def test_generate_realistic_reading_has_expected_keys():
    station = {"ward": "W01", "code": "PUNE_001"}
    reading = aqi_ingestion._generate_realistic_reading(station, hour=8)

    assert set(reading.keys()) >= {"pm25", "pm10", "aqi", "temperature"}
    assert reading["aqi"] >= 0


def test_generate_realistic_reading_industrial_ward_higher_baseline():
    industrial = aqi_ingestion._generate_realistic_reading({"ward": "W04"}, hour=12)
    normal = aqi_ingestion._generate_realistic_reading({"ward": "W07"}, hour=12)

    assert industrial["pm25"] > 0
    assert normal["pm25"] > 0


def test_generate_realistic_reading_night_hours():
    reading = aqi_ingestion._generate_realistic_reading({"ward": "W01"}, hour=2)
    assert reading["pm25"] > 0


@pytest.mark.asyncio
async def test_build_reading_for_station_uses_openaq_when_live_data_available():
    live = SimpleNamespace(
        pm25=42.0,
        pm10=60.0,
        no2=20.0,
        so2=5.0,
        co=1.0,
        o3=30.0,
        temperature=25.0,
        humidity=50.0,
        wind_speed=2.0,
        wind_direction=180.0,
        openaq_location_id=1,
        openaq_location_name="Test Loc",
        distance_meters=500.0,
        observed_at=datetime.now(UTC),
    )
    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_nearest_reading",
            new=AsyncMock(return_value=live),
        ),
    ):
        built = await aqi_ingestion._build_reading_for_station(
            {"lat": 18.5, "lon": 73.8, "ward": "W01"}, hour=8
        )

    assert built is not None
    data, quality_flag, raw = built
    assert quality_flag == "good"
    assert data["pm25"] == 42.0
    assert "openaq" in raw


@pytest.mark.asyncio
async def test_build_reading_for_station_returns_none_when_unconfigured():
    """No synthetic fallback: an unconfigured OpenAQ means no reading at
    all is produced for this station this cycle — never a fabricated one
    (requirement 4)."""
    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=False
    ):
        built = await aqi_ingestion._build_reading_for_station(
            {"lat": 18.5, "lon": 73.8, "ward": "W01"}, hour=8
        )

    assert built is None


@pytest.mark.asyncio
async def test_build_reading_for_station_returns_none_when_no_live_reading():
    """No synthetic fallback: OpenAQ configured but nothing nearby/fresh
    means no reading is produced — never a fabricated one."""
    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_nearest_reading",
            new=AsyncMock(return_value=None),
        ),
    ):
        built = await aqi_ingestion._build_reading_for_station(
            {"lat": 18.5, "lon": 73.8, "ward": "W01"}, hour=8
        )

    assert built is None


@pytest.mark.asyncio
async def test_ensure_stations_exist_creates_new_and_reuses_existing():
    session = make_db_session()

    existing_result = MagicMock()
    existing_result.one_or_none.return_value = SimpleNamespace(
        id="existing-id", station_code="PUNE_001"
    )
    missing_result = MagicMock()
    missing_result.one_or_none.return_value = None

    session.execute = AsyncMock(side_effect=[existing_result, missing_result])
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    stations = [
        {
            "code": "PUNE_001",
            "name": "Station A",
            "ward": "W01",
            "lat": 18.5,
            "lon": 73.8,
        },
        {
            "code": "PUNE_002",
            "name": "Station B",
            "ward": "W02",
            "lat": 18.6,
            "lon": 73.9,
        },
    ]

    code_to_id = await aqi_ingestion._ensure_stations_exist(session, "Pune", stations)

    assert code_to_id["PUNE_001"] == "existing-id"
    assert "PUNE_002" in code_to_id
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.fixture
def patched_engine():
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create_engine,
        patch("sqlalchemy.ext.asyncio.async_sessionmaker") as mock_sessionmaker,
    ):
        fake_engine = AsyncMock()
        mock_create_engine.return_value = fake_engine
        yield mock_create_engine, mock_sessionmaker, fake_engine


@pytest.mark.asyncio
async def test_fetch_aqi_async_ingests_all_cities(patched_engine):
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    with (
        patch(
            "app.workers.tasks.aqi_ingestion._ensure_stations_exist",
            new=AsyncMock(return_value={"PUNE_001": "id-1"}),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.ALL_STATIONS",
            {"Pune": [{"code": "PUNE_001", "lat": 18.5, "lon": 73.8}]},
        ),
        patch(
            "app.workers.tasks.aqi_ingestion._build_reading_for_station",
            new=AsyncMock(
                return_value=(
                    {
                        "pm25": 40.0,
                        "pm10": 60.0,
                        "no2": 20.0,
                        "so2": 5.0,
                        "co": 1.0,
                        "o3": 20.0,
                        "aqi": 90,
                        "temperature": 25.0,
                        "humidity": 50.0,
                        "wind_speed": 2.0,
                        "wind_direction": 180.0,
                    },
                    "good",
                    '{"source": "openaq"}',
                )
            ),
        ),
    ):
        await aqi_ingestion._fetch_aqi_async()

    session.add_all.assert_called_once()
    session.commit.assert_awaited_once()
    fake_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_aqi_async_skips_station_with_no_live_reading(patched_engine):
    """No synthetic fallback: when `_build_reading_for_station` returns
    None (no real OpenAQ observation), no AQIReading is created for that
    station — the batch is simply smaller, never padded with fabricated
    data."""
    _, mock_sessionmaker, _fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    with (
        patch(
            "app.workers.tasks.aqi_ingestion._ensure_stations_exist",
            new=AsyncMock(return_value={"PUNE_001": "id-1"}),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.ALL_STATIONS",
            {"Pune": [{"code": "PUNE_001", "lat": 18.5, "lon": 73.8}]},
        ),
        patch(
            "app.workers.tasks.aqi_ingestion._build_reading_for_station",
            new=AsyncMock(return_value=None),
        ),
    ):
        await aqi_ingestion._fetch_aqi_async()

    session.add_all.assert_called_once_with([])
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_weather_async_success_and_failure_status():
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = {"hourly": {"time": ["t1", "t2"]}}
    fail_response = MagicMock(status_code=500)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[ok_response, fail_response])

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        await aqi_ingestion._fetch_weather_async()

    assert mock_client.get.await_count == 2


@pytest.mark.asyncio
async def test_fetch_weather_async_handles_request_exception():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("boom"))

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        await aqi_ingestion._fetch_weather_async()

    assert mock_client.get.await_count == 2


def test_fetch_live_aqi_all_cities_task_invokes_async():
    with (
        patch(
            "app.workers.tasks.aqi_ingestion._fetch_aqi_async", new=AsyncMock()
        ) as mocked,
        patch("app.workers.tasks.aqi_ingestion.asyncio.run") as mock_run,
    ):
        mock_run.side_effect = lambda coro: coro.close()
        aqi_ingestion.fetch_live_aqi_all_cities()
        mocked.assert_called_once()
        mock_run.assert_called_once()


def test_fetch_weather_data_task_invokes_async():
    with (
        patch(
            "app.workers.tasks.aqi_ingestion._fetch_weather_async", new=AsyncMock()
        ) as mocked,
        patch("app.workers.tasks.aqi_ingestion.asyncio.run") as mock_run,
    ):
        mock_run.side_effect = lambda coro: coro.close()
        aqi_ingestion.fetch_weather_data()
        mocked.assert_called_once()
        mock_run.assert_called_once()


def test_discover_and_ingest_india_locations_task_invokes_async():
    with (
        patch(
            "app.workers.tasks.aqi_ingestion._discover_india_locations_async",
            new=AsyncMock(),
        ) as mocked,
        patch("app.workers.tasks.aqi_ingestion.asyncio.run") as mock_run,
    ):
        mock_run.side_effect = lambda coro: coro.close()
        aqi_ingestion.discover_and_ingest_india_locations()
        mocked.assert_called_once()
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_discover_india_locations_noop_when_unconfigured():
    """No OpenAQ key configured -> the task must not touch the database at
    all (no engine/session created), and must not fabricate stations."""
    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured",
            return_value=False,
        ),
        patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create_engine,
    ):
        await aqi_ingestion._discover_india_locations_async()
        mock_create_engine.assert_not_called()


@pytest.mark.asyncio
async def test_discover_india_locations_persists_discovered_station_only(
    patched_engine,
):
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()

    lookup_result = MagicMock()
    lookup_result.one_or_none.return_value = None
    session.execute = AsyncMock(return_value=lookup_result)

    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    fake_location = SimpleNamespace(
        openaq_location_id=42,
        name="Test India Station",
        latitude=28.6,
        longitude=77.2,
        city="Delhi",
        state=None,
        country_code="IN",
        sensor_parameters=["pm25", "pm10"],
    )

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_country_locations",
            new=AsyncMock(side_effect=[[fake_location], []]),
        ),
    ):
        await aqi_ingestion._discover_india_locations_async()

    assert session.add.call_count == 1
    session.commit.assert_awaited()
    fake_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_discover_india_locations_persists_openaq_location_id_on_new_station(
    patched_engine,
):
    _, mock_sessionmaker, _fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()

    lookup_result = MagicMock()
    lookup_result.one_or_none.return_value = None
    session.execute = AsyncMock(return_value=lookup_result)

    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    fake_location = SimpleNamespace(
        openaq_location_id=42,
        name="Test India Station",
        latitude=28.6,
        longitude=77.2,
        city="Delhi",
        state=None,
        country_code="IN",
        sensor_parameters=["pm25", "pm10"],
    )

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_country_locations",
            new=AsyncMock(side_effect=[[fake_location], []]),
        ),
    ):
        await aqi_ingestion._discover_india_locations_async()

    added_station = session.add.call_args[0][0]
    assert added_station.openaq_location_id == 42


@pytest.mark.asyncio
async def test_discover_india_locations_updates_openaq_location_id_on_existing_station(
    patched_engine,
):
    _, mock_sessionmaker, _fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()

    lookup_result = MagicMock()
    lookup_result.one_or_none.return_value = ("existing-station-id",)
    session.execute = AsyncMock(return_value=lookup_result)

    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    fake_location = SimpleNamespace(
        openaq_location_id=99,
        name="Existing India Station",
        latitude=19.0,
        longitude=72.8,
        city="Mumbai",
        state="Maharashtra",
        country_code="IN",
        sensor_parameters=["pm25"],
    )

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_country_locations",
            new=AsyncMock(side_effect=[[fake_location], []]),
        ),
    ):
        await aqi_ingestion._discover_india_locations_async()

    update_call = session.execute.call_args_list[-1]
    update_stmt = update_call.args[0]
    assert "openaq_location_id" in str(update_stmt)


def test_city_for_location_falls_back_to_name_when_no_locality():
    """OpenAQ's `locality` field is frequently blank; MonitoringStation.city
    is NOT NULL, so a station without a locality must still get a usable
    (never fabricated) city label rather than being dropped from India-wide
    discovery entirely."""
    location = SimpleNamespace(
        openaq_location_id=7,
        name="  Some Rooftop Sensor  ",
        city=None,
    )
    assert aqi_ingestion._city_for_location(location) == "Some Rooftop Sensor"


def test_city_for_location_falls_back_to_id_when_no_name_either():
    location = SimpleNamespace(openaq_location_id=7, name="", city="")
    assert aqi_ingestion._city_for_location(location) == "OpenAQ 7"


def test_city_for_location_prefers_locality_when_present():
    location = SimpleNamespace(openaq_location_id=7, name="Ignored", city="Nagpur")
    assert aqi_ingestion._city_for_location(location) == "Nagpur"


@pytest.mark.asyncio
async def test_discover_india_locations_persists_station_without_locality(
    patched_engine,
):
    """Regression test for the root cause of India discovery silently
    under-populating non-Pune coverage: a discovered OpenAQ location with
    no `locality` used to be dropped outright (`if not location.city:
    return None, False`). It must now be persisted, using the location's
    own name as the city label."""
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()

    lookup_result = MagicMock()
    lookup_result.one_or_none.return_value = None
    session.execute = AsyncMock(return_value=lookup_result)

    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    fake_location = SimpleNamespace(
        openaq_location_id=101,
        name="Rural Monitoring Post",
        latitude=23.2,
        longitude=77.4,
        city=None,  # OpenAQ returned no locality for this location
        state=None,
        country_code="IN",
        sensor_parameters=["pm25"],
    )

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_country_locations",
            new=AsyncMock(side_effect=[[fake_location], []]),
        ),
    ):
        summary = await aqi_ingestion._discover_india_locations_async()

    assert session.add.call_count == 1
    added_station = session.add.call_args[0][0]
    assert added_station.city == "Rural Monitoring Post"
    assert added_station.station_type == "OpenAQ"
    assert added_station.country == "India"
    assert summary["stations_created"] == 1
    assert summary["stations_skipped"] == 0
    fake_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_discover_india_locations_reports_stations_skipped(patched_engine):
    """A location OpenAQ can't be placed on a map for (no id/lat/lon —
    already filtered upstream in openaq.fetch_country_locations) or any
    other unresolved case must be counted in `stations_skipped`, not
    silently dropped from the summary."""
    _, mock_sessionmaker, _fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_country_locations",
            new=AsyncMock(side_effect=[[], []]),
        ),
    ):
        summary = await aqi_ingestion._discover_india_locations_async()

    assert summary["locations_discovered"] == 0
    assert summary["stations_created"] == 0
    assert summary["stations_skipped"] == 0
    assert summary["errors"] == 0


@pytest.mark.asyncio
async def test_get_india_station_batch_query_filters_by_openaq_and_india(
    patched_india_batch_redis,
):
    """The India ingestion batch selection must be driven purely by
    `station_type == 'OpenAQ' AND country == 'India'` — never by a
    Pune-specific station_code prefix, city filter, or the REQUIRED_STATIONS
    fixture list. This is what lets Pune-live stations and India-wide
    discovered stations sit in the same canonical selection without any
    Pune-specific carve-out."""
    session = make_db_session()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    await aqi_ingestion._get_india_station_batch(session, batch_size=20)

    query = session.execute.call_args[0][0]
    compiled = str(query.compile(compile_kwargs={"literal_binds": True}))
    assert "country" in compiled and "India" in compiled
    assert "station_type" in compiled and "OpenAQ" in compiled
    # Must not filter on station_code/city at all (that would silently
    # re-introduce a Pune-only selection).
    assert "station_code =" not in compiled
    assert "city =" not in compiled


async def _create_openaq_india_station(
    session: AsyncSession,
    code: str,
    *,
    city: str = "Delhi",
    openaq_location_id: int,
):
    from geoalchemy2.elements import WKTElement

    from app.models.monitoring import MonitoringStation

    station = MonitoringStation(
        name=f"Test Station {code}",
        station_code=code,
        city=city,
        state=None,
        country="India",
        operator="OpenAQ (CPCB / state boards)",
        latitude=28.6,
        longitude=77.2,
        geometry=WKTElement("POINT(77.2 28.6)", srid=4326),
        is_active=True,
        station_type="OpenAQ",
        openaq_location_id=openaq_location_id,
    )
    session.add(station)
    await session.flush()
    return station


@pytest.mark.asyncio
async def test_india_ingestion_selection_includes_pune_and_non_pune_stations(
    db_session: AsyncSession,
):
    """End-to-end regression test for the reported bug: with both a
    Pune-live station (station_code 'PUNE_LIVE_*') and an India-wide
    discovered station (station_code 'OPENAQ_IN_*') present — both
    station_type='OpenAQ', country='India' — the India ingestion batch
    selection must include the non-Pune station too, never only Pune.
    Uses the real database (no mocking of the query itself) to prove the
    selection logic, not a mock's behavior."""
    pune_live = await _create_openaq_india_station(
        db_session, "PUNE_LIVE_SPPU", city="Pune", openaq_location_id=1001
    )
    non_pune = await _create_openaq_india_station(
        db_session, "OPENAQ_IN_2002", city="Chennai", openaq_location_id=2002
    )
    await db_session.commit()

    with patch(
        "app.workers.tasks.aqi_ingestion.get_redis",
        new=AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=None))),
    ):
        stations = await aqi_ingestion._get_india_station_batch(
            db_session, batch_size=20
        )

    codes = {s.station_code for s in stations}
    assert pune_live.station_code in codes
    assert non_pune.station_code in codes
    assert not codes.issubset({pune_live.station_code}), (
        "India ingestion selected only the Pune-live station — this is "
        "exactly the reported production bug."
    )


@pytest.fixture
def patched_india_batch_redis():
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)
    fake_redis.set = AsyncMock()
    with patch(
        "app.workers.tasks.aqi_ingestion.get_redis",
        new=AsyncMock(return_value=fake_redis),
    ):
        yield fake_redis


@pytest.mark.asyncio
async def test_ingest_india_batch_accepts_reading_missing_pm25(
    patched_engine, patched_india_batch_redis
):
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    latest_result = MagicMock()
    latest_result.scalar_one_or_none.return_value = None
    update_result = MagicMock()
    session.execute = AsyncMock(side_effect=[latest_result, update_result])

    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    fake_station = SimpleNamespace(
        id="station-uuid",
        station_code="OPENAQ_IN_42",
        name="Test India Station",
        openaq_location_id=42,
        latitude=28.6,
        longitude=77.2,
    )

    live = SimpleNamespace(
        pm25=None,
        pm10=95.0,
        no2=18.0,
        so2=None,
        co=None,
        o3=None,
        temperature=None,
        humidity=None,
        wind_speed=None,
        wind_direction=None,
        openaq_location_id=42,
        openaq_location_name="Test India Station",
        distance_meters=0.0,
        observed_at=datetime.now(UTC),
        is_stale=False,
        age_seconds=0.0,
    )

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion._get_india_station_batch",
            new=AsyncMock(return_value=[fake_station]),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=live),
        ),
    ):
        summary = await aqi_ingestion._ingest_india_station_batch_async()

    assert summary["no_current_observation"] == 0
    assert summary["readings_ingested"] == 1
    assert summary["errors"] == 0
    fake_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingest_india_batch_reports_no_observation_when_all_pollutants_none(
    patched_engine, patched_india_batch_redis
):
    """A LiveReading with every pollutant None must still be treated as
    no_current_observation, never fabricated or force-inserted."""
    _, mock_sessionmaker, _fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()
    session.execute = AsyncMock()

    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    fake_station = SimpleNamespace(
        id="station-uuid",
        station_code="OPENAQ_IN_43",
        name="Test India Station 2",
        openaq_location_id=43,
        latitude=28.6,
        longitude=77.2,
    )

    live = SimpleNamespace(
        pm25=None,
        pm10=None,
        no2=None,
        so2=None,
        co=None,
        o3=None,
        temperature=None,
        humidity=None,
        wind_speed=None,
        wind_direction=None,
        openaq_location_id=43,
        openaq_location_name="Test India Station 2",
        distance_meters=0.0,
        observed_at=datetime.now(UTC),
        is_stale=False,
        age_seconds=0.0,
    )

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion._get_india_station_batch",
            new=AsyncMock(return_value=[fake_station]),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=live),
        ),
    ):
        summary = await aqi_ingestion._ingest_india_station_batch_async()

    assert summary["no_current_observation"] == 1
    assert summary["readings_ingested"] == 0
    assert summary["errors"] == 0


@pytest.mark.asyncio
async def test_ingest_india_batch_stores_stale_observation_when_no_prior_reading(
    patched_engine, patched_india_batch_redis
):
    _, mock_sessionmaker, _fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    latest_result = MagicMock()
    latest_result.scalar_one_or_none.return_value = None
    update_result = MagicMock()
    session.execute = AsyncMock(side_effect=[latest_result, update_result])

    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    fake_station = SimpleNamespace(
        id="station-uuid",
        station_code="OPENAQ_IN_44",
        name="Old Station",
        openaq_location_id=44,
        latitude=18.5,
        longitude=73.9,
    )

    stale_observed_at = datetime(2022, 7, 21, 4, 45, tzinfo=UTC)
    live = SimpleNamespace(
        pm25=30.0,
        pm10=55.0,
        no2=10.0,
        so2=2.0,
        co=0.6,
        o3=8.0,
        temperature=None,
        humidity=None,
        wind_speed=None,
        wind_direction=None,
        openaq_location_id=44,
        openaq_location_name="Old Station",
        distance_meters=0.0,
        observed_at=stale_observed_at,
        is_stale=True,
        age_seconds=(datetime.now(UTC) - stale_observed_at).total_seconds(),
    )

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion._get_india_station_batch",
            new=AsyncMock(return_value=[fake_station]),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=live),
        ),
    ):
        summary = await aqi_ingestion._ingest_india_station_batch_async()

    assert summary["readings_ingested"] == 1
    inserted_reading = session.add.call_args[0][0]
    assert inserted_reading.timestamp == stale_observed_at
    assert inserted_reading.quality_flag == "stale"


@pytest.mark.asyncio
async def test_ingest_india_batch_skips_when_no_new_observation(
    patched_engine, patched_india_batch_redis
):
    _, mock_sessionmaker, _fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    now = datetime.now(UTC)
    latest_result = MagicMock()
    latest_result.scalar_one_or_none.return_value = now  # already on file
    update_result = MagicMock()
    session.execute = AsyncMock(side_effect=[latest_result, update_result])

    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    fake_station = SimpleNamespace(
        id="station-uuid",
        station_code="OPENAQ_IN_45",
        name="Repeat Station",
        openaq_location_id=45,
        latitude=19.0,
        longitude=72.8,
    )

    live = SimpleNamespace(
        pm25=40.0,
        pm10=70.0,
        no2=12.0,
        so2=3.0,
        co=0.8,
        o3=9.0,
        temperature=None,
        humidity=None,
        wind_speed=None,
        wind_direction=None,
        openaq_location_id=45,
        openaq_location_name="Repeat Station",
        distance_meters=0.0,
        observed_at=now,
        is_stale=False,
        age_seconds=0.0,
    )

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion._get_india_station_batch",
            new=AsyncMock(return_value=[fake_station]),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=live),
        ),
    ):
        summary = await aqi_ingestion._ingest_india_station_batch_async()

    assert summary["readings_ingested"] == 0
    assert summary["no_new_observation"] == 1
    assert summary["errors"] == 0
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_india_batch_duplicate_insert_race_not_counted_as_error(
    patched_engine, patched_india_batch_redis
):

    _, mock_sessionmaker, _fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock(side_effect=IntegrityError("dup", {}, Exception("dup")))

    latest_result = MagicMock()
    latest_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=latest_result)

    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    fake_station = SimpleNamespace(
        id="station-uuid",
        station_code="OPENAQ_IN_46",
        name="Racing Station",
        openaq_location_id=46,
        latitude=22.5,
        longitude=88.3,
    )

    now = datetime.now(UTC)
    live = SimpleNamespace(
        pm25=50.0,
        pm10=90.0,
        no2=14.0,
        so2=4.0,
        co=0.9,
        o3=11.0,
        temperature=None,
        humidity=None,
        wind_speed=None,
        wind_direction=None,
        openaq_location_id=46,
        openaq_location_name="Racing Station",
        distance_meters=0.0,
        observed_at=now,
        is_stale=False,
        age_seconds=0.0,
    )

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion._get_india_station_batch",
            new=AsyncMock(return_value=[fake_station]),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=live),
        ),
    ):
        summary = await aqi_ingestion._ingest_india_station_batch_async()

    assert summary["readings_ingested"] == 0
    assert summary["duplicate_observation_skipped"] == 1
    assert summary["errors"] == 0
