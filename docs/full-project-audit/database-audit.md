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
| `weather_measurements` | `WeatherMeasurement` vs migration 007, including inherited audit timestamps | **Correction to the original audit:** commit `47226d3` inherited non-null audit timestamps while migration 007 permits NULL. The schema-drift remediation below aligns this model with the existing migrated schema; full PostgreSQL verification remains blocked. |
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

## Weather schema-drift remediation (base revision `47226d333b2e4bc202a0ca18d49dc44e2dcd85f6`)

### Investigation and schema decision

Selected **Case D: model mismatch plus stale baseline**, not a comparator defect.

- `007_weather_measurements` was introduced in `e2dba7d`. Its `created_at` and `updated_at` have always been nullable, timezone-aware timestamps with server `now()` defaults. Its later edit in `d0814b3` only changed type annotations. No subsequent migration through head `025_retire_alandi_karve_road` references the table.
- Baseline commit `3d0c88b` predates the weather ORM model. Alembic's `remove_table` and `remove_index` signatures mean database objects absent from target metadata, not approved deletion instructions.
- Commit `47226d3` introduced and registered `WeatherMeasurement`, along with the persistence writer. Both required indexes and the `(city, observed_at, source)` unique constraint match migration 007. The table has a UUID primary key and no foreign keys. It must remain present.
- The new model accidentally inherited `TimestampMixin.nullable=False`; no migration or weather-specific requirement established a new NOT NULL invariant. Preserve the longstanding migrated schema, including valid existing NULL audit timestamps, rather than inventing a backfill or tightening constraints solely for CI.
- The correction overrides only this model's two audit timestamps with `Mapped[datetime | None]`, `nullable=True`. Timezone-aware types, server defaults, and client-side `updated_at.onupdate=now()` are preserved. `observed_at` and `fetched_at` remain NOT NULL. The shared mixin is unchanged.
- Remove only `remove_table weather_measurements`, `remove_index ix_weather_measurements_city`, and `remove_index ix_weather_measurements_observed_at` from the baseline. All 121 unrelated signatures remain unchanged; no new timestamp exceptions are added. This is a targeted stale-entry cleanup, not a baseline regeneration or a different schema-version baseline.

No new migration is necessary: no database DDL/data change is intended, and migration history, CI, and drift-tool filters are unchanged.

### Count semantics and before/after evidence

`app/tools/schema_drift.py` imports `app.models` and compares live SQLAlchemy reflection against `app.core.database.Base.metadata` using Alembic `compare_metadata`. It flattens and deduplicates differences into sorted signatures. `current` counts those signatures; `baseline` counts entries in `backend/schema_drift_baseline.json`. New and stale entries are set differences. Type/default comparison is already disabled by this existing tool; this change does not alter that policy, and explicit regression assertions cover the weather timestamp types/defaults.

Reported CI before: `current=123 baseline=124 new=2 stale=3`, consistent with `124 - 3 + 2 = 123`.

Locally reproduced before implementation: executing the actual migration 007 against isolated in-memory SQLite gives the two exact timestamp signatures against the original model; omitting the weather metadata gives exactly the three stale signatures. The initial regression run failed twice and passed once, as expected.

After implementation: the same migrated weather table compares with **zero signatures**. Tests verify table/index/constraint presence, timestamps/defaults, legacy NULL-row retrieval, and defaults on new inserts. Deliberately reintroducing NOT NULL in copied metadata still produces both signatures as new drift.

Expected full PostgreSQL output, **not yet observed**: `current=121 baseline=121 new=0 stale=0`, provided all unrelated schema state matches the reported CI run. Count agreement alone is not verification.

### Verification commands and results

All backend commands below ran from `backend` with `.venv/Scripts/python.exe` (abbreviated `python`).

| Command | Exit/result |
|---|---|
| `python -m alembic heads` | 0; single head `025_retire_alandi_karve_road` |
| `python -m alembic history` | 0; linear chain 001 through 025 |
| `python -m app.tools.schema_drift --database-url <CI-local-test-URL>` | 1; `InvalidPasswordError` for the CI user at localhost:5432, before schema comparison. Same URL/command as `.github/workflows/ci.yml:130-131`; credentials are not repeated here. |
| `python -m pytest app/tests/test_week2_schema_drift.py app/tests/test_week3_weather_persistence.py app/tests/test_weather_provider.py app/tests/test_aqi_ingestion.py app/tests/test_model_migration_parity.py -m "not integration" --no-cov -q` | 0; 52 passed, 1 skipped (live migrated DB unset), 5 deselected. Focused diagnostic run, not a coverage gate. |
| `python -m pytest app/tests -m "not integration" -q` | 1; 733 passed, 1 skipped, 261 deselected; **71.14% coverage fails the unchanged 80% gate**. Full-service coverage remains unknown. |
| `python -m black --check app/` | 0; 278 files unchanged |
| `python -m isort --check-only app/` | 0 |
| `python -m ruff check app/` | 0 |
| `python -m compileall -q app db_migrations` | 0 |
| `git diff --check` | 0 |
| Standalone backend type check | No mypy/pyright gate found in backend configuration or CI; not claimed run. |
| `alembic upgrade head`, full pytest, fresh/full-chain and previous-head database upgrades | NOT RUN: no authorized disposable database. Existing fixtures drop tables during teardown and must not target an unidentified/shared server. |

Docker is not installed. Local port 5434 (the test default) and Redis 6379 refuse connections; PostgreSQL 5432 is reachable but rejects CI credentials. No credential retries, migration writes, or PostgreSQL test writes were attempted after that authentication failure. SQLite tests prove this table's migration/metadata contract, not PostgreSQL/PostGIS/TimescaleDB or the full migration chain.

### Remaining verification

Use the existing CI workflow's fresh `airquality_migrations` database and separate disposable `airquality_test` database, with its required extensions. After confirming targets and supplying authorized test credentials via environment variables, run from `backend` (Bash):

```bash
python -m alembic upgrade head
python -m alembic current
python -m app.tools.schema_drift --database-url "$DATABASE_URL"
MIGRATED_DATABASE_URL="$DATABASE_URL" python -m pytest --cov=app --cov-report=xml --cov-fail-under=80
```

`DATABASE_URL` must target the migration-check database; `TEST_DATABASE_URL` must target a separate disposable test database and `REDIS_URL` a test Redis instance. Do not refresh the baseline to accept unexpected findings. Live schema-drift success and CI success remain **unverified**, pending these checks.
