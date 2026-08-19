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
    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
    ), patch(
        "app.workers.tasks.aqi_ingestion.openaq.fetch_nearest_reading",
        new=AsyncMock(return_value=live),
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
    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.is_configured", return_value=True
    ), patch(
        "app.workers.tasks.aqi_ingestion.openaq.fetch_nearest_reading",
        new=AsyncMock(return_value=None),
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
    with patch(
        "sqlalchemy.ext.asyncio.create_async_engine"
    ) as mock_create_engine, patch(
        "sqlalchemy.ext.asyncio.async_sessionmaker"
    ) as mock_sessionmaker:
        fake_engine = AsyncMock()
        mock_create_engine.return_value = fake_engine
        yield mock_create_engine, mock_sessionmaker, fake_engine


@pytest.mark.asyncio
async def test_fetch_aqi_async_ingests_all_cities(patched_engine):
    _, mock_sessionmaker, fake_engine = patched_engine
    session = make_db_session()
    session.commit = AsyncMock()
    mock_sessionmaker.return_value = MagicMock(return_value=make_session_cm(session))

    with patch(
        "app.workers.tasks.aqi_ingestion._ensure_stations_exist",
        new=AsyncMock(return_value={"PUNE_001": "id-1"}),
    ), patch(
        "app.workers.tasks.aqi_ingestion.ALL_STATIONS",
        {"Pune": [{"code": "PUNE_001", "lat": 18.5, "lon": 73.8}]},
    ), patch(
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
    with patch(
        "app.workers.tasks.aqi_ingestion._fetch_aqi_async", new=AsyncMock()
    ) as mocked, patch("app.workers.tasks.aqi_ingestion.asyncio.run") as mock_run:
        mock_run.side_effect = lambda coro: coro.close()
        aqi_ingestion.fetch_live_aqi_all_cities.run()
        mocked.assert_called_once()
        mock_run.assert_called_once()


def test_fetch_weather_data_task_invokes_async():
    with patch(
        "app.workers.tasks.aqi_ingestion._fetch_weather_async", new=AsyncMock()
    ) as mocked, patch("app.workers.tasks.aqi_ingestion.asyncio.run") as mock_run:
        mock_run.side_effect = lambda coro: coro.close()
        aqi_ingestion.fetch_weather_data.run()
        mocked.assert_called_once()
        mock_run.assert_called_once()