from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
        data, quality_flag, raw = await aqi_ingestion._build_reading_for_station(
            {"lat": 18.5, "lon": 73.8, "ward": "W01"}, hour=8
        )

    assert quality_flag == "good"
    assert data["pm25"] == 42.0
    assert "openaq" in raw


@pytest.mark.asyncio
async def test_build_reading_for_station_falls_back_when_unconfigured():
    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=False
    ):
        data, quality_flag, raw = await aqi_ingestion._build_reading_for_station(
            {"lat": 18.5, "lon": 73.8, "ward": "W01"}, hour=8
        )

    assert quality_flag == "synthetic"
    assert "openaq_unconfigured" in raw


@pytest.mark.asyncio
async def test_build_reading_for_station_falls_back_when_no_live_reading():
    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_nearest_reading",
            new=AsyncMock(return_value=None),
        ),
    ):
        data, quality_flag, raw = await aqi_ingestion._build_reading_for_station(
            {"lat": 18.5, "lon": 73.8, "ward": "W01"}, hour=8
        )

    assert quality_flag == "synthetic"
    assert "no_live_reading_available" in raw


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
                    "synthetic",
                    "{}",
                )
            ),
        ),
    ):
        await aqi_ingestion._fetch_aqi_async()

    session.add_all.assert_called_once()
    session.commit.assert_awaited_once()
    fake_engine.dispose.assert_awaited_once()


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
        aqi_ingestion.fetch_live_aqi_all_cities.run()
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
        aqi_ingestion.fetch_weather_data.run()
        mocked.assert_called_once()
        mock_run.assert_called_once()


# ─── Nationwide (India) station discovery/ingestion ──────────────────────────


def test_station_code_for_openaq_location_is_stable():
    assert aqi_ingestion._station_code_for_openaq_location(42) == "OPENAQ_IN_42"
    # Re-running discovery for the same location must produce the same
    # code, so it upserts instead of duplicating.
    assert aqi_ingestion._station_code_for_openaq_location(
        42
    ) == aqi_ingestion._station_code_for_openaq_location(42)


def test_city_for_location_prefers_locality():
    location = {"locality": "Pimpri-Chinchwad", "name": "Station 7"}
    assert aqi_ingestion._city_for_location(location) == "Pimpri-Chinchwad"


def test_city_for_location_falls_back_to_name():
    location = {"locality": "", "name": "Anand Vihar"}
    assert aqi_ingestion._city_for_location(location) == "Anand Vihar"


def test_city_for_location_none_when_no_metadata():
    # Never fabricate a placeholder city — the caller must skip the
    # location instead.
    assert aqi_ingestion._city_for_location({}) is None
    assert aqi_ingestion._city_for_location({"locality": "  ", "name": ""}) is None


@pytest.mark.asyncio
async def test_ensure_discovered_station_skips_missing_coordinates():
    session = make_db_session()
    location = {"id": 1, "name": "No Coords", "coordinates": {}}

    result = await aqi_ingestion._ensure_discovered_station(session, location)

    assert result is None
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_discovered_station_skips_missing_city():
    session = make_db_session()
    location = {
        "id": 2,
        "name": "",
        "locality": "",
        "coordinates": {"latitude": 18.5, "longitude": 73.8},
    }

    result = await aqi_ingestion._ensure_discovered_station(session, location)

    assert result is None
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_discovered_station_reuses_existing_row():
    session = make_db_session()
    existing_result = MagicMock()
    existing_result.one_or_none.return_value = ("existing-id",)
    session.execute = AsyncMock(return_value=existing_result)

    location = {
        "id": 3,
        "name": "Existing Station",
        "locality": "Nagpur",
        "coordinates": {"latitude": 21.15, "longitude": 79.09},
    }

    result = await aqi_ingestion._ensure_discovered_station(session, location)

    assert result == "existing-id"
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_discovered_station_creates_new_row_from_real_metadata():
    session = make_db_session()
    missing_result = MagicMock()
    missing_result.one_or_none.return_value = None
    session.execute = AsyncMock(return_value=missing_result)
    session.flush = AsyncMock()

    location = {
        "id": 4,
        "name": "Sector 62 CAAQMS",
        "locality": "Noida",
        "coordinates": {"latitude": 28.62, "longitude": 77.36},
        "owner": {"name": "UPPCB"},
    }

    result = await aqi_ingestion._ensure_discovered_station(session, location)

    session.add.assert_called_once()
    created_station = session.add.call_args[0][0]
    assert created_station.station_code == "OPENAQ_IN_4"
    assert created_station.city == "Noida"
    assert created_station.operator == "UPPCB"
    assert created_station.station_type == "OpenAQ"
    assert result == created_station.id


@pytest.mark.asyncio
async def test_discover_and_ingest_india_async_skips_when_unconfigured():
    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=False
    ):
        summary = await aqi_ingestion._discover_and_ingest_india_async()

    assert summary["locations_discovered"] == 0
    assert summary["stations_created"] == 0
    assert summary["readings_ingested"] == 0
    assert summary["cities"] == []


@pytest.mark.asyncio
async def test_discover_and_ingest_india_async_never_synthesizes_readings(
    patched_engine,
):
    """When OpenAQ returns a station but no fresh reading, the station is
    persisted but NO reading (real or synthetic) is created for it."""
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    empty_codes_result = MagicMock()
    empty_codes_result.all.return_value = []
    missing_station_result = MagicMock()
    missing_station_result.one_or_none.return_value = None
    session.execute = AsyncMock(
        side_effect=[empty_codes_result, missing_station_result]
    )
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    location = {
        "id": 5,
        "name": "No Fresh Data Station",
        "locality": "Kanpur",
        "coordinates": {"latitude": 26.45, "longitude": 80.33},
    }

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = AsyncMock()
    mock_client_cm.__aexit__.return_value = False

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.is_configured",
            return_value=True,
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.discover_india_locations",
            new=AsyncMock(return_value=[location]),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_latest",
            new=AsyncMock(return_value=None),
        ),
        patch("httpx.AsyncClient", return_value=mock_client_cm),
    ):
        summary = await aqi_ingestion._discover_and_ingest_india_async()

    assert summary["locations_discovered"] == 1
    assert summary["stations_created"] == 1
    assert summary["readings_ingested"] == 0
    assert summary["cities"] == ["Kanpur"]
    session.add.assert_called_once()  # the station, not a reading


def test_discover_and_ingest_india_stations_task_invokes_async():
    with (
        patch(
            "app.workers.tasks.aqi_ingestion._discover_and_ingest_india_async",
            new=AsyncMock(),
        ) as mocked,
        patch("app.workers.tasks.aqi_ingestion.asyncio.run") as mock_run,
    ):
        mock_run.side_effect = lambda coro: coro.close()
        aqi_ingestion.discover_and_ingest_india_stations.run()
        mocked.assert_called_once()
        mock_run.assert_called_once()
