# Week 3 — API Contract Changes

Baseline verified: `app.main` imports cleanly; **124 routes**; OpenAPI has **0 duplicate operation IDs**; `npm run contract:check` → `{"callsCompared":93,"fieldsCompared":1232,"errors":0,"warnings":0}`.

## New endpoints (Impact Ledger)

### `POST /api/v1/enforcement/{action_id}/outcome`

| Aspect | Contract |
|---|---|
| Auth | Bearer JWT (access token) |
| Role | `city_administrator`, `pollution_control_officer`, or `field_inspector` |
| Extra authz | `field_inspector` may only record outcomes on actions **they created** (404 otherwise) |
| Path | `action_id: UUID` |
| Body `RecordOutcomeRequest` | `aqi_before: float≥0`, `aqi_after: float≥0`, `measurement_period_hours: int (1..720)`, `verification_method: str`, `confidence_score: float (0..1)`; optional `pm25_before`, `pm25_after`, `carbon_saved_kg` |
| Response | `201` → `InterventionOutcomeRead` with server-computed `delta_score = aqi_before − aqi_after` (positive = AQI fell) |
| Errors | 401/403 auth/role; 404 action not found or not owned; 422 schema validation |
| Semantics | One row per recording event (audit trail); descriptive before/after — **not causal evidence** |

### `GET /api/v1/enforcement/outcomes`

| Aspect | Contract |
|---|---|
| Auth | Bearer JWT |
| Role | `city_administrator`, `pollution_control_officer` |
| Query | `city?: str` (defaults to caller's city when omitted), `page ≥1`, `page_size 1..100` |
| Response | `PaginatedResponse[InterventionOutcomeRead]` (`items`, `total`, `page`, `page_size`, `pages`), ordered `created_at DESC` |
| Errors | 401/403; 422 invalid pagination |

**Route-order note:** `/outcomes` is registered **before** `/{action_id}` in the router — verified at runtime, otherwise `/outcomes` would 422 on UUID parsing.

### Frontend client (`lib/api/services.ts`)

```ts
enforcementApi.recordOutcome(id, data)   // POST /enforcement/{id}/outcome
enforcementApi.listOutcomes({city,page,page_size})  // GET /enforcement/outcomes
```
Types: `InterventionOutcome`, `RecordInterventionOutcome`. UI: `ImpactLedgerCard` on `/dashboard/analytics` with explicit loading/empty/error states and a "descriptive, not causal" label.

## Changed contracts (non-breaking)

| Component | Change |
|---|---|
| `RateLimitMiddleware` | On Redis outage: requests to `/api/v1/auth/*` and `/api/v1/admin/*` → **503** (`rate_limiter_unavailable`); all other paths fall back to a bounded in-process sliding-window limiter (`RATE_LIMIT_FALLBACK_RPM`, default 30/min/IP). Was: fail-open (unlimited). |
| `POST /api/v1/auth/login` | Adds per-identifier throttling (`login_throttle`): `LOGIN_MAX_ATTEMPTS` (5) failures within `LOGIN_WINDOW_SECONDS` (300s) → 429 with `Retry-After`. Success resets. Uses Redis when up; in-process fallback otherwise. Response body does not reveal account existence. |
| `GET /api/v1/ws/aqi?city=…` | After token auth: **citizens** may only subscribe to `city == user.city` (close `4403`); staff roles unrestricted. Refresh tokens already rejected. |

## New internal contract (not HTTP)

`weather_persistence.persist_hourly_forecast(db, city, lat, lng, hourly, source="open-meteo")` — upserts `weather_measurements` on `(city, observed_at, source)`; idempotent re-fetch refreshes `temp_c/humidity/wind/pressure/precip/weather_code` + new `fetched_at`. Wired into `aqi_ingestion._fetch_weather_async` (was a dead fetch). Model `WeatherMeasurement` matches migration 007 exactly.

## Backward compatibility

No route removed, no response shape changed. All additions are additive endpoints or tightened failure behavior (Redis outage path that was previously silently insecure).
