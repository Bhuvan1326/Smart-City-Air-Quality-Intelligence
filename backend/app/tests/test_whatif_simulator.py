from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.pune_current_aqi import CurrentPuneAQI
from app.services.whatif_simulator import SimulationResult, WhatIfSimulator


class FakeResult:
    def __init__(self, row):
        self._row = row

    def one_or_none(self):
        return self._row

    def first(self):
        return self._row


def current_pune_aqi(avg_aqi=150.0, avg_pm25=90.0, wards=None):
    """A reliable current reading from the authoritative PUNE_LIVE_*
    stations — what `get_current_pune_aqi` returns when at least one live
    station has a live/recent, non-synthetic observation."""
    return CurrentPuneAQI(
        available=True,
        avg_aqi=avg_aqi,
        avg_pm25=avg_pm25,
        contributing_stations=["PUNE_LIVE_SPPU"],
        wards=wards or ["W01", "W02"],
    )


def unavailable_pune_aqi(
    reason="No authoritative Pune Live station currently has a live or recent observation.",
):
    return CurrentPuneAQI(available=False, reason=reason)


def attr_row(vehicular=40.0, industrial=20.0, construction=25.0, biomass=15.0):
    return SimpleNamespace(
        vehicular=vehicular,
        industrial=industrial,
        construction=construction,
        biomass=biomass,
    )


def wind_row(avg_wind_speed=3.0, avg_wind_direction=225.0):
    return SimpleNamespace(
        avg_wind_speed=avg_wind_speed, avg_wind_direction=avg_wind_direction
    )


def make_session(results):
    """A fake session for the raw `text()` queries that remain after the
    baseline-AQI lookup (attribution, then wind for weather scenarios)."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[FakeResult(r) for r in results])
    return session


def patch_current_pune_aqi(monkeypatch, value):
    """Pune's baseline AQI now comes from `get_current_pune_aqi` (the
    authoritative PUNE_LIVE_* stations) rather than a raw session query —
    see `app.services.pune_current_aqi`. Tests patch that call directly
    instead of faking its internal repository calls."""
    monkeypatch.setattr(
        "app.services.whatif_simulator.get_current_pune_aqi",
        AsyncMock(return_value=value),
    )


@pytest.mark.asyncio
async def test_unknown_scenario_raises():
    simulator = WhatIfSimulator(AsyncMock())

    with pytest.raises(ValueError, match="Unknown scenario"):
        await simulator.simulate(city="Pune", scenario_key="not_a_real_scenario")


@pytest.mark.asyncio
async def test_standard_scenario_reduces_aqi(monkeypatch):
    patch_current_pune_aqi(monkeypatch, current_pune_aqi())
    session = make_session([attr_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(
        city="Pune", scenario_key="restrict_truck_traffic"
    )

    assert isinstance(result, SimulationResult)
    assert result.data_available is True
    assert result.aqi_delta < 0
    assert result.simulated_aqi < result.baseline_aqi
    assert result.time_to_effect_hours == 1
    assert len(result.dispersion_map) == 49
    assert result.secondary_effects == []


@pytest.mark.asyncio
async def test_ward_scoped_scenario_passes_ward_param(monkeypatch):
    get_current = AsyncMock(return_value=current_pune_aqi(wards=["W03"]))
    monkeypatch.setattr(
        "app.services.whatif_simulator.get_current_pune_aqi", get_current
    )
    session = make_session([attr_row()])
    simulator = WhatIfSimulator(session)

    await simulator.simulate(
        city="Pune", scenario_key="shutdown_industrial_unit", ward_id="W03"
    )

    # The ward filter is now applied inside get_current_pune_aqi (scoped to
    # the authoritative stations) rather than via a raw SQL WHERE fragment.
    get_current.assert_awaited_once_with(session, ward_id="W03")
    attr_call_params = session.execute.call_args_list[0].args[1]
    assert attr_call_params["ward"] == "W03"


@pytest.mark.asyncio
async def test_pune_current_aqi_unavailable_returns_clear_state(monkeypatch):
    """Requirement 2/9: if no authoritative PUNE_LIVE_* station has a
    live/recent reading, the simulator must not fabricate a baseline — it
    must return an explicit unavailable result and skip the rest of the
    simulation (no attribution/wind queries)."""
    patch_current_pune_aqi(
        monkeypatch, unavailable_pune_aqi(reason="No live station reporting.")
    )
    session = make_session([])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(city="Pune", scenario_key="dust_suppression")

    assert result.data_available is False
    assert result.data_unavailable_reason == "No live station reporting."
    assert "unavailable" in result.reasoning.lower()
    assert result.baseline_aqi == 0.0
    assert result.simulated_aqi == 0.0
    assert result.aqi_delta == 0.0
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_pune_city_still_uses_raw_station_query(monkeypatch):
    """Cities other than Pune have no legacy/live station split, so they
    keep the original city-wide query instead of routing through
    get_current_pune_aqi."""
    get_current = AsyncMock()
    monkeypatch.setattr(
        "app.services.whatif_simulator.get_current_pune_aqi", get_current
    )
    aqi_row = SimpleNamespace(avg_aqi=120.0, avg_pm25=70.0, wards=["W01"])
    session = make_session([aqi_row, attr_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(city="Mumbai", scenario_key="dust_suppression")

    get_current.assert_not_awaited()
    assert result.baseline_aqi == 120.0


@pytest.mark.asyncio
async def test_diverts_traffic_scenario_adds_secondary_effect(monkeypatch):
    patch_current_pune_aqi(monkeypatch, current_pune_aqi())
    session = make_session([attr_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(
        city="Pune", scenario_key="road_closure", ward_id="W01"
    )

    assert len(result.secondary_effects) == 1
    assert result.secondary_effects[0]["effect"] == "traffic_diversion_increase"
    assert "W01" not in {result.secondary_effects[0]["ward_id"]}


@pytest.mark.asyncio
async def test_weather_scenario_queries_wind_and_lowers_confidence(monkeypatch):
    patch_current_pune_aqi(monkeypatch, current_pune_aqi())
    session = make_session([attr_row(), wind_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(
        city="Pune",
        scenario_key="weather_shift",
        weather_wind_speed_mps=8.0,
    )

    assert session.execute.await_count == 2
    assert result.confidence <= 0.67
    assert "Wind speed scenario" in result.reasoning


@pytest.mark.asyncio
async def test_weather_scenario_defaults_when_no_wind_data(monkeypatch):
    patch_current_pune_aqi(monkeypatch, current_pune_aqi())
    session = make_session([attr_row(), wind_row(None, None)])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(city="Pune", scenario_key="weather_shift")

    assert result is not None


@pytest.mark.asyncio
async def test_policy_bundle_default_reductions(monkeypatch):
    patch_current_pune_aqi(monkeypatch, current_pune_aqi())
    session = make_session([attr_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(city="Pune", scenario_key="policy_bundle")

    assert "Policy bundle applying" in result.reasoning
    assert result.aqi_delta < 0


@pytest.mark.asyncio
async def test_policy_bundle_custom_reductions(monkeypatch):
    patch_current_pune_aqi(monkeypatch, current_pune_aqi())
    session = make_session([attr_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(
        city="Pune",
        scenario_key="policy_bundle",
        custom_reductions={"vehicular": 0.5},
    )

    assert result.aqi_delta < 0


@pytest.mark.asyncio
async def test_missing_attribution_row_uses_defaults(monkeypatch):
    patch_current_pune_aqi(monkeypatch, current_pune_aqi())
    session = make_session([None])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(city="Pune", scenario_key="dust_suppression")

    assert result.baseline_aqi == 150.0
    assert result.affected_wards == ["W01", "W02"]


@pytest.mark.asyncio
async def test_custom_reduction_pct_overrides_default(monkeypatch):
    patch_current_pune_aqi(monkeypatch, current_pune_aqi())
    session = make_session([attr_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(
        city="Pune",
        scenario_key="ban_biomass_burning",
        custom_reduction_pct=0.10,
    )

    assert result.aqi_delta < 0


@pytest.mark.asyncio
async def test_list_scenarios_matches_scenario_params():
    simulator = WhatIfSimulator(AsyncMock())

    scenarios = await simulator.list_scenarios()

    assert len(scenarios) == len(WhatIfSimulator.SCENARIO_PARAMS)
    keys = {s["key"] for s in scenarios}
    assert "close_construction_site" in keys


def test_estimate_co2_impact_known_and_unknown_sources():
    simulator = WhatIfSimulator(AsyncMock())

    assert simulator._estimate_co2_impact("vehicular", 0.5) == -2250
    assert simulator._estimate_co2_impact("something_else", 1.0) == -1000


def test_nearest_ward_returns_none_for_unknown_ward():
    simulator = WhatIfSimulator(AsyncMock())

    assert simulator._nearest_ward("NOT_A_WARD") is None


def test_nearest_ward_returns_a_different_ward():
    simulator = WhatIfSimulator(AsyncMock())

    nearest = simulator._nearest_ward("W01")

    assert nearest is not None
    assert nearest != "W01"


def test_gaussian_dispersion_map_shape_and_keys():
    simulator = WhatIfSimulator(AsyncMock())

    points = simulator._gaussian_dispersion_map(
        ward_id="W01", aqi_delta=-10.0, city="Pune"
    )

    assert len(points) == 49
    for point in points:
        assert {"latitude", "longitude", "aqi_delta"} <= point.keys()


def test_gaussian_dispersion_map_unknown_ward_uses_default_center():
    simulator = WhatIfSimulator(AsyncMock())

    points = simulator._gaussian_dispersion_map(
        ward_id="UNKNOWN", aqi_delta=5.0, city="Pune"
    )

    assert len(points) == 49
