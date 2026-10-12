# Week 4 — Known Limitations

## Data & ML
1. **No production forecast-accuracy claim exists.** The walk-forward pipeline runs and produced metrics on a *labeled synthetic fixture* only. Real evaluation is BLOCKED until ≥35 days of ingested AQI+weather observations exist. Any number quoted from `walk_forward_results.json` describes pipeline execution, not model quality.
2. **`FORECAST_ALIGN_FEATURES_TO_ORIGIN=False`** — a documented training/serving feature-order skew flag; the aligned variant is measurable but not enabled.
3. Existing `xgb_forecast_*.joblib` artifacts (9 files) predate sidecar metadata — version/feature provenance only exists for *new* trainings.
4. **Impact Ledger deltas are descriptive** before/after comparisons — no causal design; `carbon_saved_kg` is a self-reported estimate field.

## Infrastructure
5. Local env has **no Postgres/PostGIS/TimescaleDB, Redis, Docker, or Playwright browsers** — 258 `integration` tests, live schema-drift, E2E, and live persistence proofs are BLOCKED and must run in CI.
6. **Coverage gate (80%) unverifiable locally** — non-integration lane measured 70.51%; the gate is only meaningful on the full suite with services.
7. Rate-limit Redis outage fallback is **per-process** — bounded (30 rpm/IP default) but N replicas multiply the cap; documented design decision.

## Security
8. `python-jose` PYSEC-2025-185 unfixed upstream — PyJWT migration scheduled W5; interim exposure documented (tokens are HS256-signed server-side; the advisory concerns algorithm-confusion paths not used).
9. 178 pip-audit findings across 17 packages untriaged; 2 npm findings need breaking `next@16` — owner decisions required.
10. Demo users exist only under `ALLOW_DEMO_SEED`; production startup creates no default credentials.

## Features
11. **City Action Brief** is design-only — no endpoint or UI (not silently claimed in the demo).
12. Twilio IVR signature logic verified; **live Twilio verification never executed** (no credentials).
13. Frontend role-policy mirrors backend roles for UX only — the backend is the authorization boundary.
