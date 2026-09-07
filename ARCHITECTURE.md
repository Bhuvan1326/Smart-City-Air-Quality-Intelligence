# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Load Balancer / Nginx                     │
└──────────────┬──────────────────────────────────┬───────────────┘
               │                                  │
     ┌─────────▼──────────┐            ┌──────────▼─────────┐
     │   Next.js 15 SPA   │            │   FastAPI Backend   │
     │   React 19         │◄──REST────►│   Python 3.12      │
     │   Tailwind v4      │◄──WS──────►│   Uvicorn/Gunicorn │
     │   TanStack Query   │            │   Port 8000        │
     │   Port 3000        │            └──────────┬─────────┘
     └────────────────────┘                       │
                                        ┌──────────┼──────────┐
                                        │          │          │
                              ┌─────────▼──┐  ┌────▼────┐  ┌─▼──────┐
                              │TimescaleDB │  │ Redis 7 │  │Celery  │
                              │PostGIS 3.5 │  │ Cache   │  │Workers │
                              │PostgreSQL16│  │ Broker  │  │+ Beat  │
                              └────────────┘  └─────────┘  └────────┘
```

## Backend module map

```
app/
├── api/v1/endpoints/
│   ├── auth.py         # JWT auth, register, login, refresh
│   ├── dashboard.py    # Overview aggregation with Redis cache
│   ├── aqi.py          # Live readings + TimescaleDB history
│   ├── forecast.py     # Ward-level 72h forecasts
│   ├── enforcement.py  # CRUD with RBAC, status transitions
│   ├── alerts.py       # Citizen alerts + attribution history
│   ├── analytics.py    # Trend analysis, city comparison
│   ├── reports.py      # PDF generation (ReportLab)
│   ├── assistant.py    # AI chat endpoint
│   └── websocket.py    # Live WS per city
├── agents/
│   └── assistant_agent.py  # Gemini-backed NL query agent
├── workers/tasks/
│   ├── aqi_ingestion.py    # Fetch/generate readings every 5 min
│   ├── forecast.py         # XGBoost ward forecasts, model retraining
│   ├── anomaly_detection.py # Z-score spike detection + sensor health
│   ├── attribution.py      # Source attribution per ward
│   └── alerts.py           # Multilingual alert generation
├── models/             # SQLAlchemy ORM (PostGIS + TimescaleDB)
├── repositories/       # Data access layer (async)
├── services/           # Business logic (auth)
└── core/
    ├── config.py       # Pydantic settings from env
    ├── database.py     # Async SQLAlchemy engine
    ├── redis_client.py # Cache helpers
    ├── security.py     # JWT + bcrypt
    ├── websocket.py    # Connection manager
    ├── logging.py      # Structlog JSON
    └── seeder.py       # Demo data (7d readings, forecasts, anomalies)
```

## Database schema

13 tables. All with UUID PK, created_at/updated_at, soft delete.

| Table | Type | Notes |
|-------|------|-------|
| users | standard | RBAC roles |
| monitoring_stations | PostGIS POINT | CAAQMS station registry |
| aqi_readings | TimescaleDB hypertable | Partitioned by timestamp |
| emission_sources | PostGIS GEOMETRY | Industrial, construction, vehicular |
| enforcement_actions | PostGIS POINT | AI reasoning stored as JSONB |
| forecast_grids | PostGIS POLYGON | Ward-level 1km² grids |
| citizen_alerts | standard | Multilingual, per channel |
| intervention_outcomes | standard | Before/after AQI delta |
| anomaly_events | PostGIS POINT | Z-score spike detection |
| officer_routes | PostGIS LINESTRING | Optimised waypoints |
| policy_snapshots | standard | Cross-city comparison |
| pollution_attributions | TimescaleDB + PostGIS | Per ward, per hour |
| audit_logs | standard | All API actions |

## Multi-agent orchestration pipeline

Six core agents (`app/agents/langgraph_agents.py`) — Data Ingestion,
Forecast, Attribution, Enforcement, Citizen Advisory, Policy Analytics —
each implementing a common `BaseAgent.execute()` contract that returns a
structured `AgentOutput` (confidence score, reasoning trace, supporting
evidence, data sources, feature importance, execution metadata). Every
agent call goes through `run_with_retry()` (up to 3 attempts, exponential
backoff).

Two orchestrators are available:

```
POST /agents/run          AirQualityOrchestrator (default)
                           Hand-rolled async orchestrator, sequential +
                           asyncio.gather() for independent branches.

POST /agents/run-graph    LangGraphOrchestrator (additive)
                           A real langgraph.graph.StateGraph with the same
                           dependency order, plus one extra node:

    START → ingestion → forecast ─────╮
                     ╰─→ attribution ─┴→ investigation → enforcement → policy → END
                                                       ╰─→ advisory ─────╯

  "investigation" runs a CrewAI crew (Field Investigator + Evidence
  Verifier agents, sequential process, shared memory) ONLY when
  Attribution's confidence < 0.65 — otherwise it's a fast no-op pass-through.
  The crew cross-checks satellite evidence, citizen alert history,
  enforcement history, and sensor health, then feeds a confidence
  adjustment (±0.15 max) back into shared graph state — genuine
  LangGraph-orchestrates / CrewAI-executes-autonomous-subtasks division of
  labor. Requires GEMINI_API_KEY; degrades to a no-op without one.
```

Both orchestrators share the same six agent instances and produce
structurally equivalent aggregated output (`overall_confidence`,
per-agent `confidence_scores`/`reasoning_traces`, `supporting_evidence`,
`data_sources`, `errors`) — `/run-graph` additionally includes an
`investigation` key.

## Assistant chat pipeline

```
User query
    │
    ▼
AssistantAgent.respond()
    │
    ├── _fetch_context(query)
    │   ├── Always: current AQI snapshot (last 2h)
    │   ├── If "source/why/cause": pollution attribution
    │   ├── If "forecast/tomorrow": forecast_grids
    │   ├── If "enforcement/inspection": enforcement_actions
    │   └── If "anomaly/spike/alert": anomaly_events
    │
    ▼
Gemini gemini-2.5-flash
    │   system = city context + retrieved data
    │   max_output_tokens = 1500
    │
    ▼
Response with:
    ├── answer (natural language)
    ├── confidence_score (data completeness heuristic)
    ├── data_sources (cited)
    ├── map_data (ward AQI points for frontend)
    ├── supporting_evidence (sensor readings)
    └── reasoning_trace (what data was fetched)
```

This is a separate, narrower pipeline from the six-agent orchestration
above — a single Gemini call for interactive Q&A, not multi-agent.

## Atmospheric dispersion model (`app/services/dispersion.py`)

Real Gaussian plume dispersion, feeding both the Forecast Agent and the
What-If Simulator's `/twin/dispersion` digital-twin endpoint:

```
Wind speed + time of day
    │
    ▼
Pasquill-Gifford stability class (A–F)
    │
    ▼
Briggs urban dispersion coefficients → sigma_y, sigma_z(downwind distance)
    │
    ▼
Gaussian plume equation, evaluated per ward pair within a 60° upwind cone
    │
    ├── PM2.5: near-zero settling velocity (passive tracer at city scale)
    └── PM10: measurable settling velocity (attenuates faster with distance)
    │
    ▼
Cross-ward transport delta, decayed with forecast lookahead hours
(a snapshot wind reading shouldn't be trusted 3 days out)
```

## Forecast pipeline

```
Current AQI (TimescaleDB)
    │
    ├── Feature engineering
    │   ├── hour_of_day (sin/cos encoded)
    │   ├── day_of_week (sin encoded)
    │   ├── is_weekend, is_industrial_ward
    │   ├── is_peak_morning, is_peak_evening
    │   └── current_aqi
    │
    ├── Statistical model (demo) → XGBoost (production after 90d data)
    │
    ├── For each ward × each of 72 hours:
    │   ├── aqi_forecast
    │   ├── confidence_score (degrades with lookahead)
    │   ├── confidence_lower / confidence_upper
    │   └── contributing_factors + feature_importance
    │
    └── Persist to forecast_grids (TimescaleDB)
```

## Security model

- JWT HS256 access tokens (30 min) + refresh tokens (7 days), with
  Redis-backed rotation and theft/reuse detection (replaying an
  already-rotated refresh token revokes the entire token family)
- bcrypt password hashing (rounds=12)
- RBAC enforced at dependency level — not in business logic
- Rate limiting: 60 req/min, 1000 req/hour per user
- Secure headers on every response: CSP, HSTS (production only),
  X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- CSRF double-submit-cookie protection (scoped to any future cookie-based
  auth flow — current Bearer-token flows aren't ambient credentials and
  don't need it, but the protection is in place for when it applies)
- Input sanitization on free-text fields (enforcement notes/descriptions,
  alert messages) — rejects script/HTML injection rather than silently
  stripping it
- All secrets via environment variables
- Audit log on every mutation
- CORS: explicit allowed origins only

## Performance

- Redis cache: dashboard (2 min TTL), live AQI (5 min), forecasts (1 hour)
- TimescaleDB continuous aggregate (`aqi_daily_by_station`) for the
  analytics daily-trend chart — incrementally maintained rather than
  rescanning raw readings on every request; compression policy on chunks
  older than 7 days; retention policy drops raw rows older than 2 years
  (daily rollups in the continuous aggregate are unaffected)
- TimescaleDB time_bucket for ad-hoc aggregation queries
- PostGIS GIST indexes on all geometry columns
- Async SQLAlchemy with connection pool (20 + 40 overflow)
- GZip middleware for API responses > 1KB
- Frontend: TanStack Query with stale-while-revalidate
- PWA service worker: cache-first static assets, network-first API with
  offline fallback — the officer dashboard remains usable with zero
  connectivity
