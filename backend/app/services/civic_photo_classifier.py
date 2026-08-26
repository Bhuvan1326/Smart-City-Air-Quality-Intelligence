"""AI-assisted civic issue photo classification.

Uses the same Anthropic client pattern already established in
app.agents.assistant_agent (reused, not duplicated) to ask Claude to
classify a citizen-submitted photo into one of the supported civic issue
types, with a confidence, a severity suggestion, and a one-line reason.

Per this platform's data-truthfulness rules AND the explicit civic-photo
requirement ("AI classification is not absolute truth" / "citizen must be
able to correct it"): this is a genuine, real model call — not a
fabricated or rule-based stand-in — but its result is always a
SUGGESTION. Any failure (no API key configured, timeout, rate limit,
malformed response) returns None; callers must fall back to asking the
citizen to pick the issue type themselves rather than inventing a
classification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import logger
from app.models.civic_issue import CivicIssueSeverity, CivicIssueType

_CLASSIFY_TIMEOUT_SECONDS = 20.0

_SUPPORTED_TYPES = [t.value for t in CivicIssueType]
_SUPPORTED_SEVERITIES = [s.value for s in CivicIssueSeverity]

_SYSTEM_PROMPT = (
    "You are classifying a citizen-submitted photo of a municipal civic "
    "issue for a city services app. Respond with ONLY a JSON object, no "
    "other text, in this exact shape:\n"
    '{"issue_type": "<one of: ' + ", ".join(_SUPPORTED_TYPES) + '>", '
    '"confidence": <0.0-1.0>, '
    '"severity": "<one of: ' + ", ".join(_SUPPORTED_SEVERITIES) + '>", '
    '"reasoning": "<one short sentence>"}\n'
    "If the photo does not clearly show a recognizable civic issue from "
    'that list, use issue_type "other" and a low confidence. Do not '
    "guess wildly — a low confidence is the correct response when the "
    "photo is ambiguous."
)


@dataclass
class PhotoClassification:
    issue_type: CivicIssueType
    confidence: float
    suggested_severity: CivicIssueSeverity
    reasoning: str


async def classify_photo(
    *, image_base64: str, media_type: str
) -> PhotoClassification | None:
    """Classifies a base64-encoded civic issue photo. Returns None (never
    raises, never fabricates a result) if the API key isn't configured or
    the call fails in any way.
    """
    if not settings.ANTHROPIC_API_KEY:
        return None

    try:
        import anthropic
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY, timeout=_CLASSIFY_TIMEOUT_SECONDS
        )
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Classify this civic issue photo.",
                        },
                    ],
                }
            ],
        )
    except anthropic.APITimeoutError:
        logger.warning("civic_photo_classifier.timeout")
        return None
    except anthropic.RateLimitError:
        logger.warning("civic_photo_classifier.rate_limited")
        return None
    except anthropic.APIStatusError as e:
        logger.warning("civic_photo_classifier.api_error", status=e.status_code)
        return None
    except anthropic.APIConnectionError:
        logger.warning("civic_photo_classifier.connection_error")
        return None
    except Exception:  # noqa: BLE001 -- optional AI assist, must fail open
        logger.warning("civic_photo_classifier.unexpected_error")
        return None

    text_blocks = [
        b.text for b in response.content if getattr(b, "type", None) == "text"
    ]
    if not text_blocks:
        return None

    try:
        parsed = json.loads(text_blocks[0].strip())
        issue_type = CivicIssueType(parsed["issue_type"])
        severity = CivicIssueSeverity(parsed["severity"])
        confidence = float(parsed["confidence"])
        reasoning = str(parsed.get("reasoning", ""))
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        logger.warning("civic_photo_classifier.unparseable_response")
        return None

    confidence = max(0.0, min(1.0, confidence))

    return PhotoClassification(
        issue_type=issue_type,
        confidence=confidence,
        suggested_severity=severity,
        reasoning=reasoning,
    )
