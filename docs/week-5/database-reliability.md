# Week 5 — Database & Integration Reliability

## Required stack (verified)

- **Postgres 16 + PostGIS + TimescaleDB**: `docker-compose.yml` uses `timescale/timescaledb-ha:pg16` (ships both extensions); `ci.yml` postgres service uses the same image. Alembic migrations create PostGIS geometry columns + Timescale hypertables.
- **Redis 7**: `redis:7-alpine` in compose + CI (rate limits, token families, queues).

## Repeatable test procedure

```bash
docker compose up -d db redis                      # timescale pg16 + redis7, health-gated
cd backend && alembic upgrade head                 # clean-baseline migration test
TEST_DATABASE_URL=postgresql+asyncpg://airuser:airpass@localhost:5434/airquality_test \
REDIS_URL=redis://localhost:6379/0 \
  pytest app/tests -m integration -q
python -m app.tools.schema_drift --database-url <url>   # ORM↔migration drift check
```

CI (`ci.yml`) already: spins both services → runs migrations on a scratch DB (`airquality_migrations`) → runs schema-drift → runs the suite with `TEST_DATABASE_URL`/`REDIS_URL`. **The config exists; it has not been observed running** — local machine has no Docker daemon, and no CI run was inspectable from this environment.

## What was fixed for test-lane truthfulness

`test_redis_client_thread_safety.py` (2 tests) needed live Redis but was unmarked → failed every unit run. Now `pytestmark = [asyncio, integration]` → deselected without services, runs in CI.

## Local blocker report (honest)

| Check | Status | Why |
|---|---|---|
| Clean-DB migration upgrade | BLOCKED | no docker daemon; `localhost:5434` refused |
| PostGIS/Timescale extension presence | BLOCKED | needs the container |
| ORM↔schema drift (live) | BLOCKED | `schema_drift.py` runs but needs a migrated DB |
| Weather persistence write-path | BLOCKED | integration test written; needs DB |
| Token-family Redis tests | BLOCKED | needs Redis |
| Transaction rollback behavior | BLOCKED | needs DB |

**Nothing above is a code failure** — every blocked item has its test written and `integration`-marked. The unblock is exactly: `docker compose up -d db redis` on a machine with Docker, or an observed CI run.
