from datetime import timedelta

import pytest
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class _FakeRedis:
    """Minimal in-memory stand-in for the subset of redis.asyncio used by security.py."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()

    async def _get_redis():
        return fake

    monkeypatch.setattr("app.core.redis_client.get_redis", _get_redis)
    return fake


def test_password_hashing():
    password = "SecurePass@123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)


def test_wrong_password_rejected():
    hashed = hash_password("CorrectPassword")
    assert not verify_password("WrongPassword", hashed)


def test_access_token_creates_and_decodes():
    token = create_access_token("test-user-id")
    payload = decode_token(token)
    assert payload["sub"] == "test-user-id"
    assert payload["type"] == "access"


def test_refresh_token_type():
    token, jti, family_id = create_refresh_token("user-123")
    payload = decode_token(token)
    assert payload["type"] == "refresh"
    assert payload["sub"] == "user-123"
    assert payload["jti"] == jti
    assert payload["fam"] == family_id


def test_access_token_cannot_be_used_as_refresh():
    token = create_access_token("user-id")
    payload = decode_token(token)
    assert payload["type"] != "refresh"


def test_invalid_token_raises():
    with pytest.raises(ValueError):
        decode_token("not.a.valid.jwt")


def test_expired_token_raises():
    token = create_access_token("user-id", expires_delta=timedelta(seconds=-1))
    with pytest.raises(ValueError):
        decode_token(token)


def test_refresh_token_includes_jti_and_family():
    token, jti, family_id = create_refresh_token("user-123")
    payload = decode_token(token)
    assert payload["jti"] == jti
    assert payload["fam"] == family_id


@pytest.mark.asyncio
async def test_refresh_rotation_accepts_current_jti(fake_redis):
    from app.core.security import register_refresh_token, validate_and_rotate

    await register_refresh_token("fam-1", "jti-1", ttl_seconds=3600)
    assert await validate_and_rotate("fam-1", "jti-1") is True


@pytest.mark.asyncio
async def test_refresh_reuse_is_rejected_and_revokes_family(fake_redis):
    from app.core.security import (
        is_family_revoked,
        register_refresh_token,
        validate_and_rotate,
    )

    await register_refresh_token("fam-2", "jti-old", ttl_seconds=3600)
    # Simulate rotation: server now expects jti-new
    await register_refresh_token("fam-2", "jti-new", ttl_seconds=3600)

    # Attacker replays the old (already-rotated-out) token
    result = await validate_and_rotate("fam-2", "jti-old")
    assert result is False
    assert await is_family_revoked("fam-2") is True


@pytest.mark.asyncio
async def test_revoked_family_rejects_even_current_jti(fake_redis):
    from app.core.security import (
        register_refresh_token,
        revoke_family,
        validate_and_rotate,
    )

    await register_refresh_token("fam-3", "jti-1", ttl_seconds=3600)
    await revoke_family("fam-3")
    assert await validate_and_rotate("fam-3", "jti-1") is False


def test_sanitize_text_rejects_script_injection():
    from app.core.sanitization import UnsafeInputError, sanitize_text

    with pytest.raises(UnsafeInputError):
        sanitize_text("<script>alert(1)</script>", field_name="notes")


def test_sanitize_text_normalizes_whitespace():
    from app.core.sanitization import sanitize_text

    assert sanitize_text("hello    world  ") == "hello world"


def test_sanitize_text_enforces_max_length():
    from app.core.sanitization import UnsafeInputError, sanitize_text

    with pytest.raises(UnsafeInputError):
        sanitize_text("a" * 20, max_length=10, field_name="title")


@pytest.mark.asyncio
async def test_security_headers_present_on_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert "content-security-policy" in resp.headers


def test_aqi_category_boundaries():
    from app.schemas.aqi import get_aqi_category

    assert get_aqi_category(50)[0] == "Good"
    assert get_aqi_category(51)[0] == "Moderate"
    assert get_aqi_category(101)[0] == "Unhealthy for Sensitive Groups"
    assert get_aqi_category(151)[0] == "Unhealthy"
    assert get_aqi_category(201)[0] == "Very Unhealthy"
    assert get_aqi_category(301)[0] == "Hazardous"
