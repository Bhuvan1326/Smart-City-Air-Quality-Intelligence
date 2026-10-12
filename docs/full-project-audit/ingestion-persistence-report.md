# Ingestion & Persistence Report (Priority 3)

## Status: CODE-VERIFIED, LIVE-PATH BLOCKED (no DB/Postgres on this machine)

## 3.1 — Traced call graph (verified, no parallel implementations created)

```
scheduler (app/workers/scheduler.py, fixed intervals)
└─ aqi_ingestion task (every 900s)
   ├─ OpenAQ client ──► validate/convert units/UTC ──► aqi_measurements
   │                    (source+observed_at keys, is_stale flags)
   └─ _fetch_weather_async ──► Open-Meteo hourly
        └─ weather_persistence.persist_* 
           ├─ map_open_meteo_hourly  (field map, unit validation, skip-rules)
           └─ persist_weather_rows   (upsert on uq_weather_city_time_source)
              ──► weather_measurements
Dashboard:  /aqi/* + /kpi/data-freshness  ←  same tables  ←  contract-checked client
```

## 3.2 — Provider handling (test-verified where non-DB)

| Case | Handling | Evidence |
|---|---|---|
| Success | mapped+persisted | mapper unit tests (8) |
| Empty results | 0 rows, logged | mapper test |
| Missing/invalid fields | row skipped or null-column (never fabricated) | mapper tests |
| Invalid unit/timestamp | skip, not converted | mapper tests |
| 429 / rate budget | OpenAQ client enforces 45rpm/1700rph margin | provider code + tests |
| Timeout/transient | cycle skips+logs; no partial writes | task code |
| Partial (one provider down) | other cities/providers continue | per-city loop isolation |

## 3.3 — Persistence & idempotency

- Weather: **upsert** on `(city, observed_at, source)` — re-fetch refreshes (correct for revised forecasts); out-of-order keyed on `observed_at`.
- AQI: source+timestamp dedup; `is_stale`/`stale_since` flags.
- Integration test asserting real write+count+idempotent re-run: **written** (`test_week3_weather_persistence.py`, `integration`-marked) — **BLOCKED: needs `localhost:5434`**.

## 3.4 — Freshness/dashboard

Freshness KPI endpoint + `DataFreshnessIndicator` share thresholds; `is_synthetic` → "Demo data"; stale never labeled live (unit-tested).

## 3.5 — Impact Ledger persistence

API contract verified (role-gated POST, server-computed `delta_score`, inspector-ownership 404, validation bounds, paginated GET). Real write/read cycle = integration test → **BLOCKED**.

## Acceptance status

| Criterion | Status |
|---|---|
| Ingestion success/failure tests | PASS (non-DB lane) |
| Live test-DB write+read | **BLOCKED** — `docker compose up db` |
| Idempotency/timestamps/units | verified in mapper; live upsert BLOCKED |
| Provider failures bounded | verified (unit) |
| Dashboard freshness honest | PASS |
| Impact Ledger persistence | **BLOCKED** (API verified, write-path needs DB) |
