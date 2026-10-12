"""Week 2 data-correctness regressions: D1 (observation time), D3 (units),
D4 (no-data is not AQI 500).

PAYLOAD PROVENANCE: the OpenAQ payloads below are constructed from the
documented OpenAQ v3 response shape (location.instruments[].sensors[].parameter
{name, units}; /latest results[] {sensorsId, value, datetime.utc}). They are
representative fixtures, NOT captures from the live API (no credentials/network
were available). Live verification remains an open item.
"""

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.services.aqi_providers import openaq
from app.services.aqi_providers.openaq import LiveReading
from app.services.aqi_providers.units import normalise_reading
from app.workers.tasks import aqi_ingestion
from app.workers.tasks.aqi_ingestion import (
    _build_reading_for_station,
    _calculate_aqi_from_pm25,
    calculate_overall_aqi,
)

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------- D3: units --
def test_ug_m3_passes_through_and_co_is_converted_to_mg_m3():
    assert normalise_reading("pm25", 40.0, "µg/m³").value == 40.0
    assert normalise_reading("no2", 55.0, "ug/m3").value == 55.0
    assert normalise_reading("co", 600.0, "µg/m³").value == pytest.approx(0.6)
    assert normalise_reading("co", 0.6, "mg/m3").value == pytest.approx(0.6)


def test_ppb_and_ppm_gas_conversion_at_25c_1atm():
    # ug/m3 = ppb * MW / 24.45
    assert normalise_reading("no2", 20.0, "ppb").value == pytest.approx(
        20 * 46.0055 / 24.45
    )
    assert normalise_reading("o3", 30.0, "ppb").value == pytest.approx(
        30 * 47.9982 / 24.45
    )
    # CO ppm -> mg/m3: 1 ppm ~ 1.1456 mg/m3
    assert normalise_reading("co", 1.0, "ppm").value == pytest.approx(
        28.0101 / 24.45, rel=1e-6
    )


@pytest.mark.parametrize(
    "param,value,units,reason_prefix",
    [
        ("co", 1.0, None, "units_missing_for_gas"),
        ("no2", 1.0, "", "units_missing_for_gas"),
        ("co", 1.0, "furlongs", "unsupported_units"),
        ("pm25", 10.0, "ppm", "invalid_units_for_pm25"),
        ("pm25", -1.0, "ug/m3", "negative"),
        ("pm25", float("nan"), "ug/m3", "non_finite"),
        ("pm25", 99999.0, "ug/m3", "above_plausible_maximum"),
        ("co", 900.0, "mg/m3", "above_plausible_maximum"),
    ],
)
def test_unsupported_or_invalid_readings_are_rejected(
    param, value, units, reason_prefix
):
    out = normalise_reading(param, value, units)
    assert out.value is None
    assert out.reason.startswith(reason_prefix)


def test_pm_without_units_is_assumed_ug_m3_and_flagged():
    out = normalise_reading("pm25", 33.0, None)
    assert out.value == 33.0 and out.assumed_units is True


def _location(units: dict[str, str | None]):
    sensors = []
    for i, (name, u) in enumerate(units.items(), start=1):
        parameter = {"name": name}
        if u is not None:
            parameter["units"] = u
        sensors.append({"id": i, "parameter": parameter})
    return {"id": 77, "name": "Fixture Station", "instruments": [{"sensors": sensors}]}


def _latest(values: dict[int, tuple[float, datetime]]):
    return {
        "results": [
            {
                "sensorsId": sid,
                "value": v,
                "datetime": {"utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ")},
            }
            for sid, (v, ts) in values.items()
        ]
    }


async def _fetch(location, payload):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=payload, headers={"date": format_datetime(NOW, usegmt=True)}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await openaq.fetch_location_latest(client, location)


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    async def noop(*a, **k):
        return None

    monkeypatch.setattr(openaq, "_acquire_rate_slot", noop)


@pytest.mark.asyncio
async def test_co_in_ug_m3_does_not_blow_up_aqi_to_500():
    """The D3 scenario: CO reported in ug/m3 (600) used to be read as mg/m3 and
    clamp the AQI to 500. After normalisation it is 0.6 mg/m3 (sub-index ~30)."""
    ts = NOW - timedelta(minutes=10)
    reading = await _fetch(
        _location({"pm25": "µg/m³", "co": "µg/m³"}),
        _latest({1: (25.0, ts), 2: (600.0, ts)}),
    )
    assert reading.co == pytest.approx(0.6)
    aqi = calculate_overall_aqi(pm25=reading.pm25, co=reading.co)
    assert aqi == 41  # PM2.5 25 ug/m3 dominates; CO sub-index is 30


@pytest.mark.asyncio
async def test_gas_with_unknown_units_is_dropped_not_guessed():
    ts = NOW - timedelta(minutes=5)

    def handler(request: httpx.Request) -> httpx.Response:
        # the per-sensor fallback lookup also lacks units
        if "/sensors/" in request.url.path:
            return httpx.Response(
                200,
                json={"results": [{"id": 2, "parameter": {"name": "co"}}]},
                headers={"date": format_datetime(NOW, usegmt=True)},
            )
        return httpx.Response(
            200,
            json=_latest({1: (25.0, ts), 2: (600.0, ts)}),
            headers={"date": format_datetime(NOW, usegmt=True)},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        reading = await openaq.fetch_location_latest(
            client, _location({"pm25": "µg/m³", "co": None})
        )
    assert reading.pm25 == 25.0
    assert reading.co is None


@pytest.mark.asyncio
async def test_rejected_pollutant_does_not_make_location_look_fresher():
    old, newest = NOW - timedelta(hours=3), NOW - timedelta(minutes=1)
    reading = await _fetch(
        _location({"pm25": "µg/m³", "no2": "ppb"}),
        _latest({1: (25.0, old), 2: (-5.0, newest)}),  # invalid NO2 is the newest
    )
    assert reading.no2 is None
    assert reading.observed_at == old
    assert reading.is_stale is True


@pytest.mark.asyncio
async def test_naive_utc_timestamp_is_treated_as_utc():
    payload = {
        "results": [
            {"sensorsId": 1, "value": 20.0, "datetime": {"utc": "2026-09-04T11:55:00"}}
        ]
    }
    reading = await _fetch(_location({"pm25": "µg/m³"}), payload)
    assert reading.observed_at == datetime(2026, 9, 4, 11, 55, tzinfo=UTC)


# ------------------------------------------------- D4: no data is not AQI 500 --
def test_no_valid_pollutant_returns_none_not_500():
    assert calculate_overall_aqi() is None
    assert calculate_overall_aqi(pm25=-3.0) is None
    assert calculate_overall_aqi(pm25=-3.0, no2=None, co=-1.0) is None


def test_zero_pm25_is_aqi_zero_not_500():
    assert calculate_overall_aqi(pm25=0.0) == 0
    assert _calculate_aqi_from_pm25(0.0) == 0


def test_genuinely_extreme_value_still_clamps_to_500():
    assert calculate_overall_aqi(pm25=900.0) == 500


def _live(**kw):
    base = dict(
        pm25=25.0,
        pm10=None,
        no2=None,
        so2=None,
        co=None,
        o3=None,
        temperature=None,
        humidity=None,
        wind_speed=None,
        wind_direction=None,
        observed_at=NOW - timedelta(minutes=5),
        openaq_location_id=5,
        openaq_location_name="X",
        distance_meters=0.0,
        is_stale=False,
        age_seconds=300.0,
    )
    base.update(kw)
    return LiveReading(**base)


@pytest.mark.asyncio
async def test_build_reading_skips_when_no_valid_aqi(monkeypatch):
    monkeypatch.setattr(openaq, "is_configured", lambda: True)

    async def fake(lat, lon):
        return _live(pm25=-4.0)

    monkeypatch.setattr(openaq, "fetch_nearest_reading", fake)
    assert await _build_reading_for_station({"lat": 18.5, "lon": 73.8}, 0) is None


@pytest.mark.asyncio
async def test_build_reading_flags_stale_and_keeps_observed_at(monkeypatch):
    monkeypatch.setattr(openaq, "is_configured", lambda: True)
    stale_at = NOW - timedelta(hours=5)

    async def fake(lat, lon):
        return _live(observed_at=stale_at, is_stale=True, age_seconds=18000.0)

    monkeypatch.setattr(openaq, "fetch_nearest_reading", fake)
    data, flag, raw = await _build_reading_for_station({"lat": 18.5, "lon": 73.8}, 0)
    assert flag == "stale"
    assert aqi_ingestion._observed_at_from_raw(raw) == stale_at
    assert data["aqi"] is not None


def test_observed_at_from_raw_rejects_missing_or_garbage():
    assert aqi_ingestion._observed_at_from_raw("{}") is None
    assert aqi_ingestion._observed_at_from_raw("not json") is None
    assert aqi_ingestion._observed_at_from_raw('{"observed_at": "nope"}') is None


# --------------------------------------- D1: timestamp = observation, not fetch --
@pytest.mark.asyncio
@pytest.mark.integration
async def test_legacy_ingest_stores_observation_time_and_dedupes(
    test_engine, monkeypatch
):
    from app.models.monitoring import AQIReading, MonitoringStation

    monkeypatch.setattr(
        settings,
        "DATABASE_URL",
        test_engine.url.render_as_string(hide_password=False),
    )
    station = {
        "code": "W01_FIXTURE",
        "name": "Fixture",
        "lat": 18.5,
        "lon": 73.8,
        "ward": "W01",
    }
    monkeypatch.setattr(aqi_ingestion, "ALL_STATIONS", {"Pune": [station]})

    observed = datetime.now(UTC) - timedelta(hours=3)  # clearly stale
    raw = json.dumps({"source": "openaq", "observed_at": observed.isoformat()})
    data = {
        "pm25": 40.0,
        "pm10": None,
        "no2": None,
        "so2": None,
        "co": None,
        "o3": None,
        "aqi": 100,
        "temperature": None,
        "humidity": None,
        "wind_speed": None,
        "wind_direction": None,
    }

    async def fake_build(s, hour):
        return data, "stale", raw

    monkeypatch.setattr(aqi_ingestion, "_build_reading_for_station", fake_build)

    await aqi_ingestion._fetch_aqi_async()
    await aqi_ingestion._fetch_aqi_async()  # same observation polled again

    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with async_sessionmaker(test_engine, expire_on_commit=False)() as s:
        rows = (await s.execute(select(AQIReading))).scalars().all()
        st = (await s.execute(select(MonitoringStation))).scalars().all()
    assert len(rows) == 1, "same observation must not be re-inserted"
    assert rows[0].timestamp == observed  # NOT the fetch time
    assert rows[0].quality_flag == "stale"
    assert st[0].last_data_at == observed
