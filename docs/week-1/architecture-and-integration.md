# Architecture and Integration (as inspected)

Everything below is from reading the repository and running it locally in a sandbox; nothing was deployed. Items I could not confirm are marked *(not verified)*.

## Components
| Layer | Technology (verified in code/deps) | Location |
|---|---|---|
| Frontend | Next.js (App Router) + React, TanStack Query, Zustand auth store, axios client with refresh interceptor, service worker / IndexedDB offline layer | `frontend/` |
| Backend API | FastAPI, async SQLAlchemy (asyncpg), Pydantic, structlog; routes under `/api/v1` | `backend/app/` |
| Auth | JWT bearer access + refresh tokens, passlib password hashing, role dependency factory `require_roles` | `core/security.py`, `api/deps.py` |
| Database | PostgreSQL with PostGIS; TimescaleDB `time_bucket` used by history queries; Alembic-style migrations in `backend/db_migrations/versions` (25 files) | `backend/db_migrations/` |
| Cache / locks | Redis (rate limiting, scheduler locks); fails open when unavailable | `core/middleware.py`, `workers/scheduler.py` |
| Background work | In-process scheduler started with the app (ingestion, forecast regeneration, nightly retrain) | `workers/scheduler.py`, `workers/tasks/*` |
| AI/ML | XGBoost 1-hour AQI model (`ml_models/*.joblib`, 9 artifacts), statistical fallback, SHAP explanations, LangGraph agents (CrewAI listed in requirements, not installed here) | `app/ml`, `app/agents` |
| External services | OpenAQ v3, Open-Meteo (OpenWeather key optional), NASA FIRMS, Sentinel Hub, traffic provider (configurable, empty default), electricity provider (`auto`), Twilio (SMS/IVR), Anthropic/Gemini (assistant, civic photo classifier) | `app/core/config.py`, `app/services/*` |

## Request / data flows (actual)
1. **Auth:** client `POST /auth/login` -> JWT pair -> axios attaches bearer; 401 triggers `/auth/refresh`; frontend `middleware.ts` + `module-access.ts` shape navigation; **API dependencies enforce roles**.
2. **Live AQI:** scheduler -> provider (OpenAQ, Pune station path with observation timestamps; legacy 10-minute path for other cities) -> `aqi_readings` with `quality_flag` -> API -> frontend maps/cards.
3. **Forecast:** scheduler regenerates ward forecasts from latest readings (+weather) -> `forecast_grids`; on request `ml/inference.py` runs XGBoost recursively or the statistical fallback; nightly retrain writes a new joblib artifact.
4. **Civic reports:** citizen `POST /civic/issues` (photo -> `evidence_storage` under `/media`) -> status events -> staff triage/resolve -> citizen verification; escalation job (admin-triggered).
5. **Alerts:** staff create alerts -> `citizen_alerts` -> `notifications`; Twilio SMS/IVR webhooks.

## Module boundaries and integration points
- Frontend <-> backend only through `/api/v1` (proxied path); contract in `api-contracts.md`.
- Ingestion -> forecasting via `aqi_readings` (hourly aggregation in the training query) — schema coupling, no versioned interface.
- Forecasting -> frontend via forecast endpoints; no `source` field distinguishes model vs fallback.
- Role model shared by `deps.py`, frontend `role-policy.ts` (mirror) and `Sidebar.tsx` (separate hard-coded lists) — three places to keep in sync.

## Risks to integration
Shared-schema coupling (B-list in `integration-blockers.md`), in-process scheduler duplicating work across workers if Redis locks fail open, inverted dependency names in `deps.py`, absence of field-level contract tests.

## Out of scope this week
Docker/deployment/cloud. Not inspected beyond noting `docker-compose.yml` sets `ENVIRONMENT` and `backend/vercel.json` routes everything to `api/index.py` (a serverless-style entry; whether a hosted demo depends on demo-user seeding is *not verified*).
