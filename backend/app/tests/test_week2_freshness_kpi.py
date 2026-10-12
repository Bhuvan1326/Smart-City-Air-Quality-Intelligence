"""Week 2 (D3): K1 data-freshness KPI — formula, exclusions and states.

Rows below are synthetic TEST FIXTURES for the formula; they say nothing about
real data coverage."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from geoalchemy2.elements import WKTElement

from app.core.security import hash_password
from app.models.monitoring import AQIReading, MonitoringStation
from app.models.user import User, UserRole
from app.services.kpi_freshness import compute_data_freshness_kpi

pytestmark = pytest.mark.integration
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _station(code, city="Pune", active=True):
    return MonitoringStation(
        name=code,
        station_code=code,
        city=city,
        ward_id="W01",
        operator="x",
        latitude=18.5,
        longitude=73.8,
        is_active=active,
        station_type="CAAQMS",
        geometry=WKTElement("POINT(73.8 18.5)", srid=4326),
    )


def _reading(station, minutes_ago, flag="good"):
    return AQIReading(
        station_id=station.id,
        pm25=20.0,
        aqi=70,
        latitude=18.5,
        longitude=73.8,
        timestamp=NOW - timedelta(minutes=minutes_ago),
        quality_flag=flag,
    )


@pytest.mark.asyncio
async def test_no_stations_is_reported_not_zero_percent(db_session):
    k = await compute_data_freshness_kpi(db_session, "Pune", now=NOW)
    assert k.status == "no_stations" and k.fresh_pct is None and k.stations_total == 0


@pytest.mark.asyncio
async def test_formula_exclusions_and_states(db_session):
    live1, live2, stale, synth_only, never, future, other_city, inactive = (
        _station("S1"),
        _station("S2"),
        _station("S3"),
        _station("S4"),
        _station("S5"),
        _station("S6"),
        _station("S7", city="Mumbai"),
        _station("S8", active=False),
    )
    db_session.add_all(
        [live1, live2, stale, synth_only, never, future, other_city, inactive]
    )
    await db_session.flush()
    db_session.add_all(
        [
            _reading(live1, 10),
            _reading(live2, 100),
            _reading(live2, 500),  # latest = 100 min -> recent (<=120)
            _reading(stale, 300),  # 5 h -> stale
            _reading(synth_only, 1, flag="synthetic"),  # synthetic never counts
            _reading(future, -330),  # +5.5 h in the future (tz bug)
            _reading(other_city, 5),
            _reading(inactive, 5),
            _reading(live1, 1, flag="invalid"),  # invalid ignored
        ]
    )
    await db_session.commit()

    k = await compute_data_freshness_kpi(db_session, "Pune", now=NOW)
    assert k.stations_total == 6  # S1..S6 (other city + inactive excluded)
    assert k.stations_live == 1  # S1 (10 min)
    assert k.stations_recent == 1  # S2 (100 min, still within 120)
    assert k.stations_stale == 1  # S3
    assert k.stations_unavailable == 3  # S4 synthetic-only, S5 never, S6 future ts
    assert k.stations_synthetic_only == 1
    assert k.fresh_pct == pytest.approx(33.3, abs=0.05)  # 2/6
    assert k.median_age_minutes == pytest.approx(100.0)  # ages 10, 100, 300
    assert k.status == "ok" and k.threshold_minutes == 120
    assert any("Synthetic" in c for c in k.caveats)


@pytest.mark.asyncio
async def test_only_synthetic_data_is_never_live(db_session):
    s = _station("ONLY_SYNTH")
    db_session.add(s)
    await db_session.flush()
    db_session.add(_reading(s, 1, flag="synthetic"))
    await db_session.commit()
    k = await compute_data_freshness_kpi(db_session, "Pune", now=NOW)
    assert k.stations_live == 0 and k.fresh_pct == 0.0 and k.status == "no_live_data"
    assert k.median_age_minutes is None


@pytest_asyncio.fixture
async def auth(db_session, client):
    db_session.add(
        User(
            email="k@t.in",
            hashed_password=hash_password("Passw0rd!123"),
            full_name="K T",
            role=UserRole.CITIZEN,
            city="Pune",
            is_active=True,
        )
    )
    await db_session.commit()
    r = await client.post(
        "/api/v1/auth/login", json={"email": "k@t.in", "password": "Passw0rd!123"}
    )
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_endpoint_requires_auth_and_returns_contract(client, auth):
    assert (await client.get("/api/v1/kpi/data-freshness?city=Pune")).status_code in (
        401,
        403,
    )
    r = await client.get("/api/v1/kpi/data-freshness?city=Pune", headers=auth)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["status"] == "no_stations" and d["fresh_pct"] is None
    assert {
        "stations_total",
        "stations_live",
        "stations_recent",
        "stations_stale",
        "live_threshold_minutes",
        "stations_unavailable",
        "stations_synthetic_only",
        "median_age_minutes",
        "definition",
        "caveats",
        "threshold_minutes",
        "as_of",
        "city",
    } <= set(d)
