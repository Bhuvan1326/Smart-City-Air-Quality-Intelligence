# Week 4 — Demo Checklist

## Environment
- [ ] `docker compose up -d` healthy: db (Postgres+PostGIS+Timescale), redis, backend, frontend
- [ ] `alembic upgrade head` applied; `python -m app.seed` with `ALLOW_DEMO_SEED=true`
- [ ] Demo users exist: `citizen@demo`, `officer@demo`, `inspector@demo`, `admin@demo`
- [ ] No real secrets/credentials anywhere in env files or fixtures

## Pre-flight checks
- [ ] `curl :8000/health` 200; `curl :8000/docs` loads; 0 dup operation IDs
- [ ] `npm test` 49/49; `npm run contract:check` 0 errors
- [ ] `pytest -m "not integration"` green; `pytest -m integration` green on the compose stack
- [ ] Playwright: `npx playwright install` done; `e2e/role-walkthrough.spec.ts` green
- [ ] Fresh AQI+weather rows in DB (check `observed_at` within live window) **or** demo fallback explicitly labeled

## During demo
- [ ] Freshness badges visible and accurate (never "Live" for missing/stale)
- [ ] Forecast shows model metadata + honest accuracy framing
- [ ] Role navigation correct for all 4 roles; WS cross-city rejection shown
- [ ] Impact Ledger card loads with non-causal labeling
- [ ] Redis-outage scenario rehearsed (stop → bounded/503 → start → recovery)
- [ ] No personal data, tokens, or internal tracebacks visible on screen

## Evidence to capture
- [ ] Screenshot: dashboard freshness badges, analytics+Impact Ledger, forecast metadata
- [ ] Terminal capture: contract check, test summaries, `walk_forward_results.json` head
- [ ] `docker compose ps` + `/health` output
