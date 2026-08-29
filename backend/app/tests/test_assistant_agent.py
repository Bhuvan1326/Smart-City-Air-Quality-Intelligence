from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.agents.assistant_agent import AssistantAgent


def make_row_result(rows):
    result = MagicMock()
    result.__iter__.return_value = iter(rows)
    return result


def fake_row(**kwargs):
    row = MagicMock()
    row._mapping = kwargs
    return row


@pytest.mark.asyncio
async def test_fetch_context_always_includes_current_aqi():
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=make_row_result(
            [fake_row(ward_id="W01", station_name="Station A", aqi=120)]
        )
    )
    agent = AssistantAgent(session, "Pune")

    context = await agent._fetch_context("what's the general status")

    assert "current_aqi" in context
    assert context["current_aqi"][0]["ward_id"] == "W01"
    assert "attributions" not in context


@pytest.mark.asyncio
async def test_fetch_context_includes_attributions_for_source_keywords():
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            make_row_result([]),
            make_row_result([fake_row(ward_id="W03", vehicular_pct=40.0)]),
        ]
    )
    agent = AssistantAgent(session, "Pune")

    context = await agent._fetch_context("what is the source of pollution here")

    assert "attributions" in context
    assert context["attributions"][0]["ward_id"] == "W03"


@pytest.mark.asyncio
async def test_fetch_context_includes_forecast_for_forecast_keywords():
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            make_row_result([]),
            make_row_result([fake_row(ward_id="W01", aqi_forecast=140)]),
        ]
    )
    agent = AssistantAgent(session, "Pune")

    context = await agent._fetch_context("what will tomorrow's aqi be")

    assert "forecasts" in context


@pytest.mark.asyncio
async def test_fetch_context_includes_enforcement_for_enforcement_keywords():
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            make_row_result([]),
            make_row_result([fake_row(title="Inspection", ward_id="W01")]),
        ]
    )
    agent = AssistantAgent(session, "Pune")

    context = await agent._fetch_context("any recent enforcement action taken")

    assert "enforcement" in context


@pytest.mark.asyncio
async def test_fetch_context_includes_anomalies_for_spike_keywords():
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            make_row_result([]),
            make_row_result([fake_row(ward_id="W01", aqi_spike_value=200)]),
        ]
    )
    agent = AssistantAgent(session, "Pune")

    context = await agent._fetch_context("was there a sudden spike alert")

    assert "anomalies" in context


@pytest.mark.asyncio
async def test_fetch_context_multiple_keyword_categories():
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            make_row_result([]),
            make_row_result([]),
            make_row_result([]),
            make_row_result([]),
        ]
    )
    agent = AssistantAgent(session, "Pune")

    context = await agent._fetch_context("why is there an anomaly and forecast issue")

    assert "anomalies" in context
    assert "forecasts" in context


class FakeAnthropicResponse:
    def __init__(self, text):
        self.content = [MagicMock(text=text)]


@pytest.mark.asyncio
async def test_respond_builds_chat_response_with_map_data():
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=make_row_result(
            [
                fake_row(
                    ward_id="W01",
                    station_name="Station A",
                    aqi=110,
                    pm25=60,
                    pm10=90,
                    no2=20,
                    timestamp="2026-01-01T08:00:00",
                    wind_speed=2.0,
                    wind_direction=180.0,
                )
            ]
        )
    )
    agent = AssistantAgent(session, "Pune")

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=FakeAnthropicResponse("Air quality is currently moderate.")
    )

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        response = await agent.respond(
            message="how is the air quality",
            history=[("user", "hello"), ("assistant", "hi there")],
            user_role="city_administrator",
        )

    assert response.answer == "Air quality is currently moderate."
    assert response.map_data["type"] == "aqi_heatmap"
    assert response.map_data["points"][0]["ward_id"] == "W01"
    assert "CAAQMS stations" in response.data_sources
    assert 0 <= response.confidence_score <= 0.95
    assert len(response.supporting_evidence) == 1


@pytest.mark.asyncio
async def test_respond_no_map_data_when_no_current_aqi():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=make_row_result([]))
    agent = AssistantAgent(session, "Pune")

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=FakeAnthropicResponse("No data currently available.")
    )

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        response = await agent.respond(
            message="status", history=[], user_role="citizen"
        )

    assert response.map_data is None
    assert response.supporting_evidence == []
