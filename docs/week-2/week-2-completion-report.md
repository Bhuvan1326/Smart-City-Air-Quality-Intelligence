# Week 2 Completion Report

**Verdict: Week 2 is PARTIALLY complete.** All security P1 items, the three data-correctness fixes, the contract-drift check, provenance/metadata and the freshness KPI backend are implemented and tested. The two items the plan treats as the foundation for evidence — **the 90-day real-data export and the retrain/walk-forward evaluation — are BLOCKED** (no real data in this environment, and weather is not stored). **No model metric exists and none is claimed.** Browser tests were written but **could not be run**. The Impact Ledger / City Action Brief is **design only**.

## 1. Executive summary
| | Count |
|---|---|
| Backlog items complete | 9 (B1, B2, B3, B4, B5, C3, D2, A2, F2*) |
| Partial | 7 (A1, A3, C1, C2, D3, E1, F1) |
| Blocked | 2 (D1 export, E2 evaluation results) |
| Design only, not implemented | 1 (G) |
| **Total backlog items** | 19 |
\*F2 complete for newly trained artifacts only (see section 9).

New findings this week: weather is never persisted (blocks training); `pm25 == 0` produced AQI 500; the login page shipped all demo passwords in the browser bundle; a successful model prediction was discarded when feature importance failed; IVR webhook was GET-only while Twilio defaults to POST; `twilio` is not in `requirements.txt`; CI already had Timescale (correcting Week 1).

## 2. Starting-state verification
See `starting-state-report.md`. Week 1 code/docs verified present; 23 Week 1 tests re-run (23 pass). Week 1's "10 Timescale failures" were sandbox-specific: CI already provisions TimescaleDB.

## 3. Work by member (all performed in this single session)
- **Aryan:** decisions doc (`decisions-and-contracts.md`), contract-drift checker + CI, migrations/drift CI, ledger/brief design.
- **Rohan:** B1-B5 + S8; `security-findings-status.md`.
- **Adwait:** forecast states + provenance labels, KPI card, role-walkthrough spec (unrun), contract alignment.
- **Bhuvan:** export consumers, evaluation harness, M4 flag, metadata sidecar, `source` field.
- **Vinyak:** D1/D3/D4 fixes, dataset export + gap report tooling, K1 KPI endpoint.

## 4. Files changed
**Modified:** `.github/workflows/ci.yml`, `.env.example`, `README.md`, `docker-compose.yml` (env passthrough only), `backend/app/{main.py, core/{config,seeder}.py, api/{deps.py,v1/__init__.py, v1/endpoints/{drone,forecast,notifications,...}.py}, ml/inference.py, schemas/enforcement.py, services/{data_freshness,aqi_providers/openaq,notifications/dispatcher}.py, workers/tasks/{aqi_ingestion,forecast}.py}`, existing tests `test_seeder.py`, `test_openaq_freshness.py` (fixtures made realistic), frontend `login/page.tsx`, `forecast/page.tsx`, `transparency/page.tsx`, `lib/api/services.ts`, `package.json`(+lock), regenerated `docs/week-1/{rbac-permission-matrix,api-contracts}.md`.
**Created:** backend `app/api/media.py`, `app/api/v1/endpoints/{media_links,kpi}.py`, `app/ml/{dataset,evaluation,provenance}.py`, `app/schemas/kpi.py`, `app/services/{media_access,kpi_freshness}.py`, `app/services/aqi_providers/units.py`, `app/services/notifications/twilio_signature.py`, `app/tools/{dump_openapi,schema_drift}.py`, `schema_drift_baseline.json`, 10 `test_week2_*.py` files; frontend `lib/{forecast-state,role-policy}.ts`, `scripts/contract-check.mjs`, `contract-exceptions.json`, `playwright.config.ts`, `e2e/role-walkthrough.spec.ts`, `transparency/FreshnessKpiCard.tsx`, 3 test files + fixtures; `docs/week-2/*`.

## 5. Security (evidence)
| Item | Result | Tests |
|---|---|---|
| B1 demo credentials | No static password anywhere in source/README/env/frontend; seeding needs `DEMO_USER_PASSWORD`; production off by default | `test_week2_demo_seeding.py` (15), updated `test_seeder.py` |
| B2 IVR signature | unsigned/invalid -> 403, valid GET and POST -> 200, tampered params -> 403, fail-closed; algorithm cross-checked against the official Twilio SDK | `test_week2_ivr_signature.py` (9). **No real Twilio call was made.** |
| B3 media | unauth 401; owner/staff 200; non-owner 404; traversal rejected; signed link tamper/other-file/expired -> 403 | `test_week2_media_access.py` (6) |
| B4 notifications | cross-user read/dismiss blocked; owner works; unauthenticated rejected | `test_week2_notification_ownership.py` (5) |
| B5 renames | route/role table of all 121 entries identical before/after | snapshot diff |
Open: S9, S10, N1, N2 (`security-findings-status.md`).

## 6. Data export and gap report
**Not produced (blocked).** No real data/credentials. Tooling is verified (`app/ml/dataset.py`, 5 tests). Blocking finding: weather is not persisted, so even a 90-day live export has no usable weather columns. See `data-and-evaluation-status.md`.

## 7. D1 / D3 / D4
Payloads are **built from the documented OpenAQ v3 schema, not captured from the live API**. 22 tests (`test_week2_data_correctness.py`): observation-time stamping + same-observation dedupe (integration, fails on original code), unit conversion (ug/m3, mg/m3, ppb, ppm; CO to mg/m3), rejection of unknown/missing gas units, plausibility limits, rejected pollutants cannot make a station look fresher, no-valid-pollutant -> `None` (not 500), `pm25 == 0` -> 0 (was 500), stale flag preserved. Tests for D1/D4 were shown to fail on the original code. **Live-provider behaviour remains unverified.**

## 8. Forecast evaluation
**No metrics.** Harness verified on synthetic fixtures (`app/ml/evaluation.py`, 8 tests + A/B test). Empty metrics table and blockers in `data-and-evaluation-status.md`. M1-M3 verified present and tested.

## 9. M4 flag and provenance
`FORECAST_ALIGN_FEATURES_TO_ORIGIN` implemented, **default off**; mismatch reproduced by tests; real-data A/B pending. `source` (3 allowed values, derived by one shared function) and `model_artifact` added to forecast responses; sidecar `<artifact>.meta.json` written at training and loaded by the registry. 13 tests. Limits: the 9 existing artifacts have no sidecar; stored forecasts do not record the artifact (needs migration).

## 10. Frontend / browser coverage
Forecast page: loading, error (403/5xx/network, retry), empty, stale banner, source label — covered by 3 pure-helper test groups; **no component or browser test executes the page**. Alert screens: **not done**. `e2e/role-walkthrough.spec.ts` (4 roles x 5 routes + API-bypass + session-switch) is **written but NOT executed** (Playwright browser download is blocked here). Role behaviour is therefore still verified only by backend tests + unit tests.

## 11. Contract drift and CI
`scripts/contract-check.mjs` (TypeScript AST, offline): 91 calls, 1,193 fields, **0 errors**; fixtures prove aligned = exit 0 and 5 kinds of deliberate drift = exit 1 (`contract-check.test.mjs`). One real finding fixed (`register` type). CI (`ci.yml`) now: applies migrations to a fresh Timescale DB, runs the drift check, dumps OpenAPI, runs frontend unit tests and the contract check. **The workflow parses but has never run on GitHub.** `alembic upgrade head` succeeds locally (PostGIS, no Timescale). `alembic check` found **124 pre-existing migration-vs-ORM differences** (46 nullable, 62 index, 8 columns, 4 migration-only tables, 4 constraints); they are recorded in `schema_drift_baseline.json`; CI fails on new or stale entries. This is a cleanup backlog, not an accepted state. **The 10 Timescale-dependent tests were NOT re-run in a Timescale environment.**

## 12. Impact Ledger / City Action Brief
Design only (`impact-ledger-and-action-brief-contract.md`). Existing `intervention_outcomes` has no writer and a default confidence of 0.8; analytics presents its delta as improvement — treat as descriptive.

## 13. Exact commands and results
Environment: Python 3.12 venv (no `crewai`/`weasyprint`), local PostgreSQL 16 + PostGIS + Redis, **no TimescaleDB**, Node 22.

| Command | Result |
|---|---|
| `pytest` full (Week 2 end) | **940 passed, 13 failed** (953 collected; Week 1 was 861) |
| diff of failure sets vs Week 1 | the same 10 `time_bucket` failures + 3 in `test_seeder.py` caused by the B1 change |
| `pytest test_seeder.py test_week2_demo_seeding.py` after updating the 3 tests | **32 passed**. The **full suite was not re-run** after this last edit; expected 943 passed / 10 failed, **unverified** |
| `black --check app/`, `isort --check-only`, `ruff check app/` | pass |
| `alembic upgrade head` (fresh DB) / `python -m app.tools.schema_drift` | success / current=124 baseline=124 new=0 stale=0 |
| `npm test` | **49/49 pass** (Week 1: 43) |
| `npx tsc --noEmit` | exit 0 |
| `npx eslint .` | 0 errors (12 warnings at last full count; all pre-existing categories) |
| `node scripts/contract-check.mjs --openapi ...` | 0 errors |
| Playwright / GitHub Actions | **not run** |

## 14. Open findings, blockers, risks
Blockers: no real data (D1/E2), weather not persisted (decision needed), no browser (C1), no Timescale locally, no provider credentials. Open: S9, S10, N1, N2, forecast alert states, D5 (instantaneous vs 24 h AQI averaging), migration/ORM drift (124), existing artifacts unvalidated, `forecast_grids` lacks artifact id, B1 decisions unconfirmed.

## 15. Week 3 backlog
| # | Task | Owner | Pri | Depends on | Acceptance criteria |
|---|---|---|---|---|---|
| 1 | Decide weather strategy (persist Open-Meteo history vs drop weather features) | Aryan | P0 | – | Written decision; if persisted: migration + ingestion with tests |
| 2 | Real export >= 90 days + gap report committed | Vinyak | P0 | credentials, 1 | `python -m app.ml.dataset` output with `meets_min_days` and weather coverage reported |
| 3 | Retrain + walk-forward evaluation; fill metrics table; decide flag M4 | Bhuvan | P0 | 1, 2 | Table with n, MAE, RMSE vs baselines; A/B result for the flag; flag decision recorded |
| 4 | Run Playwright walkthrough in CI/staging; fix failures | Adwait | P0 | demo users via `DEMO_USER_PASSWORD` | all 4 roles pass; results recorded |
| 5 | First real CI run: confirm the 10 Timescale tests, migration step, drift step, contract step | Aryan | P0 | – | Green run link; any env incompatibility documented |
| 6 | Burn down schema drift (124) | Aryan | P1 | 5 | Baseline shrinks; each removal tested |
| 7 | Alert-screen states + component tests | Adwait | P1 | – | loading/empty/403/unavailable/stale rendered and tested |
| 8 | S9 login lockout + fail-closed rate limiting; S10 WebSocket authz; N1 declare `twilio` dependency; N2 | Rohan | P1 | – | tests per item |
| 9 | Live-provider verification of D1/D3 (units, timestamps) with real payload captures | Vinyak | P1 | credentials | captured fixtures replace constructed ones |
| 10 | Record artifact id on forecasts (migration) and `source` in cached rows | Aryan + Bhuvan | P1 | 3 | stored forecasts expose `model_artifact` |
| 11 | Impact Ledger + Action Brief implementation per design | Aryan + all | P2 | 3, 9, product decisions | descriptive-only labelling; server-side authz; provenance retained |
| 12 | Citizen community-feed decision and implementation (if chosen) | Aryan/Rohan/Adwait | P2 | product | redaction tests |
| 13 | Remove default `confidence_score` 0.8; relabel analytics improvement as descriptive | Bhuvan/Aryan | P2 | – | schema + UI change with tests |
