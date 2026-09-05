"""
Gemini LLM provider abstraction.

Centralizes all Google Gemini-specific client/error-handling logic behind a
small, provider-agnostic interface so that callers (currently
app.agents.assistant_agent.AssistantAgent) never talk to the google-genai
SDK directly and never branch on `if provider == "gemini"`. If another LLM
provider is ever added, it would implement the same generate() contract and
be swapped in here — the rest of the application wouldn't need to change.

Uses the official Google GenAI SDK (`google-genai` package, `genai.Client`).
"""

from __future__ import annotations

from dataclasses import dataclass

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.core.config import settings

# The SDK default timeout can run to minutes, which is far too slow for an
# interactive chat request. Fail fast and let the caller return a clear,
# actionable error rather than hang the connection.
DEFAULT_TIMEOUT_SECONDS = 25.0


class LLMProviderError(Exception):
    """Base class for all Gemini provider failures."""


class LLMTimeoutError(LLMProviderError):
    """The request to Gemini took too long."""


class LLMRateLimitError(LLMProviderError):
    """Gemini returned a rate-limit (429) response."""


class LLMAuthenticationError(LLMProviderError):
    """Gemini rejected the configured API key."""


class LLMConnectionError(LLMProviderError):
    """Couldn't reach the Gemini API."""


class LLMEmptyResponseError(LLMProviderError):
    """Gemini returned a response with no usable text content."""


@dataclass
class LLMMessage:
    role: str  # "user" | "assistant" (mapped to Gemini's "model" internally)
    content: str


class GeminiProvider:
    """Thin async wrapper around genai.Client for text generation."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self._client = genai.Client(
            api_key=self.api_key,
            http_options=genai_types.HttpOptions(
                timeout=int(timeout_seconds * 1000)  # SDK expects milliseconds
            ),
        )

    async def generate(
        self,
        system_instruction: str,
        messages: list[LLMMessage],
        max_output_tokens: int = 1500,
        temperature: float | None = None,
    ) -> str:
        """Send a chat-style request to Gemini and return the response text.

        Raises one of the LLMProviderError subclasses above on any failure
        — callers should never need to import google.genai themselves.
        """
        contents = [
            genai_types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[genai_types.Part.from_text(text=m.content)],
            )
            for m in messages
        ]

        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        except TimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except genai_errors.ClientError as e:
            if e.code == 429:
                raise LLMRateLimitError(str(e)) from e
            if e.code in (401, 403):
                raise LLMAuthenticationError(str(e)) from e
            raise LLMProviderError(str(e)) from e
        except genai_errors.ServerError as e:
            raise LLMProviderError(str(e)) from e
        except genai_errors.APIError as e:
            raise LLMProviderError(str(e)) from e
        except OSError as e:
            # Covers httpx connection failures (DNS, refused connection,
            # etc.) that don't surface as a genai_errors.APIError.
            raise LLMConnectionError(str(e)) from e

        text = response.text if response is not None else None
        if not text:
            raise LLMEmptyResponseError("Gemini returned an empty response.")
        return text
