# Week 3 — Security Validation

## Fixed this week

| Finding | Severity | Fix | Regression tests |
|---|---|---|---|
| Rate limiter **fails open** on Redis outage | HIGH | `RateLimitMiddleware` → auth/admin paths get **503 fail-closed**; all others bounded in-process sliding-window fallback (`RATE_LIMIT_FALLBACK_RPM`, default 30/min/IP) — neither unlimited nor platform DoS | `test_week3_security_integration.py` — Redis-down → 503 on auth path; fallback limiter caps RPM; recovery after Redis returns |
| No login throttling | HIGH | `login_throttle` — per-identifier counter: `LOGIN_MAX_ATTEMPTS`(5) fails in `LOGIN_WINDOW_SECONDS`(300s) → 429 + `Retry-After`; success resets; Redis-primary with in-process fallback; constant response body (no account-existence oracle) | throttle blocks after N, resets on success, fallback works Redis-down, no leak in 401/429 bodies |
| WebSocket subscribable for **any city** | HIGH | After token auth, citizens restricted to `user.city` (close `4403`); staff roles unrestricted | citizen own-city accepted, foreign-city 4403, staff any-city, refresh-token rejected, unauthenticated rejected |
| Twilio absent from manifests | MED | `twilio==9.10.9` added to `requirements.txt` + `pyproject.toml`; signature validation (HMAC-SHA1, fail-closed, external callback URL) tested | 2 non-DB signature tests pass |

## Verified previously (unchanged)

Civic-report ownership server-side; staff-only drone endpoints; media signed-URL TTL 300s; notification ownership; registration hard-pins `citizen` role; refresh tokens rejected where access tokens required; no secrets in logs.

## Residual risks

| Risk | Status | Owner action |
|---|---|---|
| `python-jose` PYSEC-2025-185 | **OPEN** — no upstream fix; PyJWT migration is W5 scope | Decision: migrate (preferred) or document risk-acceptance |
| Rate-limit fallback is **per-process** — multi-replica deployments can be probed at N×cap | Documented; bounded but imperfect | Distributed fallback or Redis HA in W5 |
| 178 pip vulnerabilities / 17 pkgs | OPEN — bulk upgrade rejected (compat risk) | Triaged list → owner decisions in W5 |
| Redis-dependent tests unmarked as `integration` | OPEN — pollutes non-integration lane | Mark or provide test double in W4/W5 |

## Test evidence (this session)

`pytest app/tests/test_week3_security_integration.py app/tests/test_week3_weather_persistence.py -m "not integration"` → **24 passed, 1 deselected** (integration test needs Postgres).

Endpoint-level DB tests (cross-user/cross-ward/live-401s) are `integration`-marked and remain **BLOCKED** locally — they assert server rejection, not frontend hiding, and run in CI.
