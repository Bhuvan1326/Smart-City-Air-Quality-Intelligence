# Changelog

All notable changes follow [Conventional Commits](https://www.conventionalcommits.org/).

## [1.1.0] — 2026-07-05

### feat: production completion milestone — real dispersion modelling, digital twin expansion, LangGraph + CrewAI, offline PWA, and critical bug fixes

This release closes out the platform's remaining production-readiness gaps
identified in a full codebase audit. Every new integration that requires an
external API key is gated behind a config check and degrades gracefully
when unconfigured — the platform runs completely on **zero paid API keys**.
Free-tier services used: NASA FIRMS (free forever), Copernicus Data Space
Ecosystem / Sentinel Hub (free forever, EU-run), Firebase Cloud Messaging
(free forever), and SMTP email (free at this volume via Brevo/Gmail).
Twilio SMS/IVR is fully implemented but **off by default**
(`TWILIO_ENABLED=false`) since real SMS/voice delivery is never free beyond
a one-time trial credit.

**Critical bug fixes** (all pre-existing, found via end-to-end testing against a live database, not just static review)
- fix(agents)!: `AgentOutput.execution_time_ms` had no default, but every
  agent's own `execute()` constructed `AgentOutput(...)` without it — this
  meant **every one of the 6 core AI agents failed on every invocation**,
  in both the original orchestrator and the new one, undetected because no
  test ever exercised a full agent run against real data
- fix(agents): Citizen Advisory Agent claimed to filter alerts to "next 12
  hours" but never applied any time filter — was alerting on AQI breaches
  predicted up to 3 days out and labeling them as imminent
- fix(simulator): what-if simulator's ward-scoped source-attribution query
  reused a WHERE clause built for a different (joined) query — every
  ward-scoped simulation silently queried the wrong data
- fix(forecast): the trained XGBoost model was trained, saved to the
  registry, and loaded — but never actually called for a prediction;
  forecasts were always pure statistical regardless of whether a trained
  model existed
- fix(frontend): `@radix-ui/react-badge` — a package that doesn't exist —
  was listed as a dependency, making `npm install` fail from a clean
  checkout; nothing in the codebase imported it
- fix(frontend): no ESLint flat config existed at all despite a `lint`
  script referencing one — `npm run lint` had never actually run
  (42 issues found once enabled, all fixed)
- fix(frontend): critical CVE in `next@15.1.3`, patched to `15.5.20`
- fix(security): refresh tokens had no rotation or reuse detection
- fix(testing): pytest-asyncio was missing `asyncio_default_test_loop_scope`
  (only `asyncio_default_fixture_loop_scope` was set), so session-scoped
  fixtures and each test's own coroutine ran on different event loops —
  this, combined with the test `client` fixture sharing one `AsyncSession`
  across the test and the app's `BaseHTTPMiddleware`-spawned request task,
  broke every database-backed test in the original suite (`asyncpg`
  "attached to a different loop" / "another operation is in progress").
  Fixed by (1) setting the missing pytest-asyncio option, (2) giving the
  app real independent pooled connections per request instead of sharing
  one connection/session with the test (avoiding a separate anyio
  `TaskGroup` + asyncpg incompatibility), and (3) replicating the real
  `get_db` dependency's commit-after-yield behavior in the test override,
  which it was silently missing. All 82 pre-existing tests plus every test
  added in this release now pass (90 total)
- fix(enforcement): `notes` is a real, persisted, PATCH-updatable column
  on `EnforcementAction` but was missing from `EnforcementActionResponse`
  — silently dropped from every API response

**AI / Agents**
- feat(agents): real `langgraph.graph.StateGraph` orchestrator
  (`LangGraphOrchestrator`, exposed at `POST /agents/run-graph`) — the
  original `AirQualityOrchestrator` was hand-rolled sequential/parallel
  async code despite `langgraph` being a listed dependency; the new
  orchestrator is additive, the original is unchanged and still the
  default at `POST /agents/run`
- feat(agents): CrewAI Investigation Crew — a genuine multi-agent,
  autonomous sub-task (Field Investigator + Evidence Verifier agents,
  sequential process, shared memory) that corroborates low-confidence
  Attribution Agent findings against satellite evidence, citizen alert
  history, enforcement history, and sensor health, then propagates a
  confidence adjustment back into the graph state
- feat(dispersion): real atmospheric dispersion module — Pasquill-Gifford
  stability classification from actual wind speed/time-of-day, Gaussian
  plume equation with Briggs urban dispersion coefficients, PM2.5 vs PM10
  differentiated via real settling-velocity physics; replaces the previous
  hardcoded-stability-class-C placeholder in both the Forecast Agent and
  the What-If Simulator's `/twin/dispersion` endpoint
- feat(simulator): digital twin scenarios expanded — `road_closure`,
  `traffic_diversion` (with genuine secondary-ward diversion effects),
  `weather_shift` (uses the real dispersion model), `policy_bundle`
  (multi-lever custom reductions); added `impact_score` and confidence
  intervals to every scenario
- feat(ml): explainable predictive sensor maintenance
  (`app.ml.sensor_maintenance`) — CUSUM drift detection, failure
  probability, remaining-useful-life estimate, confidence, feature
  importance, alternative explanations, historical comparison; replaces
  the previous inline heuristic

**Satellite / Drone / Notifications**
- feat(satellite): real pipeline via Copernicus Data Space Ecosystem
  (NDVI/NDBI) and NASA FIRMS (thermal hotspots, biomass burning
  classification), feeding real weight adjustments into the Pollution
  Attribution Agent
- feat(drone): inspection flight planning — lawnmower coverage paths,
  no-fly zone exclusion, battery-aware sortie splitting, GeoJSON export,
  automatic hotspot detection from high-confidence attribution findings
- feat(notifications): Firebase push (free) + SMTP email (free) fully
  wired and on by default; Twilio SMS/IVR fully implemented, off by
  default (see above)

**Security**
- feat(security): refresh token rotation with theft/reuse detection
  (Redis-backed, family revocation on replay)
- feat(security): secure headers middleware (CSP, HSTS, X-Frame-Options,
  Referrer-Policy, Permissions-Policy)
- feat(security): CSRF double-submit-cookie protection for any future
  cookie-based auth flows
- feat(security): input sanitization wired into enforcement/alert schemas
  (script-injection rejection, control-character stripping, length caps)

**PWA / Offline**
- feat(pwa): full offline inspection flow — service worker (cache-first
  static assets, network-first API with cache fallback), hand-rolled
  IndexedDB evidence queue (no new dependency), Background Sync API with
  an `online`-event fallback for Safari/iOS, client-side photo compression
- feat(evidence): idempotent evidence submission endpoint
  (`POST /enforcement/{id}/evidence`) keyed by a client-generated ID so a
  retried background-sync doesn't duplicate photos
- feat(pwa): generated the two icons `manifest.json` referenced but never
  had — installability was broken before this

**Database**
- feat(db): three new tables — `sensor_health_assessments`,
  `satellite_observations`, `drone_flight_plans` — migration verified
  against a real Postgres+PostGIS instance with zero schema drift
- feat(db): TimescaleDB continuous aggregate (`aqi_daily_by_station`),
  compression policy (7-day threshold), and retention policy (2-year
  default) — could not be executed against a real TimescaleDB instance in
  the environment this was built in (no network route to install the
  extension); DDL follows the documented API precisely and failed only on
  `time_bucket()` being absent, confirming it's syntactically correct, but
  treat it as needing a live-instance smoke test before relying on it

### Known remaining gaps (not fixed in this release)
- Test coverage is at 57% (`pytest --cov`), short of the 80% target — the
  original test suite's DB-backed tests were completely broken (see fix
  below) and are now fixed and passing, but the Celery task modules
  (`app/workers/tasks/*.py`) still have 0% pytest coverage. Every one of
  them was manually verified end-to-end against a live seeded database
  during this engagement (see the session's tool-call history), but that
  verification wasn't converted into a permanent pytest suite
- Full documentation regeneration (dedicated DATABASE.md/API.md/TESTING.md
  were referenced in the original spec but never created — FastAPI's
  auto-generated OpenAPI docs at `/docs` currently serve as the API
  reference)
- A deeper pre-existing test-fixture issue: sharing one `AsyncSession`
  across a test fixture and Starlette's `BaseHTTPMiddleware` task-spawning
  breaks under asyncpg's single-connection-transaction constraint, affecting
  the original auth/aqi/enforcement test files
- `W01` and `W07` share identical placeholder centroid coordinates across
  three files' ward-coordinate constants — flagged rather than silently
  replaced with invented GPS data
- AttributionAgent's own confidence score does not appear to vary with
  underlying ward data (returns the same value across wards) — not
  investigated further in this pass

## [1.0.0] — 2024-01-01

### feat: initial production release

**Backend**
- feat(auth): JWT authentication with RBAC (city_administrator, pollution_control_officer, field_inspector, citizen)
- feat(aqi): live AQI endpoint with Redis cache (5 min TTL); TimescaleDB history with time_bucket aggregation
- feat(forecast): ward-level 72h XGBoost forecasts with confidence intervals and feature importance
- feat(enforcement): full CRUD with AI reasoning traces, priority scoring, PDF export
- feat(attribution): hourly pollution source attribution per ward (vehicular/industrial/construction/biomass/dust/domestic)
- feat(alerts): multilingual citizen health advisories (English, Marathi, Hindi)
- feat(analytics): city AQI trends, enforcement effectiveness, cross-city comparison
- feat(assistant): Claude-backed AI assistant with context-aware retrieval and evidence citations
- feat(workers): Celery background jobs — AQI ingestion (5 min), forecasting (1h), anomaly detection (5 min), attribution (1h), model retraining (daily)
- feat(anomaly): Z-score spike detection (threshold 2.5σ) with root cause timeline
- feat(websocket): real-time AQI and alert updates per city
- feat(pdf): ReportLab enforcement summary and AQI summary PDF export
- feat(seeder): full Pune demo dataset — 7 days readings, 72h forecasts, anomalies, enforcement actions, policy snapshots, multilingual alerts

**Database**
- feat(schema): 13 tables with UUID, soft delete, PostGIS geometry, TimescaleDB hypertables
- feat(migration): Alembic async migrations with PostGIS and TimescaleDB extension setup
- feat(indexes): GIST spatial indexes, time-series composite indexes, full-text search indexes

**Frontend**
- feat(dashboard): overview with live AQI banner, ward distribution, station cards
- feat(live-aqi): real-time station readings with historical trend charts (Recharts)
- feat(forecast): ward selector + 72h AreaChart with confidence band and feature importance
- feat(enforcement): full CRUD UI with AI reasoning panel, priority badges, status transitions
- feat(analytics): trend lines, anomaly pie chart, city comparison bar chart, policy table
- feat(assistant): full chat UI with evidence panel, confidence scores, reasoning traces, sample queries
- feat(citizen): multilingual alert management with language filter and create form
- feat(reports): PDF export with period selector, enforcement record table
- feat(auth): login page with demo credential autofill
- feat(theme): dark/light mode with next-themes
- feat(websocket): real-time connection indicator, auto-reconnect with 5s backoff

**Infrastructure**
- feat(docker): multi-service Docker Compose (db, redis, backend, celery_worker, celery_beat, frontend)
- feat(ci): GitHub Actions pipeline — lint, type check, test (80% coverage), Docker build
- feat(health): /health endpoint with database and Redis liveness checks
