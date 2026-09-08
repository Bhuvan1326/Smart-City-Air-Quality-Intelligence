"""Coverage for the OpenAQ 401 root cause: `docker-compose.yml` passes
`OPENAQ_API_KEY=${OPENAQ_API_KEY:-}` straight through from `.env`, and
neither `.env` interpolation nor Compose's own parsing strips
`"..."`/`'...'` quoting the way a shell would. A hand-edited
`OPENAQ_API_KEY="abcd1234"` in `.env` therefore becomes the literal
string `"abcd1234"` (quotes included) by the time it reaches the
container — non-empty, so `is_configured()` still reports it as set,
but OpenAQ rejects it outright with 401 since it isn't the real key.
"""

import pytest

from app.core.config import Settings


def _settings(**overrides) -> Settings:
    # Explicit kwargs take priority over any real .env/environment in
    # pydantic-settings, and _env_file=None stops it from also reading a
    # real .env file that happens to exist on disk during test runs.
    return Settings(_env_file=None, **overrides)


def test_openaq_api_key_double_quotes_are_stripped():
    s = _settings(OPENAQ_API_KEY='"abcd1234efgh"')
    assert s.OPENAQ_API_KEY == "abcd1234efgh"


def test_openaq_api_key_single_quotes_are_stripped():
    s = _settings(OPENAQ_API_KEY="'abcd1234efgh'")
    assert s.OPENAQ_API_KEY == "abcd1234efgh"


def test_openaq_api_key_surrounding_whitespace_is_stripped():
    s = _settings(OPENAQ_API_KEY="  abcd1234efgh  ")
    assert s.OPENAQ_API_KEY == "abcd1234efgh"


def test_openaq_api_key_whitespace_then_quotes_both_stripped():
    s = _settings(OPENAQ_API_KEY='  "abcd1234efgh"  ')
    assert s.OPENAQ_API_KEY == "abcd1234efgh"


def test_openaq_api_key_unquoted_value_untouched():
    s = _settings(OPENAQ_API_KEY="abcd1234efgh")
    assert s.OPENAQ_API_KEY == "abcd1234efgh"


def test_openaq_api_key_mismatched_quote_left_alone():
    # Only a genuinely matching pair of leading/trailing quote characters
    # is treated as accidental wrapping — a lone quote could plausibly be
    # part of the real key, so it's left untouched rather than guessed at.
    s = _settings(OPENAQ_API_KEY='"abcd1234efgh')
    assert s.OPENAQ_API_KEY == '"abcd1234efgh'


def test_openaq_api_key_empty_stays_empty_and_unconfigured():
    s = _settings(OPENAQ_API_KEY="")
    assert s.OPENAQ_API_KEY == ""


def test_openaq_base_url_quotes_are_stripped_and_still_valid():
    s = _settings(OPENAQ_BASE_URL='"https://api.openaq.org/v3"')
    assert s.OPENAQ_BASE_URL == "https://api.openaq.org/v3"


def test_openaq_base_url_blank_falls_back_to_default_after_sanitizing():
    # Blank-fallback and quote-stripping must compose correctly regardless
    # of which validator runs first.
    s = _settings(OPENAQ_BASE_URL="")
    assert s.OPENAQ_BASE_URL == "https://api.openaq.org/v3"


# ---------------------------------------------------------------------------
# Production SECRET_KEY validation.
#
# `docker-compose.yml` used to fall back to a *different* insecure
# placeholder ("...min-32-chars") than the one the backend rejected
# ("...min-32-chars-long"), so a production deploy relying on Compose's
# default could silently start with a publicly-known JWT signing secret.
# These tests pin down the full fail-fast contract: missing, too short, or
# any known placeholder must all refuse to boot in production, while
# development/staging and a valid production secret must keep working.
# ---------------------------------------------------------------------------

_VALID_PRODUCTION_SECRET_KEY = "a" * 40  # unique, random-looking, 32+ chars


def test_production_missing_secret_key_fails():
    with pytest.raises(ValueError, match="SECRET_KEY is missing"):
        _settings(ENVIRONMENT="production", SECRET_KEY="")


def test_production_whitespace_only_secret_key_fails():
    with pytest.raises(ValueError, match="SECRET_KEY is missing"):
        _settings(ENVIRONMENT="production", SECRET_KEY="   ")


def test_production_short_secret_key_fails():
    with pytest.raises(ValueError, match="too short"):
        _settings(ENVIRONMENT="production", SECRET_KEY="short-key-12345")


def test_production_backend_default_placeholder_fails():
    with pytest.raises(ValueError, match="insecure placeholder"):
        _settings(
            ENVIRONMENT="production",
            SECRET_KEY="changeme-in-production-min-32-chars-long",
        )


def test_production_docker_compose_placeholder_fails():
    # This is the specific placeholder docker-compose.yml used to fall
    # back to — distinct from the backend's own default above — which is
    # the exact mismatch that let production start with a known secret.
    with pytest.raises(ValueError, match="insecure placeholder"):
        _settings(
            ENVIRONMENT="production",
            SECRET_KEY="changeme-in-production-min-32-chars",
        )


def test_production_env_example_placeholder_fails():
    with pytest.raises(ValueError, match="insecure placeholder"):
        _settings(
            ENVIRONMENT="production",
            SECRET_KEY="changeme-generate-a-secure-32-char-secret-key",
        )


def test_production_valid_secret_key_succeeds():
    s = _settings(ENVIRONMENT="production", SECRET_KEY=_VALID_PRODUCTION_SECRET_KEY)
    assert s.SECRET_KEY == _VALID_PRODUCTION_SECRET_KEY


def test_development_default_secret_key_is_unrestricted():
    # Development/test environments may keep using the documented
    # test-only default without the app refusing to start.
    s = _settings(ENVIRONMENT="development")
    assert s.SECRET_KEY == "changeme-in-production-min-32-chars-long"


def test_development_docker_compose_placeholder_is_unrestricted():
    s = _settings(
        ENVIRONMENT="development",
        SECRET_KEY="changeme-in-production-min-32-chars",
    )
    assert s.SECRET_KEY == "changeme-in-production-min-32-chars"
