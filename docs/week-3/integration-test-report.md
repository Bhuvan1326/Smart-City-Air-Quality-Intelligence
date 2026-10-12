# Week 3 — Integration Test Report

Environment: Windows, Python 3.12.10 (`backend/.venv`), Node 24.21.0. **No Postgres (`:5434` refused), no Redis (`:6379` refused), no Playwright browsers, no Docker** — every such check is BLOCKED, not failed.

## Commands actually run (this session, post-changes)

| Check | Command | Result | Counts |
|---|---|---|---|
| Backend compile | `python -m compileall -q app` | PASS | — |
| Black | `python -m black --check app` | PASS | 275 files clean (after formatting 6 new files) |
| isort | `python -m isort --check-only app` | PASS | — |
| Ruff | `python -m ruff check app` | PASS | 0 errors (1 unused import fixed) |
| W3 security + weather tests | `pytest test_week3_security_integration.py test_week3_weather_persistence.py -m "not integration"` | PASS | **24 passed, 1 deselected** |
| App startup + routes | `python -c "from app.main import app; …"` | PASS | **124 routes**; `/enforcement/outcomes` registered before `/{action_id}`; 0 dup operation IDs |
| OpenAPI regen | `app.openapi()` → `openapi.json` | PASS | written to repo root |
| Contract drift | `npm run contract:check` | PASS | **93 calls, 1232 fields, 0 errors, 0 warnings** (+2 calls vs baseline — the new outcome endpoints) |
| Frontend tsc | `npx tsc --noEmit` | PASS | 0 errors (incl. new `ImpactLedgerCard`, `services.ts` types) |
| ML eval pipeline | `python -m app.ml.evaluation --csv ml-eval-fixture/…` | PASS (fixture) | 4 horizons × 5 models scored; artifact `walk_forward_results.json` |

## Carried-forward results (unchanged code paths, still valid)

| Check | Result |
|---|---|
| Frontend unit tests | 49 passed |
| Frontend ESLint | 0 errors, 12 warnings |
| Frontend `next build` | PASS (lockfile-root warning remains) |
| Backend non-integration suite | 691 passed, 2 failed (Redis env — tests hit `localhost:6379`, unmarked) |
| npm audit | 2 remaining (requires breaking next@16 upgrade) |
| pip-audit | 178 findings / 17 pkgs — untriaged |

## BLOCKED (infrastructure, not code)

| Check | Blocker | Unblock requirement |
|---|---|---|
| DB-backed tests (258 `integration` tests incl. weather persistence, outcome endpoints, cross-ward authz) | Postgres `:5434` connection refused | `docker compose up db` (Postgres+PostGIS+TimescaleDB) or CI `db` service |
| 2 Redis client tests in non-integration lane | Redis `:6379` refused; tests unmarked | Mark `integration` or run Redis |
| Live schema-drift check | needs migrated DB | same DB stack |
| Playwright role walkthrough | browsers uninstalled + no running stack | `npx playwright install` + `docker compose up` |
| Real ML evaluation | no populated observation DB | ≥35 days ingested data (see ml-evaluation.md) |
| Coverage gate (80%) | last full run stalled at DB connect; non-integration lane measured 70.51% | full suite needs DB+Redis |

## Status by journey

| Journey | Status |
|---|---|
| Weather ingest → persist → ML features | **PARTIAL** — writer implemented+unit-tested; live DB round-trip BLOCKED |
| Outcome record → list → UI | **PARTIAL** — API+types+card implemented, contract-checked; DB tests BLOCKED |
| Login under Redis outage | **VERIFIED (unit)** — fail-closed/throttled paths tested; multi-node behavior untested |
| Citizen WS subscription | **VERIFIED (unit)** — authz logic tested; live socket handshake BLOCKED |
| Citizen dashboard/alerts | VERIFIED previously (contract + unit) |
