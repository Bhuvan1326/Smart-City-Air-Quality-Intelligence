# Week 4 — Demo Script

Runs against `docker compose up` (Postgres+PostGIS+TimescaleDB, Redis, backend :8000, frontend :3000) + `python -m app.seed` demo users. Where a live service is absent, use the labeled fallback — never present fixture/cached data as live.

## 1. Startup & health (2 min)
- `docker compose up`; show backend `/health` + frontend login.
- Mention: 124 routes served; OpenAPI at `/docs` has 0 duplicate operation IDs (D-08).

## 2. Citizen journey (4 min)
- Login as `citizen@demo` → dashboard AQI cards with **DataFreshnessIndicator** badges (live ≤10min / recent ≤2h / stale / demo).
- Point out: a missing observation renders "Unavailable" — never silently "Live".
- File a civic report; show it's visible only to the owner + staff.
- Attempt `?city=Other` on the WS feed (dev tools) → connection closed 4403 (W3 fix, D-06).

## 3. Forecast (3 min)
- Forecast tab: model card shows version artifact `xgb_forecast_*.joblib` + sidecar `.meta.json` for new trainings.
- Honest statement: "metrics shown are from the labeled evaluation artifact; production accuracy evaluation is BLOCKED pending populated observation data." Show `docs/week-3/ml-eval-fixture/out/walk_forward_results.json` as the reproducible pipeline output.
- Failure case: toggle `FORECAST_MODEL_PATH` to a missing file → UI shows model-unavailable state, not a crash.

## 4. Staff journeys (5 min)
- Login as `officer@demo` → analytics page (RequireAnalyst): city KPIs, comparison chart, **Intervention outcomes** summary, **Impact Ledger** card (loading→list→delta labels "descriptive, not causal").
- Login as `inspector@demo` → enforcement actions; record an outcome on own action via API (`POST /enforcement/{id}/outcome`); attempt on a colleague's action → 404 (ownership).
- Admin: user management, demo-user policy statement (demo creds exist only under `ALLOW_DEMO_SEED`).

## 5. Controlled failure scenario (2 min)
- `docker compose stop redis` → POST `/auth/login` still bounded (throttle + fallback limiter; auth paths 503 when the limiter itself is required) — narrate the fail-closed-vs-bounded policy (D-04/D-05).
- `docker compose start redis` → recovery without restart.

## 6. Close (1 min)
- KPI slide: freshness semantics, provenance `source` per reading, outcome deltas labeled descriptive.
- Known-limitations card: see `known-limitations.md`.

**Fallback:** if live ingestion can't run, use seeded demo data — the UI already flags `is_synthetic` readings as "Demo data".
