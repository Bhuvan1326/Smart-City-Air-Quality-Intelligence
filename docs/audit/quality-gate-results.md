# Quality-Gate Results — Week 1 + Week 2 Audit

Every row below reflects a command actually executed during this audit (or a check verified as unrunnable with the exact prerequisite listed). Nothing is claimed from prior reports.

**Host:** Windows, Python 3.12.10 (`backend/.venv`), Node v24.21.0, npm 11.19.0
**Unavailable services:** Docker, PostgreSQL+PostGIS+TimescaleDB on :5434, Redis on :6379, Playwright browsers, WSL (unresponsive)

## Backend

| Check | Command | Result | Counts / evidence | Blocker |
|---|---|---|---|---|
| Python compile | `python -m compileall -q app` | PASS | exit 0 | — |
| Black | `python -m black --check app` | PASS | `269 files would be left unchanged` | — |
| isort | `python -m isort --check-only app` | PASS | exit 0 | — |
| Ruff | `python -m ruff check app` | PASS | `All checks passed!` | — |
| App import | `python -c "from app.main import app"` | PASS (after AUD-001 fix) | `routes: 122` | was broken: `api_router` missing |
| Backend tests — no-service lane | `pytest -m "not integration"` | **FAIL (env)** | `691 passed, 2 failed, 2 skipped, 258 deselected` in 3:32 | 2 failures = `ConnectionRefusedError` to Redis `localhost:6379` (no server); tests unmarked for `integration` (AUD-006) |
| Backend tests — full suite | `pytest app/tests` | **BLOCKED** | 953 collected; 258 `integration` tests error at fixture (`_ensure_test_database_exists` → `localhost:5434` refused) | No Postgres+PostGIS+TimescaleDB; native PG 18 on :5432 lacks extension files; Docker absent; WSL hung |
| Coverage | `pytest --cov=app --cov-fail-under=80` (via addopts) | NOT ASSESSABLE | Non-DB lane: **70.51%** total; gate is designed for the full suite | Same DB blocker; partial-file runs report 22–35% by design |
| IVR signature unit tests | `pytest test_week2_ivr_signature.py` | 2 PASS / 7 ERR | Non-DB tests pass incl. **`test_matches_official_twilio_sdk_algorithm`** (official SDK cross-check); 7 DB-fixture errors | DB |
| Schema-drift tool tests | `pytest test_week2_schema_drift.py` | PASS | 4 passed, 1 skipped | — |
| Schema-drift live run | `python -m app.tools.schema_drift --database-url …` | BLOCKED | baseline = 124 signatures (matches documented) | Needs `alembic upgrade head` on live DB |
| Alembic heads | `alembic heads` | PASS (static) | single head `025_retire_alandi_karve_road`; 26 revisions; linear chain | live `upgrade` unverifiable without DB |
| OpenAPI generation | `python -c "app.openapi()"` | PASS | 115 operations, **0 duplicate operation IDs** (after AUD-005 fix) | — |
| pip-audit | `python -m pip_audit` | FINDINGS | **178 known vulnerabilities in 17 packages** — see §Python below | remediation backlog |

## Frontend

| Check | Command | Result | Counts / evidence | Blocker |
|---|---|---|---|---|
| Unit tests | `npm test` | PASS | `tests 49, pass 49, fail 0` — includes contract-checker drift fixtures (aligned → exit 0, deliberate drift → exit 1) | — |
| TypeScript | `npx tsc --noEmit` | PASS (after AUD-002 + edit repair) | exit 0 | was failing: missing `extractErrorMessage` export |
| ESLint | `npx eslint .` | PASS w/ warnings | **0 errors, 12 warnings** (unused vars/directives, 1 `react-hooks/exhaustive-deps`) | warnings pre-existing |
| Production build | `npm run build` | PASS | next **15.5.27**, 47 static routes + middleware; workspace-root lockfile warning only | — |
| API contract drift | `npm run contract:check` | PASS | `callsCompared:91, fieldsCompared:1193, callsWithoutTypedResponse:1, errors:0, warnings:0, staleExceptions:0` | regenerated `openapi.json` after router + IVR changes |
| Playwright | `npx playwright test` | **BLOCKED** | Spec authored (`e2e/role-walkthrough.spec.ts`, 4 roles × route matrix + API-403 check); browsers not installed; needs running FE+BE+DB + `E2E_DEMO_PASSWORD` | browsers, live stack |
| npm audit (prod) | `npm audit --omit=dev` | FINDINGS → PARTIALLY FIXED | before: 8 (1 critical, 7 high); after `npm audit fix`: **2 remain** (postcss ≤8.5.22 via `next`, 1 moderate) — fixes need `next@16` major | major-version decision |
| Bundle secret scan | `grep` on `.next/static` | PASS | no demo passwords, no key-material patterns | — |

## Dependency advisories

### npm (`npm audit fix` applied — semver-compatible only)
- **Fixed:** `next` 15.5.20→15.5.27 (clears critical advisories incl. GHSA-p293-qw3h-jr36 unauthenticated RCE on Windows hosts, image-optimization RCE, SSRF/DoS set), axios, nanoid, sharp, source-map-js, playwright.
- **Remaining (2):** `postcss ≤8.5.22` bundled inside `next@15.5.27` + 1 moderate — both resolve only via `next@16.4.0` (breaking). **Owner decision required.**

### pip (`pip-audit`, no changes applied — needs compatibility review)
178 advisories across 17 packages. Notable:
- **No fix available:** `python-jose` PYSEC-2025-185 (JOSE algorithm confusion — migrate to PyJWT), `chromadb` (2), `ecdsa`, `weasyprint` PYSEC-2026-3412.
- **Fixes exist:** `aiohttp` 3.11.10→3.13.x (30+ IDs), `starlette` 0.41.3→≥0.47.2, `python-multipart` 0.0.12→≥0.0.18, `pillow` 11.0.0→12.x, `weasyprint`→68+, `jinja2` 3.1.4→3.1.6, `langgraph`/`langgraph-checkpoint`/`langgraph-sdk`, `langchain-core`, `mcp`, `black`, `pytest`, `json-repair`.
- Bulk upgrade deferred: requirements are `==`-pinned in two manifests; upgrades need CI verification (owner: Infra/Backend).

## CI/CD

- `.github/workflows/ci.yml` inspected: Postgres+**Timescale** service, migration step, schema-drift step, contract check, coverage gate — all present.
- **GitHub Actions: NOT VERIFIED** — no run evidence obtainable locally; local reproduction is blocked by the same missing services. Do not claim green CI.

## Environment-blocked summary

| Prerequisite | Unblocks |
|---|---|
| Postgres+PostGIS+TimescaleDB @ :5434 | 258 integration tests, alembic upgrade, schema-drift live run, real coverage %, DB-backed security tests (civic/drone/media/notification/IVR endpoint tests) |
| Redis @ :6379 | 2 redis-client tests, rate-limiter behavior |
| Playwright browsers + running stack | four-role browser walkthrough, page states |
| Populated DB (≥90d) | real export, gap report, walk-forward eval, MAE/RMSE |
