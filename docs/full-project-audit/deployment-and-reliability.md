# Deployment & Reliability Audit

## Runtime requirements (verified)

| Requirement | Value |
|---|---|
| Env vars | `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY` (validated ≥32, non-default), `ALLOWED_ORIGINS`, `BACKEND_URL`/`NEXT_PUBLIC_API_URL` (frontend), provider keys optional-per-feature |
| Startup | `uvicorn app.main:app`; workers via `app/workers/scheduler.py` |
| Migrations | `alembic upgrade head` required (db_migrations/) |
| Health | `GET /health` → per-dependency `healthy|degraded` (db+redis checked); raw exceptions never echoed |
| Metrics | `GET /metrics` — METRICS_TOKEN Bearer or 404-in-prod |
| Probe note | `/health` distinguishes app-up from deps-ready — correct pattern |

## Failure/recovery posture

| Scenario | Behavior | Verified |
|---|---|---|
| Redis down | rate-limit: auth/admin 503, others bounded fallback; login throttle in-process; token-family reads fail-closed | unit tests |
| Redis returns | automatic, no restart | code path |
| DB down | `/health` → degraded; requests 500 at dep layer | pattern verified, live BLOCKED |
| Provider down | cycle skipped+logged; stale flags; no fake data | code-verified |
| Model missing | forecast → model-unavailable state | verified |
| Twilio down | signature layer unaffected; service calls try/except | code-verified |

## Observability

- Structured logging `app.core.logging` (loguru-style); security events logged (`refresh_token.reuse_detected`, `health.dependency_error`, `rate_limit.redis_unavailable`).
- **No** request-correlation IDs, no Prometheus metrics middleware yet (`/metrics` exists but app instrumentation is minimal) — documented gaps, P4.
- Audit log middleware writes mutating requests to DB async.
- No secrets/tokens/PII in log statements (grep-verified).

## Deployment verdict

Config-complete and documented; **unexecuted** — no deploy performed, no hosting URL claimed, no live availability asserted. Free-tier/hosting limits not assessed (no hosting config in repo beyond compose).
