import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.models.civic_issue import AIVerificationResult
from app.services.civic_resolution_verification import verify_resolution


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
async def test_no_before_photo_returns_none():
    result = await verify_resolution(
        before_photo_url=None,
        after_photo_data_url="data:image/jpeg;base64,Zm9v",
    )
    assert result is None


@pytest.mark.asyncio
async def test_no_api_key_returns_none():
    settings.ANTHROPIC_API_KEY = ""
    result = await verify_resolution(
        before_photo_url="/media/evidence/x/y.jpg",
        after_photo_data_url="data:image/jpeg;base64,Zm9v",
    )
    assert result is None


@pytest.mark.asyncio
async def test_unreadable_before_photo_returns_none():
    with patch(
        "app.services.evidence_storage.EvidenceStorage.read_photo", return_value=None
    ):
        result = await verify_resolution(
            before_photo_url="/media/evidence/missing/y.jpg",
            after_photo_data_url="data:image/jpeg;base64,Zm9v",
        )
    assert result is None


@pytest.mark.asyncio
async def test_successful_verification_parses_response():
    payload = {
        "result": "likely_resolved",
        "confidence": 0.8,
        "reasoning": "Pothole is filled in the after photo.",
    }
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=FakeAnthropicResponse(json.dumps(payload))
    )

    with (
        patch(
            "app.services.evidence_storage.EvidenceStorage.read_photo",
            return_value=(b"fakebytes", "image/jpeg"),
        ),
        patch("anthropic.AsyncAnthropic", return_value=mock_client),
    ):
        result = await verify_resolution(
            before_photo_url="/media/evidence/x/y.jpg",
            after_photo_data_url="data:image/jpeg;base64,Zm9v",
        )

    assert result is not None
    assert result.result == AIVerificationResult.LIKELY_RESOLVED
    assert result.confidence == 0.8


@pytest.mark.asyncio
async def test_malformed_after_photo_url_returns_none():
    result = await verify_resolution(
        before_photo_url="/media/evidence/x/y.jpg",
        after_photo_data_url="not-a-data-url",
    )
    assert result is None


@pytest.mark.asyncio
async def test_api_failure_returns_none_never_raises():
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("network down"))

    with (
        patch(
            "app.services.evidence_storage.EvidenceStorage.read_photo",
            return_value=(b"fakebytes", "image/jpeg"),
        ),
        patch("anthropic.AsyncAnthropic", return_value=mock_client),
    ):
        result = await verify_resolution(
            before_photo_url="/media/evidence/x/y.jpg",
            after_photo_data_url="data:image/jpeg;base64,Zm9v",
        )
    assert result is None
