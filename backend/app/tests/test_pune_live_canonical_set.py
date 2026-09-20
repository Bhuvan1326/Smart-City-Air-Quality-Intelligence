from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from geoalchemy2.elements import WKTElement
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.civic_issue import WardAssignmentMethod
from app.models.monitoring import AQIReading, MonitoringStation
from app.services.aqi_providers import pune_stations
from app.services.civic_ward_assignment import WardAssignmentResult
from app.tests.test_helpers import make_db_session
from app.workers.tasks import aqi_ingestion

EXPECTED_CODES = [
    "PUNE_LIVE_SPPU",
    "PUNE_LIVE_DHANKAWADI",
    "PUNE_LIVE_HADAPSAR",
    "PUNE_LIVE_NIGDI",
    "PUNE_LIVE_PARK_STREET_WAKAD",
    "PUNE_LIVE_KATRAJ_DAIRY",
    "PUNE_LIVE_GAVALINAGAR",
    "PUNE_LIVE_BHUMKAR_NAGAR",
]
NEW_CODES = EXPECTED_CODES[4:]
RETIRED_CODES = {"PUNE_LIVE_ALANDI", "PUNE_LIVE_KARVE_ROAD"}


def _spec(code: str):
    return next(s for s in pune_stations.REQUIRED_STATIONS if s.station_code == code)


def _candidate(location_id: int, name: str, lat: float, lon: float, **extra) -> dict:
    return {
        "id": location_id,
        "name": name,
        "owner": {"name": "MPCB"},
        "country": {"code": "IN"},
        "coordinates": {"latitude": lat, "longitude": lon},
        **extra,
    }


@pytest.fixture(autouse=True)
def _stub_ward_assignment():
    with patch(
        "app.services.civic_ward_assignment.assign_ward",
        new=AsyncMock(
            return_value=WardAssignmentResult(
                ward_id=None, method=WardAssignmentMethod.UNAVAILABLE
            )
        ),
    ):
        yield


def _live_reading(location_id: int, name: str, **overrides):
    values = {
        "pm25": 61.0,
        "pm10": 98.0,
        "no2": 14.0,
        "so2": 4.0,
        "co": 0.9,
        "o3": 11.0,
        "temperature": 27.0,
        "humidity": 52.0,
        "wind_speed": 2.0,
        "wind_direction": 180.0,
        "openaq_location_id": location_id,
        "openaq_location_name": name,
        "distance_meters": 0.0,
        "observed_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# --- canonical registry -------------------------------------------------


def test_canonical_set_is_exactly_the_eight_required_stations_in_order():
    codes = [spec.station_code for spec in pune_stations.REQUIRED_STATIONS]
    assert codes == EXPECTED_CODES
    assert len(set(codes)) == 8
    assert pune_stations.required_station_codes() == EXPECTED_CODES


def test_alandi_and_karve_road_are_not_in_the_current_set():
    codes = {spec.station_code for spec in pune_stations.REQUIRED_STATIONS}
    names = {spec.display_name.lower() for spec in pune_stations.REQUIRED_STATIONS}
    assert not (codes & RETIRED_CODES)
    assert "alandi" not in names
    assert "karve road" not in names
    assert pune_stations.RETIRED_STATION_CODES == RETIRED_CODES
    assert pune_stations.RETIRED_OPENAQ_LOCATION_IDS == {12042, 5661}


@pytest.mark.parametrize(
    ("code", "display_name"),
    [
        ("PUNE_LIVE_PARK_STREET_WAKAD", "Park Street Wakad"),
        ("PUNE_LIVE_KATRAJ_DAIRY", "Katraj Dairy"),
        ("PUNE_LIVE_GAVALINAGAR", "Gavalinagar"),
        ("PUNE_LIVE_BHUMKAR_NAGAR", "Bhumkar Nagar"),
    ],
)
def test_new_stations_are_included(code, display_name):
    assert _spec(code).display_name == display_name


@pytest.mark.parametrize("code", NEW_CODES)
def test_new_stations_carry_no_fabricated_identity(code):
    spec = _spec(code)
    assert spec.approx_lat is None
    assert spec.approx_lon is None
    assert spec.provider is None
    assert spec.display_provider == "OpenAQ"
    assert not hasattr(spec, "openaq_location_id")
    assert spec.search_radius_m == pune_stations.REGION_SEARCH_RADIUS_M
    assert spec.search_limit == pune_stations.REGION_SEARCH_LIMIT


# --- matching against OpenAQ data --------------------------------------


@pytest.mark.parametrize(
    ("code", "openaq_name", "lat", "lon"),
    [
        ("PUNE_LIVE_PARK_STREET_WAKAD", "Park Street, Wakad, Pune - MPCB", 18.6, 73.76),
        ("PUNE_LIVE_KATRAJ_DAIRY", "Katraj Dairy, Pune - MPCB", 18.45, 73.86),
        ("PUNE_LIVE_GAVALINAGAR", "Gavalinagar, Pimpri Chinchwad - MPCB", 18.63, 73.8),
        ("PUNE_LIVE_BHUMKAR_NAGAR", "Bhumkar Nagar, Pune - MPCB", 18.61, 73.75),
    ],
)
def test_new_station_resolves_to_the_id_openaq_returned(code, openaq_name, lat, lon):
    candidates = [_candidate(910001, openaq_name, lat, lon)]
    match = pune_stations.match_station(candidates, _spec(code))
    assert match is not None
    assert match["id"] == 910001


@pytest.mark.parametrize(
    ("code", "openaq_name"),
    [
        ("PUNE_LIVE_PARK_STREET_WAKAD", "Wakad"),
        ("PUNE_LIVE_PARK_STREET_WAKAD", "Park Street"),
        ("PUNE_LIVE_KATRAJ_DAIRY", "Katraj"),
        ("PUNE_LIVE_BHUMKAR_NAGAR", "Bhumkar Chowk, Pune"),
        ("PUNE_LIVE_GAVALINAGAR", "Nigdi, Pune - IITM"),
    ],
)
def test_new_station_never_substitutes_a_different_station(code, openaq_name):
    candidates = [_candidate(910002, openaq_name, 18.55, 73.8)]
    assert pune_stations.match_station(candidates, _spec(code)) is None


def test_new_station_rejects_non_indian_and_non_pune_locations():
    spec = _spec("PUNE_LIVE_KATRAJ_DAIRY")
    foreign = _candidate(910003, "Katraj Dairy", 18.45, 73.86)
    foreign["country"] = {"code": "PK"}
    far_away = _candidate(910004, "Katraj Dairy", 28.6, 77.2)
    bad_coordinates = _candidate(910005, "Katraj Dairy", 95.0, 73.86)
    assert pune_stations.match_station([foreign], spec) is None
    assert pune_stations.match_station([far_away], spec) is None
    assert pune_stations.match_station([bad_coordinates], spec) is None


def test_retired_openaq_locations_are_never_matched_to_a_current_station():
    candidates = [
        _candidate(12042, "Nigdi", 18.652, 73.768),
        _candidate(5661, "Hadapsar", 18.5089, 73.9259),
    ]
    assert pune_stations.match_station(candidates, _spec("PUNE_LIVE_NIGDI")) is None
    assert pune_stations.match_station(candidates, _spec("PUNE_LIVE_HADAPSAR")) is None


# --- ingestion: resolution, no fabrication ------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("code", NEW_CODES)
async def test_new_station_is_created_from_verified_openaq_data(code):
    spec = _spec(code)
    session = make_db_session()
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = None
    latest_result = MagicMock()
    latest_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[lookup_result, latest_result, MagicMock()])
    session.flush = AsyncMock()

    openaq_name = f"{spec.display_name}, Pune - MPCB"
    candidates = [_candidate(910010, openaq_name, 18.5321, 73.8012)]

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
            new=AsyncMock(return_value=candidates),
        ) as search,
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=_live_reading(910010, openaq_name)),
        ),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, spec)

    assert outcome == "inserted"
    search.assert_awaited_once_with(
        pune_stations.PUNE_REGION_CENTER[0],
        pune_stations.PUNE_REGION_CENTER[1],
        radius_m=pune_stations.REGION_SEARCH_RADIUS_M,
        limit=pune_stations.REGION_SEARCH_LIMIT,
    )
    station = session.add.call_args_list[0].args[0]
    assert isinstance(station, MonitoringStation)
    assert station.station_code == code
    assert station.name == spec.display_name
    assert station.openaq_location_id == 910010
    assert station.latitude == 18.5321
    assert station.longitude == 73.8012
    assert station.country == "India"
    assert station.station_type == "OpenAQ"
    assert station.is_active is True
    assert station.data_source_url.endswith("/910010")


@pytest.mark.asyncio
async def test_unmatched_new_station_is_reported_not_fabricated():
    spec = _spec("PUNE_LIVE_GAVALINAGAR")
    session = make_db_session()
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[lookup_result])

    candidates = [_candidate(910020, "Some Other Pune Station", 18.55, 73.8)]
    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
        new=AsyncMock(return_value=candidates),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, spec)

    assert outcome == "unresolved_no_confident_match"
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_new_station_without_observation_stores_nothing():
    spec = _spec("PUNE_LIVE_KATRAJ_DAIRY")
    session = make_db_session()
    existing = SimpleNamespace(
        id="station-uuid",
        station_code=spec.station_code,
        openaq_location_id=910030,
        name=spec.display_name,
        openaq_location_stale_since=None,
    )
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = existing
    session.execute = AsyncMock(side_effect=[lookup_result])

    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
        new=AsyncMock(return_value=None),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(session, spec)

    assert outcome == "no_current_observation"
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_region_search_is_shared_across_new_stations_in_one_run():
    candidates = [
        _candidate(910041, "Park Street Wakad, Pune - MPCB", 18.6, 73.76),
        _candidate(910042, "Katraj Dairy, Pune - MPCB", 18.45, 73.86),
    ]
    search = AsyncMock(return_value=candidates)
    cache: dict = {}

    with patch(
        "app.workers.tasks.aqi_ingestion.openaq.search_locations_near", new=search
    ):
        for code, location_id, name in (
            ("PUNE_LIVE_PARK_STREET_WAKAD", 910041, "Park Street Wakad"),
            ("PUNE_LIVE_KATRAJ_DAIRY", 910042, "Katraj Dairy"),
        ):
            session = make_db_session()
            lookup_result = MagicMock()
            lookup_result.scalar_one_or_none.return_value = None
            latest_result = MagicMock()
            latest_result.scalar_one_or_none.return_value = None
            session.execute = AsyncMock(
                side_effect=[lookup_result, latest_result, MagicMock()]
            )
            session.flush = AsyncMock()
            with patch(
                "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
                new=AsyncMock(return_value=_live_reading(location_id, name)),
            ):
                outcome = await aqi_ingestion._ingest_one_pune_station(
                    session, _spec(code), cache
                )
            assert outcome == "inserted"

    assert search.await_count == 1


@pytest.mark.asyncio
async def test_retirement_statement_targets_only_alandi_and_karve_road():
    session = make_db_session()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=2))

    retired = await aqi_ingestion._retire_legacy_pune_live_stations(session)

    assert retired == 2
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert sql.upper().startswith("UPDATE MONITORING_STATIONS")
    assert "PUNE_LIVE_ALANDI" in sql
    assert "PUNE_LIVE_KARVE_ROAD" in sql
    assert "12042" in sql
    assert "5661" in sql


# --- database-backed behaviour -----------------------------------------


async def _add_station(
    session: AsyncSession,
    code: str,
    *,
    name: str,
    location_id: int | None,
    is_active: bool = True,
    station_type: str = "OpenAQ",
    lat: float = 18.52,
    lon: float = 73.85,
) -> MonitoringStation:
    station = MonitoringStation(
        name=name,
        station_code=code,
        city="Pune",
        state="Maharashtra",
        country="India",
        operator="OpenAQ",
        latitude=lat,
        longitude=lon,
        geometry=WKTElement(f"POINT({lon} {lat})", srid=4326),
        is_active=is_active,
        station_type=station_type,
        openaq_location_id=location_id,
    )
    session.add(station)
    await session.flush()
    return station


@pytest.mark.asyncio
async def test_live_api_returns_only_the_eight_current_stations(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _add_station(
        db_session,
        "PUNE_LIVE_SPPU",
        name="Savitribai Phule Pune University",
        location_id=1,
    )
    await _add_station(
        db_session,
        "PUNE_LIVE_ALANDI",
        name="Alandi",
        location_id=12042,
        is_active=False,
    )
    await _add_station(
        db_session,
        "PUNE_LIVE_KARVE_ROAD",
        name="Karve Road",
        location_id=5661,
        is_active=False,
    )
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/live?city=Pune", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [item["station_code"] for item in data] == EXPECTED_CODES
    assert not ({item["station_code"] for item in data} & RETIRED_CODES)
    names = {item["station_name"] for item in data}
    assert "Alandi" not in names
    assert "Karve Road" not in names


@pytest.mark.asyncio
async def test_live_api_ignores_a_retired_row_even_if_it_is_active(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _add_station(
        db_session, "PUNE_LIVE_ALANDI", name="Alandi", location_id=12042, is_active=True
    )
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/live?city=Pune", headers=auth_headers)

    codes = [item["station_code"] for item in resp.json()["data"]]
    assert codes == EXPECTED_CODES


@pytest.mark.asyncio
async def test_live_api_reports_null_aqi_as_null_not_zero(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    station = await _add_station(
        db_session, "PUNE_LIVE_KATRAJ_DAIRY", name="Katraj Dairy", location_id=910050
    )
    await db_session.commit()

    resp = await client.get("/api/v1/aqi/live?city=Pune", headers=auth_headers)

    by_code = {item["station_code"]: item for item in resp.json()["data"]}
    katraj = by_code["PUNE_LIVE_KATRAJ_DAIRY"]
    assert katraj["station"]["id"] == str(station.id)
    assert katraj["reading"] is None
    assert katraj["aqi_category"] is None
    assert katraj["data_source"] == "unavailable"


@pytest.mark.asyncio
async def test_station_selector_lists_only_current_live_stations(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict
):
    await _add_station(
        db_session,
        "PUNE_LIVE_SPPU",
        name="Savitribai Phule Pune University",
        location_id=1,
    )
    await _add_station(
        db_session,
        "PUNE_LIVE_ALANDI",
        name="Alandi",
        location_id=12042,
        is_active=False,
    )
    await _add_station(
        db_session,
        "PUNE_001",
        name="Karve Road CAAQMS",
        location_id=None,
        station_type="CAAQMS",
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/aqi/stations?city=Pune&live_only=true", headers=auth_headers
    )

    assert resp.status_code == 200
    codes = [item["station_code"] for item in resp.json()["data"]["items"]]
    assert codes == ["PUNE_LIVE_SPPU"]


@pytest.mark.asyncio
async def test_retirement_deactivates_but_preserves_history_and_is_idempotent(
    db_session: AsyncSession,
):
    alandi = await _add_station(
        db_session, "PUNE_LIVE_ALANDI", name="Alandi", location_id=12042
    )
    karve = await _add_station(
        db_session, "PUNE_LIVE_KARVE_ROAD", name="Karve Road", location_id=5661
    )
    db_session.add(
        AQIReading(
            station_id=alandi.id,
            pm25=40.0,
            aqi=110,
            timestamp=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
            latitude=alandi.latitude,
            longitude=alandi.longitude,
            quality_flag="good",
        )
    )
    await db_session.commit()

    first = await aqi_ingestion._retire_legacy_pune_live_stations(db_session)
    await db_session.commit()
    second = await aqi_ingestion._retire_legacy_pune_live_stations(db_session)
    await db_session.commit()

    assert first == 2
    assert second == 0
    rows = (
        await db_session.execute(
            select(MonitoringStation.station_code, MonitoringStation.is_active).where(
                MonitoringStation.id.in_([alandi.id, karve.id])
            )
        )
    ).all()
    assert {code: active for code, active in rows} == {
        "PUNE_LIVE_ALANDI": False,
        "PUNE_LIVE_KARVE_ROAD": False,
    }
    readings = await db_session.scalar(
        select(func.count())
        .select_from(AQIReading)
        .where(AQIReading.station_id == alandi.id)
    )
    assert readings == 1


@pytest.mark.asyncio
async def test_india_discovery_never_revives_a_retired_station(
    db_session: AsyncSession,
):
    alandi = await _add_station(
        db_session,
        "PUNE_LIVE_ALANDI",
        name="Alandi",
        location_id=12042,
        is_active=False,
    )
    await db_session.commit()

    location = SimpleNamespace(
        openaq_location_id=12042,
        name="Alandi, Pune - IITM",
        latitude=18.678,
        longitude=73.904,
        city="Pune",
        state="Maharashtra",
        country_code="IN",
        sensor_parameters=["pm25"],
    )
    station_id, outcome = await aqi_ingestion._ensure_discovered_station(
        db_session, location
    )
    await db_session.commit()

    assert station_id == alandi.id
    assert outcome == "retired_preserved"
    await db_session.refresh(alandi)
    assert alandi.is_active is False
    assert alandi.name == "Alandi"


@pytest.mark.asyncio
async def test_discovery_created_row_is_adopted_not_duplicated(
    db_session: AsyncSession,
):
    spec = _spec("PUNE_LIVE_KATRAJ_DAIRY")
    discovered = await _add_station(
        db_session,
        aqi_ingestion._station_code_for_openaq_location(910060),
        name="Katraj Dairy, Pune - MPCB",
        location_id=910060,
        lat=18.4501,
        lon=73.8602,
    )
    db_session.add(
        AQIReading(
            station_id=discovered.id,
            pm25=33.0,
            aqi=95,
            timestamp=datetime(2026, 9, 10, 6, 0, tzinfo=UTC),
            latitude=18.4501,
            longitude=73.8602,
            quality_flag="good",
        )
    )
    await db_session.commit()

    candidates = [_candidate(910060, "Katraj Dairy, Pune - MPCB", 18.4501, 73.8602)]
    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
            new=AsyncMock(return_value=candidates),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=None),
        ),
    ):
        outcome = await aqi_ingestion._ingest_one_pune_station(db_session, spec)
        await db_session.commit()

    assert outcome == "no_current_observation"
    rows = (
        (
            await db_session.execute(
                select(MonitoringStation).where(
                    MonitoringStation.openaq_location_id == 910060
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    adopted = rows[0]
    assert adopted.id == discovered.id
    assert adopted.station_code == "PUNE_LIVE_KATRAJ_DAIRY"
    assert adopted.name == "Katraj Dairy"
    assert adopted.station_type == "OpenAQ"
    assert adopted.country == "India"
    assert adopted.is_active is True
    kept = await db_session.scalar(
        select(func.count())
        .select_from(AQIReading)
        .where(AQIReading.station_id == discovered.id)
    )
    assert kept == 1


@pytest.mark.asyncio
async def test_repeated_resolution_never_creates_duplicate_openaq_ids(
    db_session: AsyncSession,
):
    spec = _spec("PUNE_LIVE_BHUMKAR_NAGAR")
    candidates = [_candidate(910070, "Bhumkar Nagar, Pune - MPCB", 18.61, 73.75)]

    with (
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.search_locations_near",
            new=AsyncMock(return_value=candidates),
        ),
        patch(
            "app.workers.tasks.aqi_ingestion.openaq.fetch_location_reading",
            new=AsyncMock(return_value=_live_reading(910070, "Bhumkar Nagar")),
        ),
    ):
        outcomes = []
        for _ in range(3):
            outcome = await aqi_ingestion._ingest_one_pune_station(db_session, spec)
            outcomes.append(outcome)
            await db_session.commit()

    assert outcomes[0] == "inserted"
    assert outcomes[1:] == ["no_new_observation", "no_new_observation"]
    stations = await db_session.scalar(
        select(func.count())
        .select_from(MonitoringStation)
        .where(MonitoringStation.openaq_location_id == 910070)
    )
    assert stations == 1
    readings = await db_session.scalar(select(func.count()).select_from(AQIReading))
    assert readings == 1
