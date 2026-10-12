# Week 3 Implementation Plan — Smart City Air Quality Intelligence Platform

**Baseline:** branch `main` @ `ff33c0f` ("Fixed bugs" — the Week 1+2 audit remediation, pushed). Working tree clean.
**Environment truth (re-verified this session):** Python 3.12.10 (`backend/.venv`), Node 24.21.0. **No Docker, no Postgres+PostGIS+TimescaleDB on :5434, no Redis on :6379, no Playwright browsers.** All DB/service/browser items remain BLOCKED locally; the `integration`-marked suite (258 tests) can only run in CI.

## Verified current state (not assumed)

| Area | Verified state | Source |
|---|---|---|
| Router aggregator | Restored; `app.main` imports; 122 routes; OpenAPI 115 ops, 0 dup IDs | audit fix ff33c0f |
| Backend tests | `pytest -m "not integration"` → 691 pass, 2 Redis-env fails, 2 skip | audit run |
| Weather persistence | **Dead fetch confirmed**: `aqi_ingestion._fetch_weather_async` GETs Open-Meteo hourly×3d for Pune+Mumbai every 900s and discards it; `weather_measurements` table exists (migration 007) with **no ORM model, no writer** | code read |
| ML evaluation | `app/ml/evaluation.py` + `model_evaluation.py` real walk-forward tooling exists, unit-tested (non-DB lane 100%); **real eval BLOCKED — no populated DB export** | audit |
| Serving skew | `FORECAST_ALIGN_FEATURES_TO_ORIGIN=False`; `test_week2_provenance_m4` passes | audit |
| Impact Ledger | `InterventionOutcome` model + analytics aggregation exist; **only writer is `seeder._seed_outcomes`** — no API path to record an outcome | code read |
| City Action Brief | Design-only (Week-2 report); no endpoint/UI | code search |
| Rate limiting | `RateLimitMiddleware` **fails open** on Redis outage for all endpoints | `middleware.py:110-113` |
| Login abuse | No per-account throttling/lockout on `/auth/login` | `auth.py`/`services/auth.py` read |
| WebSocket | Token authn only; **no per-city authz** — any user can subscribe to any city | `endpoints/websocket.py` |
| Frontend | 49/49 tests, tsc clean, eslint 0err/12warn, build PASS (next 15.5.27); `services.ts` + `FreshnessKpiCard`/`DataFreshnessIndicator` exist | audit |
| Deps | npm: 2 remaining (need next@16); pip: 178 vulns/17 pkgs incl. python-jose PYSEC-2025-185 (no fix) | audits |

## Ownership & work items (Week 3)

| ID | Item | Owner | Acceptance criteria | Status |
|---|---|---|---|---|
| W3-1 | Weather persistence writer | Vinyak | `WeatherMeasurement` ORM model matching migration 007 (city, lat/lng, temp °C, humidity %, wind km/h+dir, pressure, precip mm, weather_code, source, is_forecast, observed_at, fetched_at); idempotent upsert on `uq_weather_city_time_source`; scheduled task persists instead of discarding; provenance preserved | **DONE** — 8 mapper tests pass; DB round-trip BLOCKED |
| W3-2 | Rate-limit failure policy | Rohan | Auth-sensitive paths fail closed (503) on Redis outage; other paths get a bounded in-process fallback, not unlimited; tests | **DONE** — 24/24 W3 tests |
| W3-3 | Login throttling | Rohan | Per-email failure counter; lockout after N attempts; no account-existence leak; works with in-process fallback | **DONE** — tested non-DB |
| W3-4 | WebSocket city authorization | Rohan | Citizens restricted to own `user.city`; staff roles unrestricted; token still required; rejection → close 4403 | **DONE** — tested non-DB |
| W3-5 | Impact Ledger outcome API | Aryan | `POST /enforcement/{id}/outcome` RequireStaff (owns/accesses action); `delta_score` computed server-side; `confidence_score` explicit (kills silent 0.8); `verified_by=current_user`; `GET /enforcement/outcomes` RequireAnalyst paginated | **DONE** — 124 routes, contract-checked; DB tests BLOCKED |
| W3-6 | ML eval pipeline run | Bhuvan | Evaluation runs on labeled fixture/synthetic data only → machine-readable artifact; real-data eval explicitly BLOCKED | **DONE** — `ml-eval-fixture/out/walk_forward_results.json` |
| W3-7 | Frontend contract + states | Adwait | `services.ts` outcome calls; honest unavailable/stale states on touched surfaces; tests | **DONE** — client + `ImpactLedgerCard` (loading/empty/error/non-causal); tsc clean |
| W3-8 | Contract + KPI + security + integration docs | Aryan/all | api-contracts.md, data-quality-and-kpis.md, security-validation.md, integration-test-report.md | **DONE** |

### Final gate (post-changes): black/isort/ruff clean; W3 tests 24/24; contract 93 calls/0 errors; tsc clean. DB/Redis/browser lanes remain BLOCKED (see integration-test-report.md).

**Deferred by design (not silently dropped):** `next@16` major (Adwait decision), `python-jose`→PyJWT (Week 5, single import point `app/core/security.py`), stored-forecast `artifact_id` linkage (W5), community-feed contract (privacy spec), Impact Ledger frontend page (W5 vertical slice if time), real Twilio live test (credentials absent), next@16 upgrade.

## Integration order
1. Model+writer (isolated) → 2. Security middleware/auth (shared code, testable non-DB) → 3. Outcome API (touches enforcement router) → 4. Frontend services → 5. Eval artifact → 6. Docs + full gate rerun.
