from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.whatif_simulator import SimulationResult, WhatIfSimulator


class FakeResult:
    def __init__(self, row):
        self._row = row

    def one_or_none(self):
        return self._row

    def first(self):
        return self._row


def aqi_row(avg_aqi=150.0, avg_pm25=90.0, wards=None):
    return SimpleNamespace(
        avg_aqi=avg_aqi, avg_pm25=avg_pm25, wards=wards or ["W01", "W02"]
    )


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
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[FakeResult(r) for r in results])
    return session


@pytest.mark.asyncio
async def test_unknown_scenario_raises():
    simulator = WhatIfSimulator(AsyncMock())

    with pytest.raises(ValueError, match="Unknown scenario"):
        await simulator.simulate(city="Pune", scenario_key="not_a_real_scenario")


@pytest.mark.asyncio
async def test_standard_scenario_reduces_aqi():
    session = make_session([aqi_row(), attr_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(
        city="Pune", scenario_key="restrict_truck_traffic"
    )

    assert isinstance(result, SimulationResult)
    assert result.aqi_delta < 0
    assert result.simulated_aqi < result.baseline_aqi
    assert result.time_to_effect_hours == 1
    assert len(result.dispersion_map) == 49
    assert result.secondary_effects == []


@pytest.mark.asyncio
async def test_ward_scoped_scenario_passes_ward_param():
    session = make_session([aqi_row(), attr_row()])
    simulator = WhatIfSimulator(session)

    await simulator.simulate(
        city="Pune", scenario_key="shutdown_industrial_unit", ward_id="W03"
    )

    first_call_params = session.execute.call_args_list[0].args[1]
    second_call_params = session.execute.call_args_list[1].args[1]
    assert first_call_params["ward"] == "W03"
    assert second_call_params["ward"] == "W03"


@pytest.mark.asyncio
async def test_diverts_traffic_scenario_adds_secondary_effect():
    session = make_session([aqi_row(), attr_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(
        city="Pune", scenario_key="road_closure", ward_id="W01"
    )

    assert len(result.secondary_effects) == 1
    assert result.secondary_effects[0]["effect"] == "traffic_diversion_increase"
    assert "W01" not in {result.secondary_effects[0]["ward_id"]}


@pytest.mark.asyncio
async def test_weather_scenario_queries_wind_and_lowers_confidence():
    session = make_session([aqi_row(), attr_row(), wind_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(
        city="Pune",
        scenario_key="weather_shift",
        weather_wind_speed_mps=8.0,
    )

    assert session.execute.await_count == 3
    assert result.confidence <= 0.67
    assert "Wind speed scenario" in result.reasoning


@pytest.mark.asyncio
async def test_weather_scenario_defaults_when_no_wind_data():
    session = make_session([aqi_row(), attr_row(), wind_row(None, None)])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(city="Pune", scenario_key="weather_shift")

    assert result is not None


@pytest.mark.asyncio
async def test_policy_bundle_default_reductions():
    session = make_session([aqi_row(), attr_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(city="Pune", scenario_key="policy_bundle")

    assert "Policy bundle applying" in result.reasoning
    assert result.aqi_delta < 0


@pytest.mark.asyncio
async def test_policy_bundle_custom_reductions():
    session = make_session([aqi_row(), attr_row()])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(
        city="Pune",
        scenario_key="policy_bundle",
        custom_reductions={"vehicular": 0.5},
    )

    assert result.aqi_delta < 0


@pytest.mark.asyncio
async def test_missing_rows_use_defaults():
    session = make_session([None, None])
    simulator = WhatIfSimulator(session)

    result = await simulator.simulate(city="Pune", scenario_key="dust_suppression")

    assert result.baseline_aqi == 80.0
    assert result.affected_wards == ["W01"]


@pytest.mark.asyncio
async def test_custom_reduction_pct_overrides_default():
    session = make_session([aqi_row(), attr_row()])
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
