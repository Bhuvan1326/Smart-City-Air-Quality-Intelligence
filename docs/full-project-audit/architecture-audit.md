# Architecture Audit — verified from code

## Stack (manifest-verified)

| Layer | Technology | Source |
|---|---|---|
| Backend | FastAPI (Python 3.12.10), SQLAlchemy async, Pydantic v2 | `app/main.py`, `requirements.txt` |
| DB | PostgreSQL 16 + PostGIS + TimescaleDB | `docker-compose.yml` `timescale/timescaledb-ha:pg16`; geoalchemy2 WKTElement usage |
| Cache/queue | Redis 7 | `app/core/redis_client.py`, compose `redis:7-alpine` |
| Auth | PyJWT 2.15.1 (HS256) + passlib/bcrypt | `app/core/security.py` |
| Frontend | Next.js 15.5, React 19, TS 5.6, TanStack Query, Zustand | `frontend/package.json` |
| ML | XGBoost, scikit-learn, pandas, joblib artifacts | `app/ml/`, `ml_models/` |
| Providers | OpenAQ, Open-Meteo, Twilio, FCM, satellite (MODIS/FIRMS, Sentinel) | `app/services/` |

## Verified request path

```mermaid
flowchart LR
    Browser -->|/api/backend/* rewrite| NextAPI[Next.js rewrites]
    NextAPI -->|proxy to BACKEND_URL| FastAPI
    subgraph FastAPI
        MW[CORSMiddleware → GZip → SecurityHeaders → CSRF → RateLimit → AuditLog]
        Router[api_router /api/v1 — 124 routes]
        Deps[get_current_user / RequireStaff / RequireAnalyst / RequireAdmin]
        Svc[app/services/* business logic]
    end
    MW --> Router --> Deps --> Svc
    Svc --> PG[(Postgres+PostGIS+Timescale)]
    Svc --> Redis[(Redis: rate-limit, token families, queues)]
    Svc --> Ext[Providers: OpenAQ / Open-Meteo / Twilio / FCM]
    Workers[app/workers — scheduler-driven tasks] --> PG
    Workers --> Ext
    WS[/api/v1/ws/live/{city}?token=jwt/] --> Redis
```

## Middleware order (verified, `main.py:106-117`)

`CORSMiddleware → GZipMiddleware → SecurityHeadersMiddleware → CSRFMiddleware → RateLimitMiddleware → AuditLogMiddleware` — note Starlette executes in reverse-add order: AuditLog is the outermost wrapper, CORS innermost next to the app. Audit covers all mutating methods against a SKIP_PATHS allowlist.

## Entry points

- **API**: `app.main:app` (uvicorn). `api_router` aggregated in `app/api/v1/__init__.py` (restored — prior P0).
- **Workers**: `app/workers/scheduler.py` — fixed-interval tasks (AQI ingestion incl. weather persist, anomaly detection, alerts, forecast retrain).
- **WS**: `/api/v1/ws/live/{city}?token=` — access-token-only, per-city authz for citizens.
- **Frontend**: Next.js App Router, 43 pages under `app/dashboard/*`; API calls through `lib/api/client.ts` → `services.ts`; `next.config.ts` rewrites `/api/backend/*` → `${BACKEND_URL}/api/v1/*`.

## Confirmed structural findings

| Finding | Status |
|---|---|
| Circular imports | None observed; heavy imports are function-local by convention (e.g. `from app.core.redis_client import get_redis` inside functions) |
| Missing/broken imports | None — `compileall` clean, app boots |
| Dead endpoints | None found — every route reachable via router; `/metrics` intentionally schema-hidden |
| Duplicate routes / op-IDs | None — 0 duplicate operation IDs in OpenAPI |
| Missing runtime deps | None after `twilio` added to manifests |
| Unused deps | `prometheus_client` optional-imported for `/metrics` (graceful ImportError) |
| Hardcoded localhost | Only as env-var *defaults*: `DATABASE_URL`, `REDIS_URL`, `ALLOWED_ORIGINS`, `NEXT_PUBLIC_API_URL`, `BACKEND_URL` — all overrideable |
| Mock-in-production | None found — synthetic data is flagged `is_synthetic` and surfaced as "Demo data" |
| Frontend-as-security-boundary | Not relied on — `role-policy.ts` is UX-only, backend enforces |
