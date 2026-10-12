# Week 5 — Weather Data Pipeline

## Data flow (as implemented W3)

```
Open-Meteo hourly API (Pune+Mumbai, 3-day horizon)
  → aqi_ingestion._fetch_weather_async (every 900 s)
  → weather_persistence.persist_hourly_forecast(db, …)
      · map provider fields → WeatherMeasurement columns
      · skip rows with missing timestamp / invalid unit (never unit-guess)
      · UPSERT on (city, observed_at, source) — re-fetch refreshes readings + fetched_at
  → weather_measurements table (migration 007 schema)
  → ML dataset builder (avg_temp / avg_humidity / avg_wind features)
```

## Contract guarantees

| Property | Implementation |
|---|---|
| Provenance | `source="open-meteo"` stored per row |
| Time semantics | `observed_at` = provider UTC timestamp; `fetched_at` = ingestion time — distinct columns |
| Timezone | normalized to UTC at the mapper |
| Units | temp °C, humidity %, wind km/h + dir, pressure hPa, precip mm, WMO `weather_code` — validated, unsupported units skipped not converted |
| Idempotency | unique key `(city, observed_at, source)`; repeated fetch updates in place |
| Out-of-order | keyed by `observed_at`, arrival order irrelevant |
| Forecast vs obs | `is_forecast` flag distinguishes modelled hourly points from measured |
| Failure reporting | task logs provider failure, skips cycle — no partial row, no secret payloads logged |

## Evidence status

- Mapper + validation logic: **8 unit tests pass** (`test_week3_weather_persistence.py`).
- DB write-path: **1 integration test written, BLOCKED locally** (Postgres `:5434` refused); runs in CI.
- Live ingestion: **never claimed** — requires the worker + DB stack running.

## Unsupported provider scenarios (explicit)

1. Non-Open-Meteo payloads — the mapper is provider-specific; a second provider needs its own mapper into the same contract.
2. Sub-hourly or >3-day horizon data — task contract is hourly×3d.
3. Missing `time` array entries — skipped rows, not interpolated.
4. Units outside the °C/%/km/h/hPa/mm set — skipped (no guessing).
5. Backfill before provider retention — Open-Meteo free tier won't serve deep history; historical gaps must be filled by a different source or marked absent.

## What the ML pipeline consumes

`dataset.py::FEATURE_COLUMNS` reads `avg_temp / avg_humidity / avg_wind` — now backed by real stored rows once ingestion runs, instead of the previous state where the table existed but was never written.
