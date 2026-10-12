# Week 5 — CI/CD & Deployment Readiness

## CI configuration (verified in `.github/workflows/ci.yml`)

| Stage | Present? | Notes |
|---|---|---|
| Postgres+PostGIS+Timescale service | ✅ `timescale/timescaledb-ha:pg16` | health-gated |
| Redis service | ✅ `redis:7-alpine` | `redis-cli ping` healthcheck |
| Migration on scratch DB | ✅ `airquality_migrations` DB | proves clean-baseline upgrade |
| Schema-drift check | ✅ `app.tools.schema_drift` | post-migration |
| Backend suite w/ services | ✅ `TEST_DATABASE_URL`/`REDIS_URL` env | integration lane runnable in CI |
| Frontend tests/build | ✅ | standard jobs |
| OpenAPI + contract | ✅ | artifact produced |

**Honest statement:** the workflow *configuration* is correct and complete for the required services. **No CI run was observed** — nothing in this environment can see GitHub Actions state. "CI green" is NOT claimed anywhere.

## Deployment requirements (documented)

| Requirement | Value |
|---|---|
| DB | Postgres 16 + PostGIS + Timescale (Timescale-HA image covers both) |
| Redis | ≥6 (7-alpine in compose) — required for rate limits, token families, queues |
| Env | `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY` (≥32 chars, non-default — startup rejects weak keys), provider keys as needed |
| Migrations | `alembic upgrade head` — required before first start and on every schema release |
| Health probe | `GET /health` → `healthy|degraded` with per-dependency detail |
| Demo users | only via `ALLOW_DEMO_SEED` — production must leave it unset |
| Rollback | migrations are Alembic-versioned (`downgrade` available); model artifacts are file-versioned with sidecars for new trainings |

## Secrets posture

No secrets in repo; env-based config; `.env` excluded. Demo credential seeding gated by env flag. Signed media URLs TTL 300 s.

## Readiness verdict

CI *config*: READY. Deployment *config*: READY with documented prerequisites. Observed end-to-end run: **NOT VERIFIED** — requires either a Docker-capable machine running `docker compose up` or access to a CI run.
