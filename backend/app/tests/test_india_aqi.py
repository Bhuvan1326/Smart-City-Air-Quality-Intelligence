from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import AQIReading, MonitoringStation
from app.schemas.aqi import get_aqi_method, resolve_data_source
from app.services.india_aqi import IndiaAQIFilters, InvalidIndiaAQIFilterError


async def _create_station(
    session: AsyncSession,
    code: str,
    *,
    city: str = "Pune",
    state: str | None = "Maharashtra",
    country: str = "India",
    lat: float = 18.52,
    lon: float = 73.85,
    station_type: str = "OpenAQ",
) -> MonitoringStation:
    from geoalchemy2.elements import WKTElement

    station = MonitoringStation(
        name=f"Test Station {code}",
        station_code=code,
        city=city,
        state=state,
        country=country,
        ward_id="W01",
        operator="MPCB",
        latitude=lat,
        longitude=lon,
        geometry=WKTElement(f"POINT({lon} {lat})", srid=4326),
        is_active=True,
        station_type=station_type,
    )
    session.add(station)
    await session.flush()
    return station


async def _create_reading(
    session: AsyncSession,
    station_id,
    *,
    aqi: int = 120,
    pm25: float | None = 55.0,
    quality_flag: str = "good",
) -> AQIReading:
    reading = AQIReading(
        station_id=station_id,
        pm25=pm25,
        pm10=90.0,
        aqi=aqi,
        no2=30.0,
        so2=10.0,
        co=1.2,
        o3=25.0,
        temperature=27.0,
        humidity=60.0,
        wind_speed=3.0,
        wind_direction=180.0,
        timestamp=datetime.now(UTC),
        latitude=18.52,
        longitude=73.85,
        quality_flag=quality_flag,
    )
    session.add(reading)
    await session.flush()
    return reading


# ---------------------------------------------------------------------------
# Pure unit tests — no database required.
# ---------------------------------------------------------------------------


def test_resolve_data_source_values():
    assert resolve_data_source("synthetic") == "synthetic"
    assert resolve_data_source("good") == "openaq"


def test_get_aqi_method_no_aqi_returns_none():
    assert get_aqi_method(None, 55.0) is None


def test_get_aqi_method_aqi_without_pm25_is_unknown():
    assert get_aqi_method(120, None) == "unknown"


def test_get_aqi_method_aqi_with_pm25_is_cpcb_method():
    assert get_aqi_method(120, 55.0) == "CPCB_PM25_NAAQS_INTERPOLATED"


def test_india_aqi_filters_valid_defaults():
    filters = IndiaAQIFilters()
    assert filters.page == 1
    assert filters.page_size == 50


def test_india_aqi_filters_rejects_unknown_category():
    with pytest.raises(InvalidIndiaAQIFilterError):
        IndiaAQIFilters(category="Extremely Bad")


def test_india_aqi_filters_accepts_known_category_case_insensitive():
    filters = IndiaAQIFilters(category="unhealthy")
    assert filters.category == "unhealthy"


def test_india_aqi_filters_rejects_unknown_source():
    with pytest.raises(InvalidIndiaAQIFilterError):
        IndiaAQIFilters(source="satellite")


def test_india_aqi_filters_rejects_partial_bbox():
    with pytest.raises(InvalidIndiaAQIFilterError):
        IndiaAQIFilters(min_lat=10.0, min_lon=70.0)


def test_india_aqi_filters_rejects_inverted_bbox():
    with pytest.raises(InvalidIndiaAQIFilterError):
        IndiaAQIFilters(min_lat=20.0, min_lon=70.0, max_lat=10.0, max_lon=80.0)


def test_india_aqi_filters_accepts_valid_bbox():
    filters = IndiaAQIFilters(min_lat=8.0, min_lon=68.0, max_lat=37.0, max_lon=97.0)
    assert filters.max_lat == 37.0


def test_india_aqi_filters_rejects_oversized_page_size():
    with pytest.raises(InvalidIndiaAQIFilterError):
        IndiaAQIFilters(page_size=1000)


def test_india_aqi_filters_rejects_zero_page():
    with pytest.raises(InvalidIndiaAQIFilterError):
        IndiaAQIFilters(page=0)


def _fake_station(
    *,
    station_id=None,
    name="Test Station",
    station_code="OPENAQ_IN_1",
    station_type="OpenAQ",
    openaq_location_id=1,
    city="Delhi",
    state=None,
    country="India",
    lat=28.6,
    lon=77.2,
):
    import uuid
    from types import SimpleNamespace

    return SimpleNamespace(
        id=station_id or uuid.uuid4(),
        name=name,
        station_code=station_code,
        station_type=station_type,
        openaq_location_id=openaq_location_id,
        city=city,
        state=state,
        country=country,
        latitude=lat,
        longitude=lon,
    )


def _fake_reading(
    *,
    aqi=120,
    pm25=55.0,
    timestamp=None,
    quality_flag="good",
    created_at=None,
):
    from types import SimpleNamespace

    return SimpleNamespace(
        aqi=aqi,
        pm25=pm25,
        pm10=90.0,
        no2=30.0,
        so2=10.0,
        co=1.2,
        o3=25.0,
        timestamp=timestamp or datetime.now(UTC),
        created_at=created_at or datetime.now(UTC),
        quality_flag=quality_flag,
    )


@pytest.mark.asyncio
async def test_build_observation_station_without_reading_is_not_dropped():
    """A station with no accepted OpenAQ observation must still be
    returned — with aqi/observed_at/etc. all None and freshness
    'unavailable' — never omitted, and never coerced to aqi=0."""
    from app.services.india_aqi import _build_observation

    station = _fake_station()
    observation = await _build_observation(station, None)

    assert observation is not None
    assert observation.station_id == station.id
    assert observation.station_code == station.station_code
    assert observation.station_type == station.station_type
    assert observation.openaq_location_id == station.openaq_location_id
    assert observation.aqi is None
    assert observation.aqi_category is None
    assert observation.observed_at is None
    assert observation.fetched_at is None
    assert observation.data_source is None
    assert observation.quality_flag is None
    assert observation.freshness == "unavailable"


@pytest.mark.asyncio
async def test_build_observation_exposes_real_observed_at_and_freshness():
    """A station with a real (even stale) reading must expose the
    reading's actual timestamp, never a fabricated one, and classify
    freshness from it rather than discarding the observation."""
    from app.services.india_aqi import _build_observation

    station = _fake_station()
    old_timestamp = datetime(2020, 1, 1, tzinfo=UTC)
    reading = _fake_reading(timestamp=old_timestamp)

    observation = await _build_observation(station, reading)

    assert observation.observed_at == old_timestamp
    assert observation.aqi == reading.aqi
    assert observation.freshness == "stale"
    assert observation.data_source == "openaq"


@pytest.mark.asyncio
async def test_build_observation_live_reading_is_classified_live():
    from app.services.india_aqi import _build_observation

    station = _fake_station()
    reading = _fake_reading(timestamp=datetime.now(UTC))

    observation = await _build_observation(station, reading)

    assert observation.freshness == "live"


@pytest.mark.asyncio
async def test_get_india_aqi_observations_includes_stations_without_readings(
    monkeypatch,
):
    """Regression test for the reported bug: a station discovered by
    OpenAQ but not yet reporting a reading must still appear in the
    India AQI list, not be silently filtered out."""
    import uuid
    from unittest.mock import AsyncMock, patch

    from app.services import india_aqi as india_aqi_module

    id_with_reading = uuid.uuid4()
    id_without_reading = uuid.uuid4()
    station_with_reading = _fake_station(
        station_id=id_with_reading, station_code="OPENAQ_IN_1", openaq_location_id=1
    )
    station_without_reading = _fake_station(
        station_id=id_without_reading,
        station_code="OPENAQ_IN_2",
        openaq_location_id=2,
    )
    reading = _fake_reading()

    with (
        patch.object(
            india_aqi_module,
            "MonitoringStationRepository",
        ) as MockStationRepo,
        patch.object(
            india_aqi_module,
            "AQIReadingRepository",
        ) as MockReadingRepo,
    ):
        MockStationRepo.return_value.search_by_geography = AsyncMock(
            return_value=([station_with_reading, station_without_reading], 2)
        )
        MockReadingRepo.return_value.get_latest_by_stations = AsyncMock(
            return_value={id_with_reading: reading}
        )

        observations, total = await india_aqi_module.get_india_aqi_observations(
            session=None, filters=IndiaAQIFilters()
        )

    assert total == 2
    assert len(observations) == 2
    by_id = {obs.station_id: obs for obs in observations}
    assert by_id[id_with_reading].aqi == reading.aqi
    assert by_id[id_without_reading].aqi is None
    assert by_id[id_without_reading].freshness == "unavailable"
    # The batched lookup must be used instead of one query per station.
    MockReadingRepo.return_value.get_latest_by_stations.assert_awaited_once_with(
        [id_with_reading, id_without_reading]
    )


@pytest.mark.asyncio
async def test_heatmap_observations_never_coerce_missing_reading_to_zero_aqi(
    monkeypatch,
):
    """Regression test for the heatmap `aqi ?? 0` bug: a station with no
    reading must come back with aqi=None, never aqi=0 (which would render
    as clean air on the heatmap)."""
    from unittest.mock import AsyncMock, patch

    from app.services import india_aqi as india_aqi_module

    station = _fake_station(openaq_location_id=3)

    with patch.object(
        india_aqi_module, "MonitoringStationRepository"
    ) as MockStationRepo:
        MockStationRepo.return_value.get_india_heatmap_observations = AsyncMock(
            return_value=[(station, None)]
        )
        observations = await india_aqi_module.get_india_aqi_heatmap_observations(
            session=None
        )

    assert len(observations) == 1
    assert observations[0].aqi is None
    assert observations[0].freshness == "unavailable"


# ---------------------------------------------------------------------------
# Integration tests — require Postgres (auto-marked `integration`). BLOCKED
# in a sandbox without a database; written to run against the project's
# real docker-compose Postgres, following the same fixtures as test_aqi.py.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_india_aqi_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/aqi/india")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_india_aqi_empty_result(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/aqi/india?city=NoSuchCity", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_india_aqi_returns_observations_with_provenance(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _create_station(db_session, "IND_001", city="Pune")
    await _create_reading(db_session, station.id, aqi=142, quality_flag="good")
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/india?city=Pune", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    obs = items[0]
    assert obs["country"] == "India"
    assert obs["city"] == "Pune"
    assert obs["state"] == "Maharashtra"
    assert obs["data_source"] == "openaq"
    assert obs["aqi_method"] == "CPCB_PM25_NAAQS_INTERPOLATED"
    assert obs["aqi_category"] == "Unhealthy for Sensitive Groups"


@pytest.mark.asyncio
async def test_india_aqi_state_filter(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    mh_station = await _create_station(
        db_session, "IND_MH_001", city="Pune", state="Maharashtra"
    )
    dl_station = await _create_station(
        db_session, "IND_DL_001", city="Delhi", state="Delhi", lat=28.6, lon=77.2
    )
    await _create_reading(db_session, mh_station.id, aqi=100)
    await _create_reading(db_session, dl_station.id, aqi=200)
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/india?state=Delhi", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["city"] == "Delhi"


@pytest.mark.asyncio
async def test_india_aqi_category_filter(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    good_station = await _create_station(db_session, "IND_CAT_GOOD")
    bad_station = await _create_station(db_session, "IND_CAT_BAD")
    await _create_reading(db_session, good_station.id, aqi=30, pm25=10.0)
    await _create_reading(db_session, bad_station.id, aqi=350, pm25=280.0)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/aqi/india?category=Hazardous", headers=auth_headers
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["aqi_category"] == "Hazardous"


@pytest.mark.asyncio
async def test_india_aqi_is_openaq_only(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    live_station = await _create_station(db_session, "IND_SRC_LIVE")
    synthetic_station = await _create_station(db_session, "IND_SRC_SYN")
    await _create_reading(db_session, live_station.id, quality_flag="good")
    await _create_reading(db_session, synthetic_station.id, quality_flag="synthetic")
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/india?source=openaq", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["data_source"] == "openaq"

    synthetic_resp = await client.get(
        "/api/v1/aqi/india?source=synthetic", headers=auth_headers
    )
    assert synthetic_resp.status_code == 400


@pytest.mark.asyncio
async def test_india_aqi_bbox_filter(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    inside = await _create_station(db_session, "IND_BBOX_IN", lat=18.5, lon=73.8)
    outside = await _create_station(
        db_session, "IND_BBOX_OUT", city="Delhi", lat=28.6, lon=77.2
    )
    await _create_reading(db_session, inside.id)
    await _create_reading(db_session, outside.id)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/aqi/india?min_lat=17&min_lon=72&max_lat=19&max_lon=75",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["city"] == "Pune"


@pytest.mark.asyncio
async def test_india_aqi_invalid_bbox_partial(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/aqi/india?min_lat=10&min_lon=70", headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_india_aqi_invalid_bbox_inverted(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/aqi/india?min_lat=20&min_lon=70&max_lat=10&max_lon=80",
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_india_aqi_invalid_category_returns_400(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/v1/aqi/india?category=SuperBad", headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_india_aqi_invalid_source_returns_400(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/v1/aqi/india?source=satellite", headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_india_aqi_pagination_is_bounded(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    for i in range(3):
        station = await _create_station(db_session, f"IND_PAGE_{i}")
        await _create_reading(db_session, station.id)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/aqi/india?page=1&page_size=2", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["items"]) <= 2
    assert data["page_size"] == 2
    assert data["total"] >= 3


@pytest.mark.asyncio
async def test_india_aqi_rejects_oversized_page_size(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/v1/aqi/india?page_size=9999", headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_india_aqi_states_endpoint_reflects_real_data(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _create_station(db_session, "IND_STATES_MH", state="Maharashtra")
    await _create_station(
        db_session, "IND_STATES_DL", city="Delhi", state="Delhi", lat=28.6, lon=77.2
    )
    await _create_station(db_session, "IND_STATES_NULL", state=None)
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/india/states", headers=auth_headers)
    assert resp.status_code == 200
    states = resp.json()["data"]
    assert states == sorted(states)
    assert "Delhi" in states
    assert "Maharashtra" in states
    assert None not in states
    assert "" not in states


@pytest.mark.asyncio
async def test_india_aqi_states_endpoint_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/aqi/india/states")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_india_aqi_excludes_legacy_caaqms_fixture_stations(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """The six-station Pune/Mumbai CAAQMS fixtures (station_type="CAAQMS")
    also carry country="India" but belong to the separate city-scoped Live
    AQI feature, not the India-wide OpenAQ dataset. GET /api/v1/aqi/india
    must only ever return station_type="OpenAQ" stations."""
    discovered = await _create_station(
        db_session, "OPENAQ_IN_999", station_type="OpenAQ"
    )
    legacy_fixture = await _create_station(
        db_session, "PUNE_001", station_type="CAAQMS"
    )
    await _create_reading(db_session, discovered.id, aqi=90)
    await _create_reading(db_session, legacy_fixture.id, aqi=200)
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/india?city=Pune", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["aqi"] == 90


@pytest.mark.asyncio
async def test_india_aqi_and_heatmap_use_same_canonical_dataset(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """The India AQI list and the heatmap must reflect the same canonical
    OpenAQ-backed observation for a given station — never diverging
    datasets, per the requirement that they share one canonical flow."""
    discovered = await _create_station(
        db_session, "OPENAQ_IN_500", station_type="OpenAQ"
    )
    legacy_fixture = await _create_station(
        db_session, "PUNE_002", station_type="CAAQMS"
    )
    await _create_reading(db_session, discovered.id, aqi=145)
    await _create_reading(db_session, legacy_fixture.id, aqi=310)
    await db_session.commit()

    india_resp = await client.get("/api/v1/aqi/india", headers=auth_headers)
    heatmap_resp = await client.get("/api/v1/aqi/india/heatmap", headers=auth_headers)
    assert india_resp.status_code == 200
    assert heatmap_resp.status_code == 200

    india_items = india_resp.json()["data"]["items"]
    heatmap_items = heatmap_resp.json()["data"]

    india_station_ids = {item["station_id"] for item in india_items}
    heatmap_station_ids = {item["station_id"] for item in heatmap_items}
    assert india_station_ids == heatmap_station_ids

    india_by_station = {item["station_id"]: item["aqi"] for item in india_items}
    heatmap_by_station = {item["station_id"]: item["aqi"] for item in heatmap_items}
    assert india_by_station == heatmap_by_station
    assert str(discovered.id) in india_station_ids
    assert str(legacy_fixture.id) not in india_station_ids


@pytest.mark.asyncio
async def test_existing_pune_stations_endpoint_regression(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """Adding state/country to MonitoringStation and IndiaAQIObservation
    handling must not break the existing city-scoped /aqi/stations
    endpoint or its response shape."""
    await _create_station(db_session, "REGRESSION_001", city="Pune")
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/stations?city=Pune", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["items"]
    item = body["items"][0]
    assert item["country"] == "India"
    assert "city" in item and "station_code" in item


@pytest.mark.asyncio
async def test_existing_live_aqi_endpoint_regression(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    """GET /aqi/live must keep working (and keep its data_source logic
    correct) after resolve_data_source was extracted and reused by the
    India endpoint.

    Uses a non-Pune city deliberately: /aqi/live?city=Pune is now served
    exclusively by the six real, OpenAQ-matched Pune stations (see
    app/services/aqi_providers/pune_stations.py and
    test_aqi_pune_live.py), not by arbitrary MonitoringStation rows, so
    this general-endpoint regression check uses a city outside that
    special case."""
    station = await _create_station(db_session, "REGRESSION_LIVE_001", city="Nashik")
    await _create_reading(db_session, station.id, aqi=150, quality_flag="good")
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/live?city=Nashik", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data
    assert data[0]["data_source"] == "openaq"
