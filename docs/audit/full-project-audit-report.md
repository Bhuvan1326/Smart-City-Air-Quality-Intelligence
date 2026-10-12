# Full Project Audit — Week 1 + Week 2

**Project:** Smart City Air Quality Intelligence Platform
**Repository:** `Bhuvan1326/Smart-City-Air-Quality-Intelligence` (branch `main`, HEAD `3d0c88b`)
**Audit type:** Evidence-based verification + bug hunt + quality gate
**Environment:** Windows, Python 3.12.10 (`backend/.venv`), Node 24.21.0 / npm 11.19.0
**Constraint:** No Docker, no PostGIS/TimescaleDB, no Redis, no browser binaries on this machine — all DB/service/browser checks are classified BLOCKED, never assumed.

---

## 1. Executive Summary

**Overall verdict: `PASS WITH BLOCKERS`**

The repository is in substantially better shape than its own completion reports suggested in one respect (several "unverified" claims hold up at source level), and dramatically worse in another — **the application could not even import** until this audit restored the deleted API router aggregator (commit `3d0c88b` had emptied it, and every prior "passing" test report that postdates it is therefore suspect or was run before that commit).

| Metric | Count |
|---|---|
| Backlog items verified PASS (implementation + tests/source evidence) | 16 |
| PARTIAL (real implementation, but acceptance criteria only partially met or runtime-unverifiable) | 3 |
| FAIL | 0 |
| BLOCKED (environment or missing resource/decision) | 4 |
| NOT IMPLEMENTED | 5 |
| Newly discovered bugs | 6 |
| Bugs fixed + regression-verified | 5 |
| Bugs documented, not fixed (by design/environment) | 1 (plus user-edit repair) |

### Newly discovered bugs (all fixed in this audit)

| ID | Sev | Defect | Status |
|---|---|---|---|
| AUD-001 | P0 | `app.api.v1` package `__init__.py` empty → `api_router` import fails → **app cannot start** | FIXED |
| AUD-002 | P1 | `extractErrorMessage` imported by 6 modules but not exported from `lib/utils.ts` → `tsc` fails | FIXED |
| AUD-003 | P2 | `test_traffic_provider.py` POSIX-only path assumption + missing `Path` import → fails on Windows | FIXED |
| AUD-004 | P2 | `twilio` lazily imported by `twilio_service.py` but undeclared in requirements/pyproject | FIXED (pinned `9.10.9`) |
| AUD-005 | P3 | Duplicate OpenAPI operation ID (GET+POST on one `api_route`) | FIXED |
| AUD-006 | P3 | Redis-dependent tests lack `integration` marker → fail in documented non-DB lane | Documented (env-blocked, semantics per `pytest.ini` are Postgres-specific) |

Additionally: a mid-edit syntax break in `frontend/lib/utils.ts` (dangling comment fragment + duplicate `AQI_BANDS`/`AQIBand` exports) was repaired while preserving the editor's new `AQI_MAX` constant.

### Critical outstanding risks

1. **Critical dependency advisories partially remediated.** `next` bumped `15.5.20 → 15.5.27` (semver-safe) resolving its own critical advisories including unauthenticated RCE on Windows hosts; **2 advisories remain** (postcss ≤8.5.22 bundled inside next — requires the `next@16` major bump; 1 moderate). Python: **178 known vulnerabilities in 17 packages** — most with fixes, but `python-jose` PYSEC-2025-185 (algorithm confusion), `chromadb`, and `ecdsa` have **no fix version**.
2. **No database verification was possible.** 258 integration tests, Alembic upgrade verification, schema-drift live run, and the 80% coverage gate all require PostgreSQL+PostGIS+TimescaleDB at `localhost:5434`. Native Postgres 18 exists on 5432 but lacks the extension files; Docker and WSL are unusable. **The full-suite claim of any prior report cannot be reproduced here.**
3. **No real ML evaluation exists.** There is no ≥90-day real export; `weather_measurements` is a **dead table** (migration exists, zero writers/models) — the historical-weather dependency for training is unimplemented. Any MAE/RMSE would be fabricated; none is reported.
4. **Open security items remain open by design so far:** S9 (rate limiter fails open when Redis is down; no per-account lockout), S10 (WebSocket authenticates but does not authorize city), N2 (cross-user notification ops return 403, confirming ID existence).
5. **Impact Ledger / City Action Brief is still design-only** — `InterventionOutcome` is written only by the seeder.

---

## 2. Acceptance Matrix

Legend for the Evidence column: `CODE` = verified at source, `TEST` = test authored and passes where runnable, `RUN` = verified by actual execution, `DB` = requires database (blocked here).

| # | Item | Owner | Acceptance criteria | Evidence | Status |
|---|---|---|---|---|---|
| W1-S1 | Civic-report ownership scoping | Rohan | Citizen sees only own reports; `only_mine=false` cannot widen; 401/403 correct | `civic.py` scopes `reporter_id == current_user.id` for citizens server-side; `test_week1_rbac_regression.py` has dedicated negative tests (`only_mine=false`, cross-citizen GET → 403) — DB run blocked | PASS (runtime: DB) |
| W1-S2 | Drone flight-plan authorization | Rohan | Citizens cannot create/read/update staff-only plans | All drone routes use `RequireStaff` (admin/officer/inspector); `RequireInspectorOnly` on inspector routes; regression tests exist — DB run blocked | PASS (runtime: DB) |
| W1-S3 / W2-B1 | Demo credentials hardening | Rohan | No published passwords; `DEMO_USER_PASSWORD` env required; production seeding off; strong-password validation; correct handling of unset/empty | `seeder.py` verified; no `X@123` literals in seeder/docs (tests assert absence); non-DB demo-seeding tests pass (34-passed run) | PASS |
| W1-S4 | `/metrics` protection + docs exposure | Rohan | Token-gated metrics; prod `/docs`/openapi disabled; health redacts internals | `metrics.py`/`main.py` verified — `ENABLE_API_DOCS` gate, health error redaction | PASS |
| W1-S5 | Frontend/backend role alignment | Adwait/Rohan | Module visibility matches backend policy; direct-URL guard | `role-policy.ts` mirrors `RequireAnalyst`; `module-access.ts` route guard redirects; unit tests pass | PASS |
| W1-D1 | Future/observed timestamp handling | Vinyak | Provider `observed_at` used, not ingestion time; future-dated readings handled | `aqi_ingestion.py` + `openaq.py` verified; freshness flags stale/future | PASS |
| W1-M1–M3 | ML training defects (cross-ward target, shuffled split) | Bhuvan | Per-ward chronological targets; temporal split; no leakage | `forecast.py` retrain path verified; `test_week1_data_ml.py` passes | PASS |
| W2-B3/S6 | Twilio IVR signature validation | Rohan | Official algorithm or equivalent; fail-closed 403; GET+POST; no forwarded-host bypass | `twilio_signature.py` stdlib HMAC-SHA1; fails closed on missing token/URL/header/mismatch; **`test_matches_official_twilio_sdk_algorithm` passes against the real `twilio` SDK** (installed during this audit); DB endpoint tests blocked | PASS |
| W2-B4 | Notification ownership | Rohan | Users cannot read/dismiss others' notifications | All operations filter `user_id == current_user.id` | PASS |
| W2-S7 | Evidence-media authorization | Rohan | No public static path; signed links; owner/staff access; traversal-safe | `media_links` router + `evidence_storage` verified — no static mount, signed expiry, path-sanitized | PASS (runtime: DB) |
| W2-S8 | Production docs/health hardening | Rohan | Docs disabled in prod; health leaks nothing | Config + endpoints verified | PASS |
| W2-S11/S12 | RBAC dep renames + stale comments | Rohan | Correct role sets; accurate comments | `deps.py` verified: `RequireStaff`/`RequireAnalyst`/`RequireInspectorOnly` correct | PASS |
| W2-D1/D3/D4 | Units normalization, CO mg/m³, invalid-value handling | Vinyak | Explicit unit validation; zero ≠ missing; invalid ≠ AQI 500 | `units.py`/ingestion boundary verified; `test_week2_data_correctness.py` passes (non-DB) | PASS |
| W2-D2/K1 | Freshness KPI (backend + dashboard) | Vinyak/Adwait | Documented thresholds; synthetic excluded; shared definition | `kpi` router + `openaq_freshness` verified; `FreshnessKpiCard.tsx` + `DataFreshnessIndicator.tsx` exist | PASS (runtime: DB) |
| W2-A-tool | API contract drift checker | Aryan | Fails on drift, passes when aligned; CI step | `contract:check` → 91 calls, 1193 fields, 0 errors; deliberate-drift fixture test proves exit-1 on mismatch (runs inside `npm test`) | PASS |
| W2-A-tool | Migration-vs-ORM drift checker | Aryan | Detects new drift; baseline tracked | Tool + unit tests pass; baseline = **124 signatures** (matches documented); live run BLOCKED (needs migrated DB) | PARTIAL |
| W2-M4 | Serving-skew flag + feature alignment | Bhuvan | `FORECAST_ALIGN_FEATURES_TO_ORIGIN` exists, off by default, both paths tested | Config flag `False`; `test_week2_provenance_m4.py` passes 100% non-DB | PARTIAL (real-data comparison pending by design) |
| W2-M5/M6 | Model metadata sidecar + forecast `source`/`model_artifact` provenance | Bhuvan | `.meta.json` on new training; API labels model vs fallback | `metadata_path_for`/`build_model_metadata` + endpoint fields verified; tests pass. Existing 9 artifacts predate tooling → **no sidecars** (per "no retrain" constraint) | PASS (with caveat) |
| W2-EVAL | Evaluation harness + baselines | Bhuvan/Vinyak | Chronological/walk-forward eval vs persistence/seasonal-naive; real MAE/RMSE | `evaluation.py` + `model_evaluation` tests pass (tooling verified); **real-data eval BLOCKED — no dataset** | BLOCKED (partial: tooling PASS) |
| W2-EXP | ≥90-day hourly ward AQI + weather export with gap report | Vinyak | Reproducible export from DB | `dataset.py` export tooling + tests pass; **real export BLOCKED** — no populated DB, weather never persisted | BLOCKED (partial: tooling PASS) |
| W2-WX | Weather persistence decision | Vinyak/Bhuvan | Persist weather OR drop weather features | `weather_measurements` table exists (migration 007) but **no ORM model, no writer** → undecided/unimplemented | BLOCKED (decision required) |
| W2-C1 | Playwright four-role walkthrough + page states | Adwait | Spec runs against live stack; role routing verified in browser | `e2e/role-walkthrough.spec.ts` authored, config correct; **BLOCKED** — no browser binaries, requires running frontend+backend+DB+seeded users | BLOCKED |
| W2-G | Impact Ledger / City Action Brief | Vinyak | Store forecast-at-issue, interventions, before/after outcomes; non-causal labeling | `InterventionOutcome` model exists; written **only by seeder**; analytics endpoint aggregates deltas; `confidence_score` default 0.8 still present | NOT IMPLEMENTED |
| — | Community-wide citizen feed | — | Privacy-preserving public civic feed | Contract decision still pending; citizens get own reports only (correct interim state) | NOT IMPLEMENTED |
| — | S9: login lockout + fail-closed rate limit | Rohan | Per-account lockout; rate limiter fails closed | `RateLimitMiddleware` **fails open** on Redis outage (documented in code); no lockout counter on `/auth/login` | NOT IMPLEMENTED |
| — | S10: WebSocket city authorization | Rohan | User authorized for requested city | Token validated (access-type, active user); **no city check** — any user, any city | NOT IMPLEMENTED |
| — | N2: 403-vs-404 for cross-user objects | Rohan | Avoid ID-existence confirmation | Notification ops return 403 (documented contract); flags enumeration nuance | PARTIAL |
| — | Forecast `artifact_id` on stored rows | Bhuvan | Stored forecasts record artifact used | `model_artifact` returned in API response; stored-row linkage not found | NOT IMPLEMENTED (Week-3 backlog) |

---

## 3. Quality-Gate Results

Full table: [`quality-gate-results.md`](./quality-gate-results.md). Headline rows:

| Check | Result | Evidence |
|---|---|---|
| Backend tests (non-integration lane, `-m "not integration"`) | **691 passed, 2 failed (env), 2 skipped, 258 deselected** | 3:32 run; both failures = Redis `localhost:6379` refused (no server) |
| Backend tests (full, 953 collected) | **BLOCKED** | 258 integration tests need Postgres+PostGIS+TimescaleDB at `:5434`; none available |
| Coverage gate (80%) | **NOT ASSESSABLE locally** | Non-DB lane reaches 70.51%; full measurement requires the DB suite |
| Black / isort / Ruff / compileall | **PASS** | 269 files unchanged / exit 0 / 0 findings / OK |
| Frontend tests | **PASS — 49/49** | `npm test`, incl. deliberate-drift contract fixture |
| TypeScript | **PASS** (after AUD-002 fix + edit repair) | `tsc --noEmit` exit 0 |
| ESLint | **0 errors, 12 warnings** | unused vars/directives + 1 hook-dep warning — pre-existing |
| `next build` | **PASS** | next 15.5.27, 47 routes |
| API contract drift | **PASS** | 91 calls / 1193 fields / 0 errors / 0 warnings |
| Migration/ORM drift | **BLOCKED (live)** | tool + baseline verified; needs migrated DB |
| Playwright | **BLOCKED** | no browsers; needs running stack |
| GitHub Actions | **NOT VERIFIED** | workflow inspected (Timescale svc, migration, drift, contract, coverage steps present); no remote-run evidence |
| pip-audit | **178 vulns / 17 pkgs** | see findings report |
| npm audit | **8 → 2** after `npm audit fix` | remaining need `next@16` major |

---

## 4. Bug Register

Full detail: [`findings-and-remediation.md`](./findings-and-remediation.md).

**Fixed this audit:** AUD-001 (P0, app unstartable), AUD-002 (P1, tsc failure), AUD-003 (P2, Windows test), AUD-004 (P2, missing twilio dep), AUD-005 (P3, OpenAPI dup op-id).
**Documented, not modified:** AUD-006 (P3, unmarked Redis tests), N2 403-enumeration nuance, OpenAPI `1 untyped call` (contract checker allowance).

---

## 5. ML & Data-Validation Results

- **Dataset provenance:** No real ≥90-day export exists. `backend/ml_models/` contains 9 XGBoost artifacts (Aug–Sep 2026 timestamps) trained before the Week-2 metadata tooling — **none has a `.meta.json` sidecar**, so their provenance cannot be reconstructed. New trainings will produce sidecars (`build_model_metadata` verified).
- **Weather features:** `weather_measurements` table exists via migration 007 but has **no ORM model and no writer** — historical weather cannot be sourced for training. The documented decision (persist vs. drop features) is **still required**.
- **Leakage/splitting:** Per-ward chronological target construction and temporal split verified in `forecast.py`; serving feature alignment gated by `FORECAST_ALIGN_FEATURES_TO_ORIGIN=False` (off per decision).
- **Metrics:** **None reported — none measured.** Evaluation harness verified as tooling only.

## 6. Outstanding Blockers & Decisions

| # | Blocker | Needs | Owner |
|---|---|---|---|
| B-1 | Full DB suite (258 tests), migrations, drift, coverage gate | PostgreSQL 15/16 + PostGIS + TimescaleDB at `:5434` (docker-compose `db`) or CI | Infra / Aryan |
| B-2 | Redis-dependent tests + rate-limit verification | Redis at `:6379` | Infra |
| B-3 | Playwright walkthrough | `npx playwright install`, running FE+BE+DB, `E2E_DEMO_PASSWORD` | Adwait |
| B-4 | ≥90-day real export + walk-forward eval | Populated DB + weather persistence decision | Vinyak/Bhuvan |
| D-1 | Weather strategy | Decision: persist Open-Meteo history (writer + model) or drop weather features | Vinyak/Bhuvan |
| D-2 | `next@16` upgrade for remaining npm vulns | Compatibility pass on App Router usage | Adwait |
| D-3 | `python-jose` PYSEC-2025-185 | Migrate to PyJWT or documented risk acceptance | Rohan |
| D-4 | Community feed contract | Privacy-preserving spec | Product/Rohan |
| D-5 | S9/S10 | Design for lockout + city-scoped WS authz | Rohan |

## 7. Changed Files (all uncommitted; user work preserved)

| File | Change |
|---|---|
| `backend/app/api/v1/__init__.py` | Restored full router aggregator (AUD-001) |
| `backend/app/api/v1/endpoints/notifications.py` | Split IVR webhook GET/POST (AUD-005) |
| `backend/app/tests/test_traffic_provider.py` | Windows-safe path + `Path` import (AUD-003); user's docstring edit kept |
| `backend/app/tests/test_week2_demo_seeding.py` | Cross-platform regex fix |
| `backend/requirements.txt`, `backend/pyproject.toml` | `twilio==9.10.9` (AUD-004) |
| `frontend/lib/utils.ts` | Added `extractErrorMessage` (AUD-002); repaired mid-edit duplication; kept `AQI_MAX` |
| `frontend/package-lock.json` | `npm audit fix` — next 15.5.27 + axios/sharp/nanoid/playwright bumps |
| `openapi.json` (new, untracked) | Regenerated API spec for contract checker |
| Pre-existing (not mine): `.claude/settings.json` deleted; `frontend/tsconfig.tsbuildinfo` modified |

Nothing was committed, pushed, or deployed.

## 8. Reproducibility

```bash
# Backend — requires Python 3.12, services per docker-compose (Postgres+PostGIS+TimescaleDB on :5434, Redis on :6379)
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt
python -m compileall -q app
python -m black --check app && python -m isort --check-only app && python -m ruff check app
pytest -m "not integration"          # no-service lane
pytest                                # full suite (needs DB+Redis)
python -m app.tools.dump_openapi > ../openapi.json
python -m app.tools.schema_drift --database-url postgresql+asyncpg://airuser:airpass@localhost:5434/airquality_test
alembic upgrade head                  # against TEST_DATABASE_URL
python -m pip_audit                   # dependency advisories

# Frontend — requires Node/npm
cd frontend && npm ci
npm test                              # 49 unit tests
npx tsc --noEmit && npx eslint . && npm run build
npm run contract:check                # uses ../openapi.json
npx playwright install && E2E_DEMO_PASSWORD=*** npx playwright test   # needs running stack
npm audit                             # dependency advisories
```
