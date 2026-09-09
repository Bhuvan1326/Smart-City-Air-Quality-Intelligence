import pytest

from app.core.config import Settings


def _settings(**overrides) -> Settings:
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
    s = _settings(OPENAQ_API_KEY='"abcd1234efgh')
    assert s.OPENAQ_API_KEY == '"abcd1234efgh'


def test_openaq_api_key_empty_stays_empty_and_unconfigured():
    s = _settings(OPENAQ_API_KEY="")
    assert s.OPENAQ_API_KEY == ""


def test_openaq_base_url_quotes_are_stripped_and_still_valid():
    s = _settings(OPENAQ_BASE_URL='"https://api.openaq.org/v3"')
    assert s.OPENAQ_BASE_URL == "https://api.openaq.org/v3"


def test_openaq_base_url_blank_falls_back_to_default_after_sanitizing():
    s = _settings(OPENAQ_BASE_URL="")
    assert s.OPENAQ_BASE_URL == "https://api.openaq.org/v3"


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


def test_development_default_secret_key_is_unrestricted(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    s = _settings(ENVIRONMENT="development")
    assert s.SECRET_KEY == "changeme-in-production-min-32-chars-long"


def test_development_docker_compose_placeholder_is_unrestricted():
    s = _settings(
        ENVIRONMENT="development",
        SECRET_KEY="changeme-in-production-min-32-chars",
    )
    assert s.SECRET_KEY == "changeme-in-production-min-32-chars"
