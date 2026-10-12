# Database Audit

## Schema inventory

- **25 migrations** `db_migrations/versions/001–025` (linear numbering, no branches observed): initial schema, TimescaleDB optimization, forecast explainability, hotspots, traffic, **weather_measurements (007)**, model metrics, anomaly fields, alert engine, demographics, green cover, waste, water, civic issues+governance, resolution+clusters, ward assignment, monitoring stations, Pune live stations (+stale flag, +retired set), water history, heat readings, notifications.
- ORM: `app/models/` — `BaseModel` provides UUID id, created_at/updated_at, soft-delete (`is_deleted`, `deleted_at`) — matches migration column patterns.

## Required extensions (verified from migration code)

- **PostGIS** — `geoalchemy2` Geometry columns (enforcement `geometry` WKTElement srid=4326; ward boundaries; station coords).
- **TimescaleDB** — migration 003 hypertable optimization on time-series tables.
- Image `timescaledb-ha:pg16` ships both — compose + CI consistent.

## ORM↔migration consistency (spot-verified)

| Table | Check | Result |
|---|---|---|
| `weather_measurements` | model `WeatherMeasurement` vs migration 007: `temperature/humidity/wind_speed/wind_direction/pressure/precipitation/weather_code/source(open_meteo)/is_forecast/observed_at/fetched_at` + `uq_weather_city_time_source` + BaseModel cols | **MATCH column-for-column** (verified line-by-line this audit) |
| `intervention_outcomes` | ORM model exists; writer now real (W3) not just seeder | consistent |
| `enforcement_actions` | model + ownership fields | consistent |

Full live drift check (`app.tools.schema_drift`) is **BLOCKED** — needs migrated DB; CI runs it post-migration on `airquality_migrations`.

## Persistence & idempotency map

| Data | Writer | Idempotency | Status |
|---|---|---|---|
| AQI observations | `aqi_ingestion` task → OpenAQ | source+timestamp keys, stale flag | implemented; live BLOCKED |
| Weather | `weather_persistence` ← Open-Meteo, in ingestion task every 900s | **upsert on (city, observed_at, source)** | implemented+unit-tested; live BLOCKED |
| Forecasts | forecast worker → model artifacts + records | versioned artifacts + `.meta.json` (new trainings) | implemented |
| Alerts/notifications | alert engine + dispatcher | ownership keyed | implemented |
| Civic reports | civic endpoints | dedup detection exists | verified W2 |
| Media metadata | civic/media + EvidenceStorage | signed-URL reads | implemented |
| Intervention outcomes | `POST /{id}/outcome` | audit row per event | implemented; DB test BLOCKED |
| Audit records | `AuditLogMiddleware` | async write, same engine | implemented |

**No writer-less tables found.** The prior gap (weather fetch-discard) is fixed. No consumer relies solely on seed records — seeder rows are `is_synthetic`-flagged and labeled "Demo data" in UI.

## Transactions & failure handling

- `session.flush()`/`refresh()` patterns; audit log uses the same engine (not a second conn) — a documented correctness decision.
- Unique-constraint upserts (weather) refresh rows — no duplicate-on-retry.
- Connection pool: asyncpg via `get_db`; pool sizing is SQLAlchemy defaults (no explicit tuning observed — P4 note).
- **Downgrade paths** exist on migrations (Alembic-versioned) — executed? unverified (BLOCKED).
