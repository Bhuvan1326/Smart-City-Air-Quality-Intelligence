# Urban Air Quality Intelligence Platform

AI-powered urban air quality monitoring and enforcement intelligence for Indian city administrations. Moves city governments from reactive AQI dashboards to proactive, evidence-based pollution intervention.

## What this solves

India has 900+ CAAQMS stations under the National Clean Air Programme, but only 31% of cities with monitoring data have actionable multi-agency response protocols. The data exists. The intelligence layer to act on it does not.

## Core capabilities

- **Geospatial source attribution** — which emission sources are responsible, at this ward, right now, with confidence scores, now corroborated against real satellite evidence (Sentinel-2 NDVI/NDBI + NASA FIRMS thermal hotspots)
- **Predictive AQI forecasting** — ward-level 24–72 hour forecasts with confidence intervals, blending a trained XGBoost model with real Gaussian-plume atmospheric dispersion (Pasquill-Gifford stability, PM2.5/PM10-differentiated transport)
- **Digital Twin / What-If Simulator** — road closures, traffic diversion, weather scenarios, and multi-lever policy bundles, each with an impact score and confidence interval
- **Enforcement intelligence** — ranked inspection priorities with geospatial documentation, AI reasoning traces, PDF export, and an offline-capable field inspection PWA (works with zero connectivity, syncs automatically)
- **Multi-agent AI pipeline** — 6 core agents orchestrated by a real `langgraph.graph.StateGraph`, with a CrewAI crew handling autonomous evidence-corroboration for low-confidence findings
- **Drone inspection planning** — automatic hotspot detection, battery-aware coverage flight paths, GeoJSON export
- **Predictive sensor maintenance** — drift detection, failure probability, and remaining-useful-life estimates for every monitoring station

## Quick start (Docker, no paid APIs needed)

```bash
git clone <repo>
cd urban-air-quality

cp .env.example .env
# No API keys required for demo — all demo data is synthetic

docker compose up -d
```

Wait ~60 seconds for migrations and seeding to complete, then:

- **Frontend**: http://localhost:3000
- **API**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health

### Demo login credentials

| Role | Email | Password |
|------|-------|----------|
| City Administrator | admin@pune.gov.in | Admin@123 |
| Pollution Control Officer | officer@mpcb.gov.in | Officer@123 |
| Field Inspector | inspector@pune.gov.in | Inspector@123 |
| Citizen | citizen@pune.in | Citizen@123 |

## Demo flow (fully automated)

1. Login as **City Administrator** → Pune Dashboard
2. **Ward 7 AQI spike** (AQI 285) is pre-seeded — anomaly card appears on overview
3. Navigate to **Enforcement** → pre-seeded AI recommendation for Kothrud construction site
4. Navigate to **Forecast** → select Ward W07 — 72-hour forecast chart with confidence band
5. Navigate to **Analytics** → before/after intervention outcome for resolved Yerawada action
6. Navigate to **Citizen Alerts** → Marathi and English alerts for Ward W07
7. Navigate to **AI Assistant** → ask "Why is AQI increasing in Ward 7?" — full evidence response
8. **Reports** → export PDF enforcement summary (no auth required for download link)
9. **Officer Dashboard** → complete an inspection offline (disable network in devtools) — the report queues locally and syncs automatically once reconnected
10. `POST /api/v1/agents/run-graph` → runs the same 6-agent pipeline via a real LangGraph `StateGraph`, with a CrewAI crew that autonomously corroborates any low-confidence attribution finding (needs `ANTHROPIC_API_KEY`; the default `/agents/run` pipeline works without it)

## Architecture

```
frontend/          Next.js 15 + React 19 + TypeScript
  lib/offline/      IndexedDB queue + service worker registration (PWA offline inspection)
backend/           FastAPI + Python 3.12
  agents/          LangGraph StateGraph orchestrator + CrewAI Investigation Crew + 6 core agents
  services/        Dispersion modelling, satellite pipeline, drone planning, notifications, digital twin
  workers/         Celery background tasks (AQI ingestion, forecasting, anomaly detection, satellite, notifications)
  ml/              XGBoost forecast model + retraining pipeline + predictive sensor maintenance
  gis/             PostGIS spatial operations
database/          TimescaleDB (PostgreSQL 16 + PostGIS 3.5)
cache/             Redis 7
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for full system design.

## Free APIs used

Every integration below is optional — the platform runs and every feature
degrades gracefully with zero API keys configured.

| Service | Purpose | Cost |
|---------|---------|------|
| Open-Meteo | Meteorological forecasts | Free, no key |
| OpenAQ | Real CAAQMS readings | Free, key at explore.openaq.org |
| Mapbox | Map rendering | Free tier (50k loads/month) |
| Anthropic Claude | AI assistant + CrewAI Investigation Crew | Free tier / pay-per-use |
| NASA FIRMS | Thermal hotspot / biomass burning detection | **Free forever**, no card — key at firms.modis.gov/api/map_key |
| Copernicus Data Space Ecosystem | Sentinel-2 NDVI/NDBI satellite indices | **Free forever** (EU-run), no card — monthly quota resets, not a time-limited trial |
| Firebase Cloud Messaging | Push notifications | **Free forever** (Spark plan), no card |
| SMTP (Brevo / Gmail App Password) | Citizen email alerts | Free at this volume (Brevo: 300/day, no card) |
| Twilio | SMS / IVR voice alerts | **Not free** — real SMS/voice costs money on every provider past a one-time trial credit. Fully implemented but **off by default** (`TWILIO_ENABLED=false`) so it can never incur a surprise bill |

The platform runs fully in demo mode without any API keys — all sensor data is synthesised with realistic Pune diurnal patterns.

## Background jobs

| Job | Schedule | Description |
|-----|----------|-------------|
| AQI ingestion | Every 5 min | Fetch live readings from all stations |
| Weather fetch | Every 30 min | Open-Meteo forecast data |
| Ward forecasts | Every hour | Regenerate 72h forecasts (trained model + real dispersion, blended) |
| Anomaly detection | Every 5 min | Statistical spike detection (Z-score > 2.5) |
| Attribution | Every hour | Source attribution per ward, informed by latest satellite observation |
| Model retraining | Daily 00:30 | Retrain XGBoost on 90 days of history |
| Sensor maintenance | Daily 06:00 | Explainable drift/failure/RUL assessment per station |
| Satellite fetch | Every 6 hours | Sentinel-2 + NASA FIRMS observations per ward |
| Alert dispatch | Every minute | Deliver pending citizen alerts (push/email/SMS) |
| Drone hotspot detection | Daily 07:00 | Auto-generate flight plans for high-confidence pollution hotspots |

## Stack versions

- Python 3.12, FastAPI 0.115, SQLAlchemy 2.x, Alembic, Pydantic v2
- PostgreSQL 16, PostGIS 3.5, TimescaleDB, Redis 7
- Next.js 15, React 19, TypeScript 5.6, Tailwind CSS v4
- XGBoost 2.1, LangChain 0.3, Anthropic SDK 0.40
- LangGraph 0.2.60 (real `StateGraph` orchestration), CrewAI 1.15 (autonomous investigation crew)
- firebase-admin, twilio (SMS/IVR — off by default)

## Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Workers
celery -A app.workers.celery_app worker --loglevel=info
celery -A app.workers.celery_app beat --loglevel=info
```

## Testing

```bash
cd backend
pytest                           # all tests, coverage report
pytest app/tests/test_auth.py    # specific module
```

Coverage requirement: 80% minimum.
