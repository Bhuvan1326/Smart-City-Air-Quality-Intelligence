# Requirements-to-Implementation Matrix

Classification: **IMPLEMENTED-VERIFIED / IMPLEMENTED-UNVERIFIED / PARTIAL / MOCK-ONLY / NOT-IMPLEMENTED / BLOCKED-INFRA / OBSOLETE**

| # | Feature | Status | Evidence |
|---|---|---|---|
| 1 | User registration (citizen-pinned) | IMPLEMENTED-VERIFIED | `/auth/register`; role forced to CITIZEN; sec tests |
| 2 | Login + JWT access/refresh | IMPLEMENTED-VERIFIED | PyJWT round-trip; family rotation in Redis; tamper rejected |
| 3 | Login throttling | IMPLEMENTED-VERIFIED | `login_throttle` 5/300s→429; 24 W3 tests |
| 4 | Refresh rotation + reuse revocation | IMPLEMENTED-VERIFIED | `validate_and_rotate` fail-closed + family revoke |
| 5 | Password reset flow | **NOT-IMPLEMENTED** | no endpoints/handlers found |
| 6 | RBAC (4 roles) | IMPLEMENTED-VERIFIED | `deps.py` RequireAdmin/Staff/InspectorOnly/Analyst; endpoint matrix |
| 7 | Citizen AQI dashboard + freshness | IMPLEMENTED-VERIFIED | dashboard pages + `DataFreshnessIndicator` + `kpi/data-freshness` |
| 8 | Live alerts list + thresholds | IMPLEMENTED-VERIFIED | `/alerts` CRUD; thresholds staff-only |
| 9 | Civic reports + ownership | IMPLEMENTED-VERIFIED | `/civic/issues`; owner+staff scoping (W2 audit) |
| 10 | Media signed URLs | IMPLEMENTED-VERIFIED | `media_access` HMAC-SHA256+expiry; owner check unsigned |
| 11 | Notifications + IVR (Twilio sig) | IMPLEMENTED-VERIFIED | sig verify fail-closed; ownership tests |
| 12 | WebSocket live feed | IMPLEMENTED-VERIFIED | access-token + citizen per-city 4403 |
| 13 | Forecast endpoint + model meta | IMPLEMENTED-UNVERIFIED* | endpoint exists, model artifacts exist; *live inference on real data BLOCKED* |
| 14 | ML walk-forward evaluation | PARTIAL | evaluator real + fixture-verified; real-data eval BLOCKED-INFRA |
| 15 | Weather ingestion→persistence | PARTIAL | writer implemented+unit-tested; live write BLOCKED-INFRA |
| 16 | OpenAQ ingestion | IMPLEMENTED-UNVERIFIED | provider+rate-budget code real; live run BLOCKED-INFRA |
| 17 | Impact Ledger (outcomes) | PARTIAL→VERIFIED-API | POST/GET endpoints + client + card; DB write test BLOCKED |
| 18 | City Action Brief | **NOT-IMPLEMENTED** | design-only; declared in limitations |
| 19 | Analytics + comparison | IMPLEMENTED-VERIFIED | RequireAnalyst; contract-checked |
| 20 | Waste-burning workflow | IMPLEMENTED-VERIFIED | transitions+actor+audit (W2) |
| 21 | Drone planning | IMPLEMENTED-VERIFIED | staff-only; planner unit-tested |
| 22 | Reports export | IMPLEMENTED-UNVERIFIED | RequireAnalyst endpoint; export path untested locally |
| 23 | Simulator/what-if | IMPLEMENTED-UNVERIFIED | endpoint + unit tests; heavy path untested |
| 24 | AI assistant/agents | IMPLEMENTED-UNVERIFIED | endpoints + provider abstraction; live LLM untested |
| 25 | Sustainability KPIs | IMPLEMENTED-VERIFIED | formulas documented; descriptive-only claims |
| 26 | India AQI observations | IMPLEMENTED-VERIFIED | endpoints + tests |
| 27 | GIS/geospatial queries | IMPLEMENTED-UNVERIFIED | PostGIS endpoints exist; live geo queries BLOCKED-INFRA |
| 28 | Sensor health | IMPLEMENTED-UNVERIFIED | endpoints exist |
| 29 | Exposure/demographics | IMPLEMENTED-UNVERIFIED | endpoints exist |
| 30 | Heat/water/energy/traffic modules | IMPLEMENTED-UNVERIFIED | endpoints + unit tests; provider calls BLOCKED |
| 31 | Admin user mgmt | IMPLEMENTED-VERIFIED | RequireAdmin; demo-seed gated |
| 32 | Contract drift checking | IMPLEMENTED-VERIFIED | `contract:check` 0 errors + deliberate-drift tests |
| 33 | Schema drift tool | IMPLEMENTED-UNVERIFIED | tool exists; live check BLOCKED-INFRA |
| 34 | E2E role walkthrough | BLOCKED-INFRA | spec authored; browsers absent |
| 35 | CI workflows | IMPLEMENTED-UNVERIFIED | ci.yml services+migrations+drift correct; **no run observed** |

| 36 | Request-correlation IDs | IMPLEMENTED-VERIFIED | `CorrelationIdMiddleware` + 13 tests (this session) |
| 37 | App metrics instrumentation | IMPLEMENTED-VERIFIED | `RequestMetricsMiddleware` bounded labels + `/metrics` token-gate |
| 38 | City Action Brief | **NOT-IMPLEMENTED → DEFERRED (decision)** | explicit scope decision recorded — e2e-release-readiness §5.2 |
| 39 | Password reset | **NOT-IMPLEMENTED → DEFERRED (decision)** | explicit scope decision recorded — e2e-release-readiness §5.3 |
| 40 | Dependency hygiene | IMPLEMENTED-VERIFIED | pip 173→46 findings; npm 7→5; weasyprint+ecdsa removed; per-package dispositions |

**Counts:** 40 assessed — 16 IMPLEMENTED-VERIFIED · 12 IMPLEMENTED-UNVERIFIED · 3 PARTIAL · 4 NOT-IMPLEMENTED/BLOCKED (incl. 2 deferred-by-decision) · 3 BLOCKED-INFRA · 2 dual-classified

*IMPLEMENTED-UNVERIFIED means: real code exists with plausible wiring, but the running path could not be exercised in this environment (DB/provider absent). No item is claimed stronger than its evidence.*
