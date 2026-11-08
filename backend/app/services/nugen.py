from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import logger

DEFAULT_TIMEOUT_SECONDS = 30.0
_MAX_RETRIES = 2


class NugenError(Exception):
    """Base class for all Nugen API failures."""


class NugenNotConfiguredError(NugenError):
    """NUGEN_API_KEY (or the aligned model id) is not configured."""


class NugenAuthenticationError(NugenError):
    """Nugen rejected the configured API key (401/403)."""


class NugenRateLimitError(NugenError):
    """Nugen returned a rate-limit (429) response."""


class NugenTimeoutError(NugenError):
    """The request to Nugen timed out."""


class NugenConnectionError(NugenError):
    """Couldn't reach the Nugen API."""


class NugenEmptyResponseError(NugenError):
    """Nugen returned a response with no usable message content."""


class NugenInvalidResponseError(NugenError):
    """Nugen returned a response that didn't match the documented schema."""


@dataclass
class NugenChatResult:
    """Validated subset of the chat-completion response we expose to callers."""

    content: str
    model: str
    confidence_score: float | None
    prompt_tokens: int | None
    completion_tokens: int | None


class NugenClient:
    """Async HTTP client for the Nugen v3 API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.NUGEN_API_KEY
        self.base_url = (base_url or settings.NUGEN_BASE_URL).rstrip("/")
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.NUGEN_TIMEOUT_SECONDS or DEFAULT_TIMEOUT_SECONDS
        )
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        files: list[tuple] | None = None,
        data: dict | None = None,
    ) -> dict:
        """Issue one request with limited retries on transient failures.

        4xx responses are never retried; 429/5xx and connection/timeouts are
        retried up to ``_MAX_RETRIES`` times. Never logs request bodies.
        """
        if not self.configured:
            raise NugenNotConfiguredError("NUGEN_API_KEY is not configured")

        last_error: NugenError | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = await self._client.request(
                    method,
                    path,
                    json=json,
                    files=files,
                    data=data,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except httpx.TimeoutException as e:
                last_error = NugenTimeoutError(str(e))
                continue
            except httpx.HTTPError as e:
                last_error = NugenConnectionError(str(e))
                continue
            except OSError as e:
                last_error = NugenConnectionError(str(e))
                continue

            if resp.status_code in (401, 403):
                raise NugenAuthenticationError(
                    f"Nugen rejected the API key (HTTP {resp.status_code})"
                )
            if resp.status_code == 429:
                last_error = NugenRateLimitError("Nugen rate limit (HTTP 429)")
                continue
            if resp.status_code >= 500:
                last_error = NugenError(
                    f"Nugen service error (HTTP {resp.status_code})"
                )
                continue
            if resp.status_code >= 400:
                # Client error — surface the detail but never the key.
                raise NugenError(
                    f"Nugen request failed (HTTP {resp.status_code}): "
                    f"{resp.text[:300]}"
                )

            try:
                return resp.json()
            except ValueError as e:
                raise NugenInvalidResponseError(
                    "Nugen returned non-JSON response"
                ) from e

        logger.warning(
            "nugen.request_failed",
            method=method,
            path=path,
            error=str(last_error),
        )
        assert last_error is not None
        raise last_error

    # ── Inference ──────────────────────────────────────────────────────────

    async def chat_completion(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.4,
    ) -> NugenChatResult:
        """Run one non-streaming chat completion against the aligned model."""
        model_id = model or settings.NUGEN_ALIGNED_MODEL_ID
        if not model_id:
            raise NugenNotConfiguredError("NUGEN_ALIGNED_MODEL_ID is not configured")

        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        data = await self._request(
            "POST", "/api/v3/inference/chat/completions", json=payload
        )

        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise NugenInvalidResponseError(
                "Nugen response missing choices[0].message.content"
            ) from e
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            )
        if not content or not str(content).strip():
            raise NugenEmptyResponseError("Nugen returned empty content")

        usage = data.get("usage") or {}
        return NugenChatResult(
            content=str(content).strip(),
            model=str(data.get("model") or model_id),
            confidence_score=data.get("confidence_score"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )

    # ── Platform operations (alignment provisioning / diagnostics) ─────────

    async def list_base_models(self) -> list[dict]:
        data = await self._request("GET", "/api/v3/models/base")
        return data.get("models", [])

    async def list_aligned_models(self) -> list[dict]:
        data = await self._request("GET", "/api/v3/models/aligned")
        return data.get("domain_aligned_models", [])

    async def list_alignment_projects(self) -> list[dict]:
        data = await self._request("GET", "/api/v3/alignment-projects/list")
        return data.get("alignment_projects", data.get("projects", []))

    async def deployment_status(self, model_id: str) -> dict:
        return await self._request(
            "GET", f"/api/v3/models/{model_id}/deployment/status"
        )

    async def upload_documents(
        self,
        files: list[tuple[str, bytes]],
        *,
        categories: list[str] | None = None,
        names: list[str] | None = None,
    ) -> list[str]:
        multipart = [
            ("files", (name, content, "text/plain")) for name, content in files
        ]
        data: dict = {}
        if categories:
            data["categories"] = categories
        if names:
            data["names"] = names
        resp = await self._request(
            "POST", "/api/v3/documents/create", files=multipart, data=data
        )
        return resp.get("document_ids", [])

    async def create_alignment(
        self,
        *,
        name: str,
        base_model_id: str,
        document_ids: list[str],
        description: str | None = None,
    ) -> dict:
        payload: dict = {
            "alignment_name": name,
            "base_model_id": base_model_id,
            "document_ids": document_ids,
        }
        if description:
            payload["description"] = description
        return await self._request(
            "POST", "/api/v3/alignment-projects/create", json=payload
        )

    async def alignment_status(self, alignment_id: str) -> dict:
        return await self._request(
            "GET", f"/api/v3/alignment-projects/{alignment_id}/status"
        )

    async def deploy_model(self, model_id: str) -> dict:
        return await self._request("POST", f"/api/v3/models/{model_id}/deployment")
