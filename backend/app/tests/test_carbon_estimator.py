from unittest.mock import AsyncMock

import pytest
from app.services.carbon_estimator import CarbonEstimatorService, EmissionEstimate


class FakeRow:
    def __init__(self, **kwargs):
        self._mapping = kwargs


def make_session(rows):
    session = AsyncMock()
    session.execute.return_value = rows
    return session


@pytest.mark.asyncio
async def test_estimate_city_emissions_with_carbon_ton_and_rate():
    rows = [
        FakeRow(
            source_type="vehicular",
            count=5,
            total_rate_kg_hr=None,
            total_carbon_ton_yr=None,
            avg_violations=1.0,
        ),
        FakeRow(
            source_type="industrial",
            count=2,
            total_rate_kg_hr=100.0,
            total_carbon_ton_yr=500.0,
            avg_violations=0.5,
        ),
        FakeRow(
            source_type="construction",
            count=3,
            total_rate_kg_hr=None,
            total_carbon_ton_yr=None,
            avg_violations=0.0,
        ),
        FakeRow(
            source_type="biomass",
            count=1,
            total_rate_kg_hr=None,
            total_carbon_ton_yr=None,
            avg_violations=0.0,
        ),
    ]
    session = make_session(rows)
    service = CarbonEstimatorService(session)

    result = await service.estimate_city_emissions("Pune")

    assert result["city"] == "Pune"
    assert result["total_co2_kg_per_day"] > 0
    assert set(result["source_breakdown"].keys()) == {
        "vehicular",
        "industrial",
        "construction",
        "biomass",
    }
    assert len(result["reduction_scenarios"]) == 4
    for scenario in result["reduction_scenarios"]:
        assert "scenario" in scenario
        assert "aqi_delta_estimate" in scenario
    assert result["data_classification"] == "CALCULATED"
    assert "IPCC" in result["emission_factor_source"]
    assert result["generated_at"]  # non-empty ISO timestamp


@pytest.mark.asyncio
async def test_estimate_city_emissions_no_sources_zero_totals():
    session = make_session([])
    service = CarbonEstimatorService(session)

    result = await service.estimate_city_emissions("Mumbai")

    assert result["total_co2_kg_per_day"] == 0
    assert result["source_breakdown"] == {}
    assert result["total_pm25_kg_per_day"] == 0


@pytest.mark.asyncio
async def test_estimate_city_emissions_unknown_source_type_fallback_count():
    rows = [
        FakeRow(
            source_type="dust",
            count=4,
            total_rate_kg_hr=None,
            total_carbon_ton_yr=None,
            avg_violations=0.0,
        )
    ]
    session = make_session(rows)
    service = CarbonEstimatorService(session)

    result = await service.estimate_city_emissions("Pune")

    assert result["source_breakdown"]["dust"]["co2_kg_per_day"] == round(4 * 500.0, 1)


@pytest.mark.asyncio
async def test_estimate_enforcement_impact_vehicular_shutdown():
    session = AsyncMock()
    service = CarbonEstimatorService(session)

    result = await service.estimate_enforcement_impact(
        "vehicular", "shutdown", duration_days=10
    )

    assert result["source_type"] == "vehicular"
    assert result["reduction_pct"] == 30
    assert result["co2_saved_kg"] > 0
    assert result["estimated_aqi_delta"] <= 0
    assert result["data_classification"] == "ESTIMATED"
    assert result["generated_at"]


@pytest.mark.asyncio
async def test_estimate_enforcement_impact_vehicular_other_action():
    service = CarbonEstimatorService(AsyncMock())

    result = await service.estimate_enforcement_impact("vehicular", "fine")

    assert result["reduction_pct"] == 15


@pytest.mark.asyncio
async def test_estimate_enforcement_impact_industrial_shutdown_vs_other():
    service = CarbonEstimatorService(AsyncMock())

    shutdown = await service.estimate_enforcement_impact("industrial", "shutdown")
    other = await service.estimate_enforcement_impact("industrial", "notice")

    assert shutdown["reduction_pct"] == 100
    assert other["reduction_pct"] == 40


@pytest.mark.asyncio
async def test_estimate_enforcement_impact_construction_shutdown_vs_other():
    service = CarbonEstimatorService(AsyncMock())

    shutdown = await service.estimate_enforcement_impact("construction", "shutdown")
    other = await service.estimate_enforcement_impact("construction", "warning")

    assert shutdown["reduction_pct"] == 100
    assert other["reduction_pct"] == 60


@pytest.mark.asyncio
async def test_estimate_enforcement_impact_biomass():
    service = CarbonEstimatorService(AsyncMock())

    result = await service.estimate_enforcement_impact("biomass", "notice")

    assert result["reduction_pct"] == 80


@pytest.mark.asyncio
async def test_estimate_enforcement_impact_unknown_source_type_default():
    service = CarbonEstimatorService(AsyncMock())

    result = await service.estimate_enforcement_impact("unknown_type", "notice")

    assert result["daily_co2_baseline_kg"] == 500.0
    assert result["reduction_pct"] == 20


def test_estimate_by_type_vehicular_uses_default_when_no_rate():
    service = CarbonEstimatorService(AsyncMock())

    estimate = service._estimate_by_type(
        "vehicular", {"count": 2, "total_rate_kg_hr": None, "total_carbon_ton_yr": None}
    )

    assert isinstance(estimate, EmissionEstimate)
    assert estimate.confidence == 0.50


def test_estimate_by_type_industrial_uses_rate_confidence():
    service = CarbonEstimatorService(AsyncMock())

    estimate = service._estimate_by_type(
        "industrial",
        {"count": 1, "total_rate_kg_hr": 200.0, "total_carbon_ton_yr": None},
    )

    assert estimate.confidence == 0.70
    assert estimate.co2_kg_per_day > 0
