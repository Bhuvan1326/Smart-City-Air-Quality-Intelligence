import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.models.civic_issue import CivicIssueSeverity, CivicIssueType
from app.services.civic_photo_classifier import classify_photo


class FakeAnthropicResponse:
    def __init__(self, text: str):
        self.content = [MagicMock(type="text", text=text)]


@pytest.fixture(autouse=True)
def _ensure_api_key_configured():
    original = settings.ANTHROPIC_API_KEY
    settings.ANTHROPIC_API_KEY = "test-key"
    yield
    settings.ANTHROPIC_API_KEY = original


@pytest.mark.asyncio
async def test_no_api_key_returns_none_not_fabricated():
    settings.ANTHROPIC_API_KEY = ""
    result = await classify_photo(image_base64="Zm9v", media_type="image/jpeg")
    assert result is None


@pytest.mark.asyncio
async def test_successful_classification_parses_response():
    payload = {
        "issue_type": "pothole",
        "confidence": 0.87,
        "severity": "high",
        "reasoning": "Deep pothole visible on a paved road.",
    }
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=FakeAnthropicResponse(json.dumps(payload))
    )

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await classify_photo(image_base64="Zm9v", media_type="image/jpeg")

    assert result is not None
    assert result.issue_type == CivicIssueType.POTHOLE
    assert result.suggested_severity == CivicIssueSeverity.HIGH
    assert result.confidence == 0.87
    assert "pothole" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_confidence_clamped_to_valid_range():
    payload = {
        "issue_type": "garbage",
        "confidence": 1.5,  # out of range
        "severity": "low",
        "reasoning": "Trash pile.",
    }
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=FakeAnthropicResponse(json.dumps(payload))
    )

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await classify_photo(image_base64="Zm9v", media_type="image/jpeg")

    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_unparseable_response_returns_none_not_fabricated():
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=FakeAnthropicResponse("not valid json at all")
    )

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await classify_photo(image_base64="Zm9v", media_type="image/jpeg")

    assert result is None


@pytest.mark.asyncio
async def test_invalid_issue_type_in_response_returns_none():
    payload = {
        "issue_type": "not_a_real_type",
        "confidence": 0.9,
        "severity": "low",
        "reasoning": "x",
    }
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=FakeAnthropicResponse(json.dumps(payload))
    )

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await classify_photo(image_base64="Zm9v", media_type="image/jpeg")

    assert result is None


@pytest.mark.asyncio
async def test_api_failure_returns_none_never_raises():
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("network down"))

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await classify_photo(image_base64="Zm9v", media_type="image/jpeg")

    assert result is None
