from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.assistant_agent import AssistantAgent
from app.services.llm_provider import (
    LLMEmptyResponseError,
    LLMRateLimitError,
    LLMTimeoutError,
)


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


class FakeGeminiResponse:
    def __init__(self, text):
        self.text = text


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

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(
        return_value="Air quality is currently moderate."
    )

    with patch("app.agents.assistant_agent.GeminiProvider", return_value=mock_provider):
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
async def test_respond_raises_runtime_error_on_empty_provider_response():
    """An empty/whitespace text response from the provider must surface as
    a handled RuntimeError, not crash with an IndexError/AttributeError.
    """
    session = AsyncMock()
    session.execute = AsyncMock(return_value=make_row_result([]))
    agent = AssistantAgent(session, "Pune")

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(
        side_effect=LLMEmptyResponseError("Gemini returned an empty response.")
    )

    with patch("app.agents.assistant_agent.GeminiProvider", return_value=mock_provider):
        with pytest.raises(RuntimeError):
            await agent.respond(message="status", history=[], user_role="citizen")


@pytest.mark.asyncio
async def test_respond_raises_timeout_error_on_provider_timeout():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=make_row_result([]))
    agent = AssistantAgent(session, "Pune")

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(side_effect=LLMTimeoutError("timed out"))

    with patch("app.agents.assistant_agent.GeminiProvider", return_value=mock_provider):
        with pytest.raises(TimeoutError):
            await agent.respond(message="status", history=[], user_role="citizen")


@pytest.mark.asyncio
async def test_respond_raises_runtime_error_on_rate_limit():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=make_row_result([]))
    agent = AssistantAgent(session, "Pune")

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(side_effect=LLMRateLimitError("rate limited"))

    with patch("app.agents.assistant_agent.GeminiProvider", return_value=mock_provider):
        with pytest.raises(RuntimeError):
            await agent.respond(message="status", history=[], user_role="citizen")


@pytest.mark.asyncio
async def test_respond_no_map_data_when_no_current_aqi():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=make_row_result([]))
    agent = AssistantAgent(session, "Pune")

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value="No data currently available.")

    with patch("app.agents.assistant_agent.GeminiProvider", return_value=mock_provider):
        response = await agent.respond(
            message="status", history=[], user_role="citizen"
        )

    assert response.map_data is None
    assert response.supporting_evidence == []
