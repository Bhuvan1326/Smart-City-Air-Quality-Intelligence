# Week 4 — Defect Register

Status legend: **OPEN / FIXED-UNVERIFIED / VERIFIED / BLOCKED / ACCEPTED-RISK**

| ID | Sev | Defect | Reproduction | Root cause | Fix | Regression test | Validation | Status |
|---|---|---|---|---|---|---|---|---|
| D-01 | P0 | `app.main` import fails — `api_router` missing | `from app.main import app` → ImportError | `app/api/v1/__init__.py` emptied by commit 3d0c88b | Restored aggregator incl. kpi/media_links routers | startup test + route count | 124 routes load | **VERIFIED** (ff33c0f) |
| D-02 | P1 | `frontend/lib/utils.ts` broken — dup `AQI_BANDS`/`AQIBand`, dangling comment | `npx tsc` → duplicate identifier | bad manual edit | Removed duplicate block | tsc + 49 tests | tsc clean, 49/49 | **VERIFIED** |
| D-03 | P0 | Weather fetch discarded — `weather_measurements` never written | read `_fetch_weather_async` — result unused | fetch-without-persist; table had no ORM model | `WeatherMeasurement` model + `persist_hourly_forecast` upsert + task wiring | 8 mapper tests | 24/24 W3 tests | **VERIFIED** (unit); live write **BLOCKED** (no DB) |
| D-04 | P0 | Rate limiter fails open on Redis outage | kill Redis → unlimited requests | `except RedisError: pass` in middleware | fail-closed 503 on auth/admin paths; bounded in-process fallback elsewhere | Redis-down tests | 24/24 W3 tests | **VERIFIED** (unit) |
| D-05 | P1 | No login throttling | brute-force `/auth/login` — unlimited | absent feature | `login_throttle` per-identifier 5/300s → 429, Redis+in-process | throttle tests | 24/24 W3 tests | **VERIFIED** (unit) |
| D-06 | P1 | WS subscribe to any city | citizen connects `?city=X` ≠ own city | authn only, no authz | citizen→`user.city` check, close 4403 | WS authz tests | 24/24 W3 tests | **VERIFIED** (unit); live socket BLOCKED |
| D-07 | P1 | `twilio` imported but absent from manifests | `import twilio` → ModuleNotFound when enabled | dep never declared | `twilio==9.10.9` in requirements+pyproject, installed | signature tests | TwiML + 2 sig tests pass | **VERIFIED** |
| D-08 | P2 | Duplicate OpenAPI operation IDs (IVR GET+POST) | `app.openapi()` → dup IDs | single `api_route` for 2 methods | split handlers over shared logic | OpenAPI dup check | 0 dup IDs | **VERIFIED** |
| D-09 | P2 | Impact Ledger read-only — outcomes only via seeder | no API path to POST outcome | endpoint never built | POST `/{id}/outcome` + GET `/outcomes` + schemas + client + `ImpactLedgerCard` | schema tests + contract | contract 93 calls clean | **VERIFIED** (API); DB write path BLOCKED |
| D-10 | P1 | `python-jose` PYSEC-2025-185 | `pip-audit` | upstream advisory, no fixed release | **W5: migrated to `PyJWT==2.15.1`** — single import point `security.py`; jose uninstalled | token round-trip + 31 sec tests | PyJWT decode/encode verified, tamper rejected | **VERIFIED** (W5) |
| D-11 | P2 | 2 Redis tests fail in non-integration lane | `pytest -m "not integration"` | tests need real Redis but unmarked | **W5: `pytestmark += integration`** | lane deselection test | `2 deselected` in unit lane | **VERIFIED** (W5) |
| D-12 | P2 | 178 pip vulns / 17 pkgs | `pip-audit` | transitive/pinned old versions | owner-driven triage, no blind bulk bump | — | — | **OPEN → W5** |
| D-13 | P3 | npm: 2 vulns need breaking next@16 | `npm audit` | postcss/next chain | deferred by plan (owner decision) | — | — | **OPEN — decision required** |
| D-14 | P3 | Next build root-lockfile warning | `next build` | two package-locks (root + frontend) | pick canonical root | — | warning only, build passes | **ACCEPTED-RISK** |
| D-15 | P1 | Coverage 80% gate unmet locally | pytest --cov | DB-blocked lanes exclude integration code | full run in CI with services | — | last measurable: 70.51% non-int lane | **BLOCKED** |
| D-16 | P2 | Real ML eval impossible | no populated obs DB | DB unprovisioned; no export | ingest ≥35d → export CSV → run evaluator | evaluator green on fixture | fixture artifact exists | **BLOCKED** |
| D-17 | P2 | Playwright role walkthrough unexecuted | browsers absent | env | `playwright install` + running stack | spec authored | — | **BLOCKED** |

## Counts
- VERIFIED fixed: D-01, D-02, D-03(unit), D-04, D-05, D-06, D-07, D-08, D-09, **D-10, D-11 (W5)** — 11
- OPEN: D-12 (pip vulns), D-13 (next@16)
- ACCEPTED-RISK: D-14
- BLOCKED: D-15, D-16, D-17
