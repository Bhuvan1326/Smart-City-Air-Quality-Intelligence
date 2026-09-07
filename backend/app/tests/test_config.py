"""Coverage for the OpenAQ 401 root cause: `docker-compose.yml` passes
`OPENAQ_API_KEY=${OPENAQ_API_KEY:-}` straight through from `.env`, and
neither `.env` interpolation nor Compose's own parsing strips
`"..."`/`'...'` quoting the way a shell would. A hand-edited
`OPENAQ_API_KEY="abcd1234"` in `.env` therefore becomes the literal
string `"abcd1234"` (quotes included) by the time it reaches the
container — non-empty, so `is_configured()` still reports it as set,
but OpenAQ rejects it outright with 401 since it isn't the real key.
"""

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
