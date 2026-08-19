from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.langgraph_agents import (
    AgentOutput,
    AirQualityOrchestrator,
    AttributionAgent,
    BaseAgent,
    CitizenAdvisoryAgent,
    DataIngestionAgent,
    EnforcementAgent,
    ForecastAgent,
    PolicyAnalyticsAgent,
)


def rows_result(rows):
    result = MagicMock()
    result.__iter__.return_value = iter(rows)
    return result


def row(**kwargs):
    r = MagicMock()
    r._mapping = kwargs
    return r


def base_state(**overrides):
    state = {
        "city": "Pune",
        "ward_id": None,
        "query": "",
        "user_role": "city_administrator",
        "session_id": "sid-1",
        "ingestion_result": None,
        "forecast_result": None,
        "attribution_result": None,
        "enforcement_result": None,
        "advisory_result": None,
        "policy_result": None,
        "confidence_scores": {},
        "reasoning_traces": {},
        "supporting_evidence": [],
        "data_sources": [],
        "errors": [],
    }
    state.update(overrides)
    return state


# ─── BaseAgent ──────────────────────────────────────────────────────────────


class _AlwaysSucceeds(BaseAgent):
    name = "always_succeeds"

    async def execute(self, state):
        return AgentOutput(
            agent_name=self.name,
            success=True,
            data={"ok": True},
            confidence_score=0.9,
            reasoning_trace="fine",
            supporting_evidence=[],
            data_sources=[],
        )


class _FailsThenSucceeds(BaseAgent):
    name = "fails_then_succeeds"
    calls = 0

    async def execute(self, state):
        _FailsThenSucceeds.calls += 1
        if _FailsThenSucceeds.calls < 2:
            raise RuntimeError("transient error")
        return AgentOutput(
            agent_name=self.name,
            success=True,
            data={},
            confidence_score=0.5,
            reasoning_trace="recovered",
            supporting_evidence=[],
            data_sources=[],
        )


class _AlwaysFails(BaseAgent):
    name = "always_fails"
    max_retries = 2

    async def execute(self, state):
        raise ValueError("boom")


@pytest.mark.asyncio
async def test_run_with_retry_success_first_try():
    agent = _AlwaysSucceeds(AsyncMock())

    output = await agent.run_with_retry(base_state())

    assert output.success is True
    assert output.execution_time_ms >= 0


@pytest.mark.asyncio
async def test_run_with_retry_eventual_success():
    _FailsThenSucceeds.calls = 0
    agent = _FailsThenSucceeds(AsyncMock())

    with patch("asyncio.sleep", new=AsyncMock()):
        output = await agent.run_with_retry(base_state())

    assert output.success is True
    assert output.reasoning_trace == "recovered"


@pytest.mark.asyncio
async def test_run_with_retry_all_attempts_fail():
    agent = _AlwaysFails(AsyncMock())

    with patch("asyncio.sleep", new=AsyncMock()):
        output = await agent.run_with_retry(base_state())

    assert output.success is False
    assert output.confidence_score == 0.0
    assert "boom" in output.error


# ─── DataIngestionAgent ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_data_ingestion_no_readings():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=rows_result([]))
    agent = DataIngestionAgent(session)

    output = await agent.execute(base_state())

    assert output.confidence_score == 0.3
    assert output.data["readings"] == []


@pytest.mark.asyncio
async def test_data_ingestion_with_readings_imputes_and_flags_maintenance():
    readings = [
        row(
            station_code="PUNE_001",
            name="Station A",
            ward_id="W01",
            aqi=150,
            pm25=80,
            pm10=100,
            no2=20,
            co=1.0,
            o3=30,
            temperature=25,
            humidity=50,
            wind_speed=2.0,
            wind_direction=180,
            quality_flag="good",
            timestamp=datetime.now(UTC),
            maintenance_score=0.5,
        ),
        row(
            station_code="PUNE_002",
            name="Station B",
            ward_id="W02",
            aqi=None,
            pm25=None,
            pm10=None,
            no2=None,
            co=None,
            o3=None,
            temperature=None,
            humidity=None,
            wind_speed=None,
            wind_direction=None,
            quality_flag="suspect",
            timestamp=datetime.now(UTC),
            maintenance_score=1.0,
        ),
    ]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=rows_result(readings))
    agent = DataIngestionAgent(session)

    with patch.object(agent, "_fetch_weather", new=AsyncMock(return_value={})):
        output = await agent.execute(base_state())

    assert output.data["quality_summary"]["total"] == 2
    assert output.data["quality_summary"]["good"] == 1
    assert output.data["quality_summary"]["missing"] == 1
    assert len(output.data["maintenance_alerts"]) == 1
    imputed = [r for r in output.data["readings"] if r.get("imputed")]
    assert len(imputed) == 1


@pytest.mark.asyncio
async def test_fetch_weather_success():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "current": {
            "temperature_2m": 26.0,
            "relative_humidity_2m": 55.0,
            "wind_speed_10m": 3.0,
            "wind_direction_10m": 200.0,
            "precipitation": 0.0,
        }
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=resp)
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    agent = DataIngestionAgent(AsyncMock())
    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        weather = await agent._fetch_weather("Pune")

    assert weather["source"] == "Open-Meteo"
    assert weather["temperature"] == 26.0


@pytest.mark.asyncio
async def test_fetch_weather_non_200_returns_empty():
    resp = MagicMock(status_code=500)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=resp)
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False

    agent = DataIngestionAgent(AsyncMock())
    with patch("httpx.AsyncClient", return_value=mock_client_cm):
        weather = await agent._fetch_weather("Delhi")

    assert weather == {}


@pytest.mark.asyncio
async def test_fetch_weather_handles_exception():
    agent = DataIngestionAgent(AsyncMock())
    with patch("httpx.AsyncClient", side_effect=Exception("network down")):
        weather = await agent._fetch_weather("Unknown City")

    assert weather == {}


# ─── ForecastAgent ────────────────────────────────────────────────────────────


def test_load_model_no_files_returns_none():
    agent = ForecastAgent(AsyncMock())
    with patch("glob.glob", return_value=[]):
        assert agent._load_model() is None


def test_load_model_loads_latest_file():
    agent = ForecastAgent(AsyncMock())
    with patch("glob.glob", return_value=["xgb_forecast_1.joblib"]), patch(
        "joblib.load", return_value=MagicMock()
    ):
        assert agent._load_model() is not None


def test_load_model_handles_load_exception():
    agent = ForecastAgent(AsyncMock())
    with patch("glob.glob", return_value=["xgb_forecast_1.joblib"]), patch(
        "joblib.load", side_effect=Exception("corrupt")
    ):
        assert agent._load_model() is None


def test_compute_dispersion_missing_wind_data():
    agent = ForecastAgent(AsyncMock())

    result = agent._compute_dispersion("W01", {}, {})

    assert result["available"] is False


def test_compute_dispersion_with_wind_data():
    agent = ForecastAgent(AsyncMock())
    ward_data = {"W01": {"avg_aqi": 120.0}, "W02": {"avg_aqi": 90.0}}
    weather = {"wind_speed": 4.0, "wind_direction": 220.0}

    result = agent._compute_dispersion("W01", ward_data, weather)

    assert result["available"] is True
    assert result["ward_id"] == "W01"
    assert "upwind_wards" in result


@pytest.mark.asyncio
async def test_forecast_agent_execute_full_flow():
    ward_rows = rows_result(
        [
            row(
                ward_id="W01",
                avg_aqi=120.0,
                avg_pm25=70.0,
                avg_temp=26.0,
                avg_humidity=50.0,
                avg_wind=3.0,
            )
        ]
    )
    forecast_rows = rows_result(
        [
            row(
                ward_id="W01",
                aqi_forecast=180,
                pm25_forecast=90.0,
                confidence_score=0.7,
                confidence_lower=150,
                confidence_upper=210,
                forecast_timestamp=datetime.now(UTC),
                contributing_factors={},
                feature_importance={},
            )
        ]
    )
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[ward_rows, forecast_rows])
    agent = ForecastAgent(session)

    state = base_state(
        ingestion_result={
            "data": {"weather": {"wind_speed": 3.0, "wind_direction": 200.0}}
        }
    )

    with patch.object(agent, "_load_model", return_value=None):
        output = await agent.execute(state)

    assert output.data["peak_aqi"] == 180
    assert output.data["peak_ward"] == "W01"
    assert output.data["model_version"] == "statistical-v1.0"


@pytest.mark.asyncio
async def test_forecast_agent_execute_ward_scoped_and_no_forecasts():
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[rows_result([]), rows_result([])])
    agent = ForecastAgent(session)

    state = base_state(ward_id="W02", ingestion_result=None)

    with patch.object(agent, "_load_model", return_value=object()):
        output = await agent.execute(state)

    assert output.data["peak_aqi"] == 0
    assert output.data["peak_ward"] is None
    assert output.data["model_version"] == "xgb-v1.0"


# ─── AttributionAgent ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_attribution_agent_no_attributions():
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[rows_result([]), rows_result([])])
    agent = AttributionAgent(session)

    output = await agent.execute(base_state())

    assert output.confidence_score == 0.4
    assert output.data["top_source"] == "unknown"


@pytest.mark.asyncio
async def test_attribution_agent_with_hotspots():
    attributions = rows_result(
        [
            row(
                ward_id="W03",
                vehicular_pct=20.0,
                industrial_pct=50.0,
                construction_pct=15.0,
                biomass_pct=5.0,
                dust_pct=5.0,
                domestic_pct=5.0,
                overall_confidence=0.8,
                contributing_sources={},
                satellite_evidence={},
                timestamp=datetime.now(UTC),
            )
        ]
    )
    sources = rows_result(
        [
            row(
                name="Factory X",
                source_type="industrial",
                ward_id="W03",
                violation_count=5,
                permit_status="expired",
                last_inspected_at=None,
                emission_rate_kg_hr=100.0,
                carbon_estimate_ton_yr=200.0,
                latitude=18.5,
                longitude=73.9,
            )
        ]
    )
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[attributions, sources])
    agent = AttributionAgent(session)

    output = await agent.execute(base_state(city="Pune", ward_id="W03"))

    assert output.data["top_source"] == "industrial"
    assert len(output.data["hotspots"]) == 1


# ─── EnforcementAgent ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enforcement_agent_get_anomalies():
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=rows_result(
            [
                row(
                    ward_id="W01",
                    aqi_spike_value=280,
                    probable_cause="Industrial",
                    confidence_score=0.7,
                    detected_at=datetime.now(UTC),
                )
            ]
        )
    )
    agent = EnforcementAgent(session)

    anomalies = await agent._get_anomalies("Pune")

    assert len(anomalies) == 1
    assert anomalies[0]["ward_id"] == "W01"


@pytest.mark.asyncio
async def test_enforcement_agent_execute_with_hotspots_and_pending():
    pending = rows_result(
        [
            row(
                id="a1",
                title="Existing action",
                ward_id="W01",
                action_type="notice",
                status="pending",
                priority_score=70.0,
                created_at=datetime.now(UTC),
                ai_reasoning={},
                source_name="Src",
                source_type="industrial",
                violation_count=2,
            )
        ]
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=pending)
    agent = EnforcementAgent(session)

    state = base_state(
        attribution_result={
            "data": {
                "hotspots": [
                    {
                        "name": "Factory X",
                        "ward_id": "W03",
                        "source_type": "industrial",
                        "violation_count": 6,
                        "permit_status": "expired",
                        "latitude": 18.5,
                        "longitude": 73.9,
                    }
                ]
            }
        }
    )

    with patch.object(agent, "_get_anomalies", new=AsyncMock(return_value=[])):
        output = await agent.execute(state)

    assert output.data["total_pending"] == 1
    assert len(output.data["new_recommendations"]) == 1
    assert output.data["new_recommendations"][0]["recommended_action"] == "shutdown"
    assert output.confidence_score == 0.82


@pytest.mark.asyncio
async def test_enforcement_agent_execute_no_hotspots():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=rows_result([]))
    agent = EnforcementAgent(session)

    with patch.object(agent, "_get_anomalies", new=AsyncMock(return_value=[])):
        output = await agent.execute(base_state())

    assert output.confidence_score == 0.65
    assert output.data["new_recommendations"] == []


# ─── CitizenAdvisoryAgent ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_citizen_advisory_hours_ahead_filters_and_generates_messages():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=rows_result([]))
    agent = CitizenAdvisoryAgent(session)

    state = base_state(
        forecast_result={
            "data": {
                "peak_aqi": 250,
                "peak_ward": "W02",
                "forecasts": [
                    {"ward_id": "W02", "aqi_forecast": 250, "hours_ahead": 6},
                    {"ward_id": "W05", "aqi_forecast": 320, "hours_ahead": 20},
                    {"ward_id": "W01", "aqi_forecast": 100, "hours_ahead": 2},
                ],
            }
        }
    )

    output = await agent.execute(state)

    assert "W02" in output.data["alert_wards"]
    assert "W05" not in output.data["alert_wards"]
    assert output.data["new_alerts_needed"] == 1
    assert len(output.data["advisory_messages"]) == 3


@pytest.mark.asyncio
async def test_citizen_advisory_forecast_timestamp_fallback():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=rows_result([]))
    agent = CitizenAdvisoryAgent(session)

    near_future = datetime.now(UTC).isoformat()
    state = base_state(
        forecast_result={
            "data": {
                "peak_aqi": 210,
                "peak_ward": "W04",
                "forecasts": [
                    {
                        "ward_id": "W04",
                        "aqi_forecast": 210,
                        "forecast_timestamp": near_future,
                    },
                    {"ward_id": "W06", "aqi_forecast": 160},
                ],
            }
        }
    )

    output = await agent.execute(state)

    assert "W04" in output.data["alert_wards"]


@pytest.mark.asyncio
async def test_citizen_advisory_filters_already_alerted_wards():
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=rows_result(
            [
                row(
                    ward_id="W02",
                    risk_level="high",
                    language="en",
                    sent_at=datetime.now(UTC),
                    aqi_value=200,
                )
            ]
        )
    )
    agent = CitizenAdvisoryAgent(session)

    state = base_state(
        forecast_result={
            "data": {
                "forecasts": [
                    {"ward_id": "W02", "aqi_forecast": 250, "hours_ahead": 3},
                ]
            }
        }
    )

    output = await agent.execute(state)

    assert output.data["new_alerts_needed"] == 0


def test_get_action_known_and_default():
    agent = CitizenAdvisoryAgent(AsyncMock())

    assert "N95" in agent._get_action("high")
    assert "indoors" in agent._get_action("very_high")
    assert "Emergency" in agent._get_action("severe")
    assert agent._get_action("moderate") == "Monitor air quality alerts."


# ─── PolicyAnalyticsAgent ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_policy_analytics_with_comparable_policy():
    outcomes = rows_result(
        [
            row(
                aqi_before=150.0,
                aqi_after=100.0,
                delta_score=-50.0,
                carbon_saved_kg=1200.0,
                measurement_period_hours=48,
                confidence_score=0.8,
                action_type="shutdown",
                ward_id="W03",
                city="Pune",
            )
        ]
    )
    policies = rows_result(
        [
            row(
                city="Delhi",
                policy_type="odd_even",
                impact_score=72.0,
                aqi_delta=-20.0,
                pm25_delta=-10.0,
                implemented_at=datetime.now(UTC),
                comparable_city_ref="Pune",
                measurement_days=30,
            )
        ]
    )
    city_comparison = rows_result([row(city="Pune", avg_aqi=110.0, max_aqi=200.0)])
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[outcomes, policies, city_comparison])
    agent = PolicyAnalyticsAgent(session)

    output = await agent.execute(base_state())

    assert output.data["best_comparable_policy"]["policy_type"] == "odd_even"
    assert output.confidence_score == 0.75
    assert len(output.data["recommendations"]) == 1


@pytest.mark.asyncio
async def test_policy_analytics_no_comparable_policy():
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[rows_result([]), rows_result([]), rows_result([])]
    )
    agent = PolicyAnalyticsAgent(session)

    output = await agent.execute(base_state())

    assert output.data["best_comparable_policy"] is None
    assert output.confidence_score == 0.50
    assert output.data["recommendations"] == []


# ─── AirQualityOrchestrator ──────────────────────────────────────────────────


def _canned_output(name, confidence=0.7, error=None):
    return AgentOutput(
        agent_name=name,
        success=error is None,
        data={"name": name},
        confidence_score=confidence,
        reasoning_trace=f"{name} ran",
        supporting_evidence=[{"type": name}],
        data_sources=[f"{name}_source"],
        error=error,
    )


@pytest.mark.asyncio
async def test_orchestrator_runs_full_pipeline():
    session = AsyncMock()
    orchestrator = AirQualityOrchestrator(session)

    patches = [
        patch.object(
            DataIngestionAgent,
            "run_with_retry",
            new=AsyncMock(return_value=_canned_output("ingestion")),
        ),
        patch.object(
            ForecastAgent,
            "run_with_retry",
            new=AsyncMock(return_value=_canned_output("forecast")),
        ),
        patch.object(
            AttributionAgent,
            "run_with_retry",
            new=AsyncMock(return_value=_canned_output("attribution")),
        ),
        patch.object(
            EnforcementAgent,
            "run_with_retry",
            new=AsyncMock(return_value=_canned_output("enforcement")),
        ),
        patch.object(
            CitizenAdvisoryAgent,
            "run_with_retry",
            new=AsyncMock(return_value=_canned_output("advisory")),
        ),
        patch.object(
            PolicyAnalyticsAgent,
            "run_with_retry",
            new=AsyncMock(return_value=_canned_output("policy", confidence=0.6)),
        ),
    ]
    for p in patches:
        p.start()
    try:
        result = await orchestrator.run(city="Pune", query="status?")
    finally:
        for p in patches:
            p.stop()

    assert result["city"] == "Pune"
    assert set(result["confidence_scores"].keys()) == {
        "ingestion",
        "forecast",
        "attribution",
        "enforcement",
        "advisory",
        "policy",
    }
    assert result["overall_confidence"] > 0
    assert result["errors"] == []
    assert result["ingestion"]["success"] is True


@pytest.mark.asyncio
async def test_orchestrator_partial_pipeline_and_errors():
    session = AsyncMock()
    orchestrator = AirQualityOrchestrator(session)

    with patch.object(
        DataIngestionAgent,
        "run_with_retry",
        new=AsyncMock(return_value=_canned_output("ingestion", error="db down")),
    ):
        result = await orchestrator.run(city="Mumbai", agents_to_run=["ingestion"])

    assert result["agents_executed"] == ["ingestion"]
    assert result["forecast"] is None
    assert "ingestion: db down" in result["errors"]
    assert result["overall_confidence"] == 0.7
