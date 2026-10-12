import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1.endpoints.websocket import is_city_subscription_allowed
from app.core.local_rate_limit import LocalRateLimiter, local_rate_limiter
from app.core.middleware import RateLimitMiddleware
from app.models.user import User, UserRole
from app.services import login_throttle


def _user(role: UserRole, city: str | None = "Pune") -> User:
    return User(
        email="t@t.in",
        hashed_password="x",
        full_name="T",
        role=role,
        city=city,
    )


# ------------------------------------------------------- WS authorization
class TestWebSocketCityAuthorization:
    @pytest.mark.parametrize(
        "role",
        [
            UserRole.CITY_ADMINISTRATOR,
            UserRole.POLLUTION_CONTROL_OFFICER,
            UserRole.FIELD_INSPECTOR,
        ],
    )
    def test_staff_may_subscribe_to_any_city(self, role):
        assert is_city_subscription_allowed(_user(role, "Pune"), "Mumbai")
        assert is_city_subscription_allowed(_user(role, None), "Delhi")

    def test_citizen_allowed_own_city_only(self):
        citizen = _user(UserRole.CITIZEN, "Pune")
        assert is_city_subscription_allowed(citizen, "Pune")
        assert is_city_subscription_allowed(citizen, "pune")  # case-insensitive
        assert not is_city_subscription_allowed(citizen, "Mumbai")
        assert not is_city_subscription_allowed(citizen, "Delhi")

    def test_citizen_without_city_is_denied_everything(self):
        citizen = _user(UserRole.CITIZEN, None)
        assert not is_city_subscription_allowed(citizen, "Pune")


# ------------------------------------------------------- local fallback
class TestLocalRateLimiter:
    def test_hit_increments_within_window(self):
        limiter = LocalRateLimiter()
        assert limiter.hit("1.2.3.4", now=60_000) == 1
        assert limiter.hit("1.2.3.4", now=60_000) == 2
        assert limiter.hit("5.6.7.8", now=60_000) == 1

    def test_window_roll_resets_counts(self):
        limiter = LocalRateLimiter()
        for _ in range(5):
            limiter.hit("1.2.3.4", now=60_000)
        assert limiter.hit("1.2.3.4", now=60_060) == 1  # next minute


# ------------------------------------------------------- middleware policy
def _request(path: str, ip: str = "8.8.8.8") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": (ip, 12345),
    }
    return Request(scope)


async def _ok(request):
    return Response(status_code=200)


@pytest.fixture(autouse=True)
def _reset_fallback():
    local_rate_limiter.reset()
    yield
    local_rate_limiter.reset()


class TestRateLimitFailurePolicy:
    async def test_redis_outage_auth_path_gets_strict_cap(self, monkeypatch):
        from app.core import redis_client

        async def _boom():
            raise ConnectionError("redis down")

        monkeypatch.setattr(redis_client, "get_redis", _boom)
        mw = RateLimitMiddleware(app=None)
        path = "/api/v1/auth/login"

        for _ in range(10):
            resp = await mw.dispatch(_request(path), _ok)
            assert resp.status_code == 200
        resp = await mw.dispatch(_request(path), _ok)
        assert resp.status_code == 429

    async def test_redis_outage_normal_path_uses_normal_cap(self, monkeypatch):
        from app.core import redis_client
        from app.core.config import settings

        async def _boom():
            raise ConnectionError("redis down")

        monkeypatch.setattr(redis_client, "get_redis", _boom)
        mw = RateLimitMiddleware(app=None)
        path = "/api/v1/dashboard/overview"

        for _ in range(settings.RATE_LIMIT_PER_MINUTE):
            resp = await mw.dispatch(_request(path, ip="9.9.9.9"), _ok)
            assert resp.status_code == 200
        resp = await mw.dispatch(_request(path, ip="9.9.9.9"), _ok)
        assert resp.status_code == 429

    async def test_redis_outage_auth_cap_is_per_ip(self, monkeypatch):
        from app.core import redis_client

        async def _boom():
            raise ConnectionError("redis down")

        monkeypatch.setattr(redis_client, "get_redis", _boom)
        mw = RateLimitMiddleware(app=None)
        for _ in range(11):
            await mw.dispatch(_request("/api/v1/auth/login", ip="8.8.8.8"), _ok)
        # a different IP still gets its own budget
        resp = await mw.dispatch(_request("/api/v1/auth/login", ip="7.7.7.7"), _ok)
        assert resp.status_code == 200


# ------------------------------------------------------- login throttle
class TestLoginThrottle:
    @pytest.fixture(autouse=True)
    def _reset(self):
        login_throttle.reset_local_throttle()
        yield
        login_throttle.reset_local_throttle()

    async def test_local_fallback_locks_after_max_attempts(self, monkeypatch):
        from app.core import redis_client

        async def _boom():
            raise ConnectionError("redis down")

        monkeypatch.setattr(redis_client, "get_redis", _boom)
        email = "victim@x.in"
        from app.core.config import settings

        for _ in range(settings.LOGIN_MAX_ATTEMPTS - 1):
            await login_throttle.record_failure(email)
            assert not await login_throttle.is_locked(email)
        await login_throttle.record_failure(email)
        assert await login_throttle.is_locked(email)

    async def test_lock_applies_to_nonexistent_email_equally(self, monkeypatch):
        from app.core import redis_client
        from app.core.config import settings

        async def _boom():
            raise ConnectionError("redis down")

        monkeypatch.setattr(redis_client, "get_redis", _boom)
        ghost = "no-such-account@x.in"
        for _ in range(settings.LOGIN_MAX_ATTEMPTS):
            await login_throttle.record_failure(ghost)
        assert await login_throttle.is_locked(ghost)

    async def test_clear_failures_unlocks(self, monkeypatch):
        from app.core import redis_client
        from app.core.config import settings

        async def _boom():
            raise ConnectionError("redis down")

        monkeypatch.setattr(redis_client, "get_redis", _boom)
        email = "u@x.in"
        for _ in range(settings.LOGIN_MAX_ATTEMPTS):
            await login_throttle.record_failure(email)
        assert await login_throttle.is_locked(email)
        await login_throttle.clear_failures(email)
        assert not await login_throttle.is_locked(email)

    def test_local_throttle_prunes_out_of_window_failures(self, monkeypatch):
        from app.core.config import settings

        email = "old@x.in"
        ancient = int(__import__("time").time()) - settings.LOGIN_WINDOW_SECONDS - 10
        for _ in range(settings.LOGIN_MAX_ATTEMPTS):
            login_throttle._local._failures[email] = [ancient] * 5
        assert not login_throttle._local.is_locked(email)


# ------------------------------------------------------- outcome schemas
class TestOutcomeSchemaContract:
    def test_confidence_is_required_no_silent_default(self):
        from app.schemas.enforcement import InterventionOutcomeCreate

        with pytest.raises(Exception):
            InterventionOutcomeCreate(
                aqi_before=200,
                aqi_after=100,
                measurement_period_hours=24,
                verification_method="24h CAAQMS comparison",
            )  # no confidence_score → must fail validation

    def test_valid_payload(self):
        from app.schemas.enforcement import InterventionOutcomeCreate

        req = InterventionOutcomeCreate(
            aqi_before=195,
            aqi_after=128,
            measurement_period_hours=24,
            verification_method="24h CAAQMS comparison",
            confidence_score=0.84,
        )
        assert req.aqi_before - req.aqi_after == 67.0
