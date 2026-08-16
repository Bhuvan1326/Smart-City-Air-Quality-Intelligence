"""
Input sanitization helpers.

The primary defenses against injection already exist structurally:
  - SQL injection: every query goes through SQLAlchemy's parameter binding
    (Core `text()` with bound params, or the ORM) — nowhere in the codebase
    is user input interpolated directly into SQL strings.
  - XSS: the frontend is React/Next.js, which escapes interpolated text by
    default.

This module adds a second layer of defense on top of that structural
protection for the free-text fields users write (alert messages, enforcement
notes, descriptions) — stripping control characters, collapsing whitespace,
enforcing length caps, and rejecting content that contains raw HTML/script
markup rather than silently "fixing" it (silent rewriting can hide intent
from moderators reviewing officer notes).
"""

from __future__ import annotations

import re
import unicodedata

_SCRIPT_PATTERN = re.compile(r"<\s*script[^>]*>|javascript:|on\w+\s*=", re.IGNORECASE)
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class UnsafeInputError(ValueError):
    """Raised when input contains content that looks like an injection attempt."""


def sanitize_text(
    value: str, *, max_length: int = 5000, field_name: str = "field"
) -> str:
    """
    Normalize and validate free-text input.

    - Normalizes unicode (NFKC) to prevent homoglyph/lookalike smuggling.
    - Strips control characters.
    - Collapses excessive whitespace.
    - Rejects (rather than strips) obvious script/HTML injection attempts,
      since silently stripping tags can mask malicious intent in an audit
      trail — better to reject and let the caller see why.
    """
    if not isinstance(value, str):
        return value

    normalized = unicodedata.normalize("NFKC", value)
    normalized = _CONTROL_CHARS.sub("", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized).strip()

    if _SCRIPT_PATTERN.search(normalized):
        raise UnsafeInputError(f"{field_name} contains disallowed script content")

    if len(normalized) > max_length:
        raise UnsafeInputError(
            f"{field_name} exceeds maximum length of {max_length} characters"
        )

    return normalized


def strip_html(value: str) -> str:
    """Remove HTML tags entirely. Used for fields where no markup is ever valid (titles, names)."""
    if not isinstance(value, str):
        return value
    return _HTML_TAG_PATTERN.sub("", value).strip()


def is_safe_identifier(value: str) -> bool:
    """Whitelist check for things used to build dynamic query fragments (e.g. sort columns)."""
    return bool(re.fullmatch(r"[A-Za-z0-9_]{1,64}", value))
