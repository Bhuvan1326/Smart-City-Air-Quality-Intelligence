from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors as genai_errors

from app.services.llm_provider import (
    GeminiProvider,
    LLMAuthenticationError,
    LLMEmptyResponseError,
    LLMMessage,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)


def make_client_error(code: int) -> genai_errors.ClientError:
    return genai_errors.ClientError(
        code=code, response_json={"error": {"message": "boom"}}
    )


@pytest.fixture
def provider():
    with patch("app.services.llm_provider.genai.Client"):
        yield GeminiProvider(api_key="test-key", model="gemini-2.5-flash")


@pytest.mark.asyncio
async def test_generate_success_returns_text(provider):
    fake_response = MagicMock()
    fake_response.text = "The AQI is currently moderate."
    provider._client.aio.models.generate_content = AsyncMock(return_value=fake_response)

    result = await provider.generate(
        system_instruction="You are an assistant.",
        messages=[LLMMessage(role="user", content="how's the air?")],
    )

    assert result == "The AQI is currently moderate."


@pytest.mark.asyncio
async def test_generate_raises_empty_response_error_on_blank_text(provider):
    fake_response = MagicMock()
    fake_response.text = ""
    provider._client.aio.models.generate_content = AsyncMock(return_value=fake_response)

    with pytest.raises(LLMEmptyResponseError):
        await provider.generate(
            system_instruction="sys", messages=[LLMMessage(role="user", content="hi")]
        )


@pytest.mark.asyncio
async def test_generate_raises_empty_response_error_on_none_response(provider):
    provider._client.aio.models.generate_content = AsyncMock(return_value=None)

    with pytest.raises(LLMEmptyResponseError):
        await provider.generate(
            system_instruction="sys", messages=[LLMMessage(role="user", content="hi")]
        )


@pytest.mark.asyncio
async def test_generate_raises_timeout_error(provider):
    provider._client.aio.models.generate_content = AsyncMock(
        side_effect=TimeoutError("deadline exceeded")
    )

    with pytest.raises(LLMTimeoutError):
        await provider.generate(
            system_instruction="sys", messages=[LLMMessage(role="user", content="hi")]
        )


@pytest.mark.asyncio
async def test_generate_raises_rate_limit_error_on_429(provider):
    provider._client.aio.models.generate_content = AsyncMock(
        side_effect=make_client_error(429)
    )

    with pytest.raises(LLMRateLimitError):
        await provider.generate(
            system_instruction="sys", messages=[LLMMessage(role="user", content="hi")]
        )


@pytest.mark.asyncio
async def test_generate_raises_authentication_error_on_401(provider):
    provider._client.aio.models.generate_content = AsyncMock(
        side_effect=make_client_error(401)
    )

    with pytest.raises(LLMAuthenticationError):
        await provider.generate(
            system_instruction="sys", messages=[LLMMessage(role="user", content="hi")]
        )


@pytest.mark.asyncio
async def test_generate_raises_provider_error_on_server_error(provider):
    server_error = genai_errors.ServerError(
        code=500, response_json={"error": {"message": "internal error"}}
    )
    provider._client.aio.models.generate_content = AsyncMock(side_effect=server_error)

    with pytest.raises(LLMProviderError):
        await provider.generate(
            system_instruction="sys", messages=[LLMMessage(role="user", content="hi")]
        )
