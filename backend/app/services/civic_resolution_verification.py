"""AI before/after resolution verification.

Reuses the same Anthropic client pattern already established in
app.services.civic_photo_classifier (itself reused from
app.agents.assistant_agent) rather than duplicating it. Compares a
civic issue's original ("before") photo against the officer-submitted
resolution ("after") photo and returns one of three deliberately
non-absolute verdicts — this platform never claims certainty about
whether an issue was actually fixed from a photo comparison alone.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import logger
from app.models.civic_issue import AIVerificationResult

_VERIFY_TIMEOUT_SECONDS = 25.0

_SUPPORTED_RESULTS = [r.value for r in AIVerificationResult]

_SYSTEM_PROMPT = (
    "You are comparing a BEFORE photo (the original civic issue report) "
    "and an AFTER photo (submitted by a municipal officer claiming the "
    "issue is resolved) for a city services app. Respond with ONLY a "
    "JSON object, no other text, in this exact shape:\n"
    '{"result": "<one of: ' + ", ".join(_SUPPORTED_RESULTS) + '>", '
    '"confidence": <0.0-1.0>, '
    '"reasoning": "<one short sentence>"}\n'
    'Use "likely_resolved" only when the after photo clearly shows the '
    'specific problem from the before photo is gone. Use "needs_review" '
    "when the photos are ambiguous, show a different angle/location, or "
    'the change is unclear. Use "insufficient_evidence" when the after '
    "photo doesn't let you meaningfully compare (e.g. wrong subject, too "
    "dark, doesn't show the reported location). You are never certain — "
    "a photo comparison alone cannot prove a physical repair took place."
)


@dataclass
class ResolutionVerification:
    result: AIVerificationResult
    confidence: float
    reasoning: str


def _media_type_for(data_url: str) -> tuple[str, str] | None:
    """Parses a data:image/...;base64,... URL into (media_type, payload).
    Returns None for anything else — callers must not guess.
    """
    if not data_url.startswith("data:"):
        return None
    try:
        header, payload = data_url.split(",", 1)
        media_type = header[len("data:") : header.index(";")]
    except (ValueError, IndexError):
        return None
    if media_type not in ("image/jpeg", "image/png", "image/webp"):
        return None
    return media_type, payload


async def verify_resolution(
    *, before_photo_url: str | None, after_photo_data_url: str
) -> ResolutionVerification | None:
    """Returns None (never raises, never fabricates a verdict) if the API
    key isn't configured, the before photo isn't available, or the call
    fails in any way. Callers must treat None as "AI verification
    unavailable" and rely on citizen confirmation alone.
    """
    if not settings.ANTHROPIC_API_KEY or not before_photo_url:
        return None

    after = _media_type_for(after_photo_data_url)
    if after is None:
        return None
    after_media_type, after_payload = after

    from app.services.evidence_storage import EvidenceStorage

    before_read = EvidenceStorage().read_photo(before_photo_url)
    if before_read is None:
        return None
    before_bytes, before_media_type = before_read
    before_payload = base64.b64encode(before_bytes).decode("ascii")

    try:
        import anthropic
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY, timeout=_VERIFY_TIMEOUT_SECONDS
        )
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "BEFORE photo (original report):"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": before_media_type,
                                "data": before_payload,
                            },
                        },
                        {
                            "type": "text",
                            "text": "AFTER photo (officer's resolution submission):",
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": after_media_type,
                                "data": after_payload,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Compare these and classify the resolution.",
                        },
                    ],
                }
            ],
        )
    except anthropic.APITimeoutError:
        logger.warning("civic_resolution_verification.timeout")
        return None
    except anthropic.RateLimitError:
        logger.warning("civic_resolution_verification.rate_limited")
        return None
    except anthropic.APIStatusError as e:
        logger.warning("civic_resolution_verification.api_error", status=e.status_code)
        return None
    except anthropic.APIConnectionError:
        logger.warning("civic_resolution_verification.connection_error")
        return None
    except Exception:  # noqa: BLE001 -- optional AI assist, must fail open
        logger.warning("civic_resolution_verification.unexpected_error")
        return None

    text_blocks = [
        b.text for b in response.content if getattr(b, "type", None) == "text"
    ]
    if not text_blocks:
        return None

    try:
        parsed = json.loads(text_blocks[0].strip())
        result = AIVerificationResult(parsed["result"])
        confidence = max(0.0, min(1.0, float(parsed["confidence"])))
        reasoning = str(parsed.get("reasoning", ""))
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        logger.warning("civic_resolution_verification.unparseable_response")
        return None

    return ResolutionVerification(
        result=result, confidence=confidence, reasoning=reasoning
    )
