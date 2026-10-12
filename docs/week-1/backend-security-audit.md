# Backend Security Audit (Week 1)

Scope: server-side authentication/authorization, civic-report privacy, public surface, defaults. Method: runtime route/dependency introspection (`tools/route_inventory.py`), reading handlers, and executing regression tests against an isolated local PostgreSQL/PostGIS test database. No production data was used. Severity = likelihood x impact as judged from code; **"Reproduced" means a test failed on the original code and passes on the fixed code.**

## Findings

| # | Sev | Finding | Where | Reproduced | Status |
|---|---|---|---|---|---|
| S1 | **High** | **Citizens could list every citizen's civic reports.** `only_mine` defaulted to false and was client-controlled, so omitting it returned the city queue including `reporter_id`, ward/location, and evidence `photo_url`. The single-report endpoint already returned 404 for non-owners, so the list contradicted the intended rule. | `api/v1/endpoints/civic.py` `list_civic_issues` | **Yes** (test fails on original code) | **Fixed** (citizens always scoped to own). UI "All Reports" toggle removed. |
| S2 | **High** | **Any authenticated user (incl. citizens) could create and read drone flight plans.** `POST /drone/plan` persists rows (unbounded writes); `GET /drone/plans` and `/plans/{id}/geojson` expose operational inspection plans. | `api/v1/endpoints/drone.py` | **Yes** | **Fixed** (ADM/OFF/INS). No frontend caller existed. |
| S3 | **High** | **Demo accounts with publicly documented passwords are provisioned in every environment, including production.** | `main.py` lifespan -> `core/seeder.py ensure_demo_users` | Config logic tested; startup path not exercised end-to-end | **Fixed by default** (`SEED_DEMO_USERS`: auto = off in production; explicit opt-in). **Assumption:** you did not answer the open question; a hosted demo now needs `SEED_DEMO_USERS=true`. Credentials remain in source/README (see R1). |
| S4 | Medium | `/api/v1/metrics` unauthenticated. (Correction to an earlier note: the rate-limit skip list matches `/metrics`, not `/api/v1/metrics`, so it **is** rate limited.) Exposes default process metrics only; no custom metrics registered. | `endpoints/metrics.py` | Yes (policy test) | **Fixed** (`METRICS_TOKEN`; 404 in production if unset). |
| S5 | Medium | Frontend/backend role mismatch: Analytics, Simulator, AI Agents tabs and `/dashboard/reports` visible/reachable to inspectors (and AI Agents to citizens) but backed by `RequireAnalyst` APIs, producing 403 dead ends. Backend was already correct. | `frontend/lib/module-access.ts`, sidebar, pages | Backend 403 verified by test; UI behaviour by code read/typecheck (no browser run) | **Fixed** in UI via `lib/role-policy.ts` (mirrors backend). |
| S6 | Medium | IVR webhook is unauthenticated and does not validate the Twilio signature; alert id is a UUID. Returns alert text only. | `endpoints/notifications.py` | Not tested | **Open.** Validate `X-Twilio-Signature` when Twilio is configured. |
| S7 | Medium | Evidence photos served from `/media` without authentication; protection is URL secrecy only. S1 previously leaked those URLs to all citizens. | `main.py` static mount | Not tested | **Open** (S1 removes the main leak). Consider authenticated/signed media route. |
| S8 | Low | `/docs`, `/redoc`, `/openapi.json` public in production. `/health` returns dependency error strings. | `main.py` | Not tested | Open. |
| S9 | Low | Login has only a global per-IP rate limit (keyed on socket IP, so shared behind a proxy); no per-account lockout. Rate limiter **fails open** when Redis is down. | `core/middleware.py` | Not tested | Open. |
| S10 | Low | WebSocket accepts any active user for any city. Nothing broadcasts to it today, so no data exposure currently. | `endpoints/websocket.py` | Not tested | Open (enforce city/role before first broadcaster ships). |
| S11 | Low | `RequireOfficer`/`RequireInspector` names are inverted relative to their role sets (see matrix). Maintainability risk that already caused one wrong edit. | `api/deps.py` | n/a | Open (rename). |
| S12 | Info | A stale comment in `deps.py` claimed inspectors/citizens "don't see" Analytics/AI nav items. Not true until the S5 fix. | `api/deps.py` | n/a | Comment still stale; update with S11. |

## Verified as correct (no change)
- `POST /auth/register` always yields `citizen` even when the body carries `role: city_administrator` (test added).
- Citizen cannot fetch another citizen's single report (404), verify it (403), change status (403), or resolve it (403).
- Analyst-only routers (`/reports`, `/analytics`, `/agents`, `/simulator`) reject inspector and citizen; admin-only writes reject officer/inspector/citizen (tests added).
- `POST /alerts` and `POST /enforcement` reject citizens (in-handler checks).

## Not verified / limits
- No dynamic scanning, fuzzing or dependency CVE audit was run. JWT handling, password hashing parameters and token revocation were not reviewed in depth.
- CORS and security headers were read, not tested.
- Notification ownership scoping is code-read only.
- `crewai`/`weasyprint` code paths were not installed or tested.

## Prioritised unresolved risks
1. **R1 (High):** Demo credentials exist in source and README; anyone enabling `SEED_DEMO_USERS` in a reachable environment exposes an admin account. Rotate/randomise via env-supplied passwords. Owner: Rohan.
2. S6 Twilio signature validation. Owner: Rohan.
3. S7 authenticated media. Owner: Rohan + Adwait (frontend must send auth for images).
4. S9 login lockout / trusted-proxy IP handling / fail-closed on auth routes. Owner: Rohan.
5. Product decision on citizen visibility of city-wide operational reads (matrix). Owner: Aryan.
6. S8, S10, S11. Owner: Rohan.
