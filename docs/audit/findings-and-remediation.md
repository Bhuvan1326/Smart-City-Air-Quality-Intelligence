# Findings & Remediation — Week 1 + Week 2 Audit

Severity scale: **P0** critical (security/data-integrity/app-breaking), **P1** high, **P2** medium, **P3** low.

## Fixed in this audit

### AUD-001 — P0 — Application cannot start: `api_router` import fails

- **File:** `backend/app/api/v1/__init__.py`
- **Reproduce:** `python -c "from app.main import app"` → `ImportError: cannot import name 'api_router' from 'app.api.v1'`
- **Root cause:** Commit `3d0c88b` ("Smart-City") emptied the package `__init__.py` — the module that aggregated every endpoint router into `api_router`. `main.py` imports it unconditionally.
- **Impact:** 100% startup failure — no endpoint served, including `/health`. Any "passing" evidence produced after that commit is invalid.
- **Fix:** Restored the full aggregator — all endpoint routers incl. Week-2 `kpi` and `media_links`, `api_router = APIRouter(prefix="/api/v1")`.
- **Verification:** `from app.main import app` → **121 routes** (122 after AUD-005 split); `compileall`/`black`/`isort`/`ruff` pass; contract check clean.
- **Regression coverage:** Import is exercised by every `client`-fixture test and by `dump_openapi`; recommend adding an explicit `test_app_imports` smoke test that is *not* integration-marked so the no-DB lane catches a recurrence.

### AUD-002 — P1 — Frontend typecheck fails: `extractErrorMessage` not exported

- **File:** `frontend/lib/utils.ts`
- **Reproduce:** `npx tsc --noEmit` → `Module '"@/lib/utils"' has no exported member 'extractErrorMessage'` from 6 files (agents, citizen, civic, enforcement, simulator pages, Navbar).
- **Root cause:** Helper existed only as a local function in one component; call sites import it from the shared util module where it was never added.
- **Fix:** Exported `extractErrorMessage(err: unknown)` — safely reads `response.data.detail`/`response.data.message`, falls back to `"Something went wrong."`
- **Verification:** `tsc --noEmit` exit 0; `npm run build` PASS; 49/49 tests pass.

### AUD-003 — P2 — `test_traffic_provider.py` fails on Windows

- **File:** `backend/app/tests/test_traffic_provider.py`
- **Reproduce:** pytest on Windows → path-assertion mismatch, then `NameError: name 'Path' is not defined` after first fix.
- **Root cause:** POSIX-style absolute-path assumption plus missing `from pathlib import Path`.
- **Fix:** `Path`-based absolute path construction + import.
- **Verification:** file passes inside the 34-test targeted run and the 691-test no-DB lane.

### AUD-004 — P2 — `twilio` required at runtime but undeclared

- **Files:** `backend/requirements.txt`, `backend/pyproject.toml`, `backend/app/services/notifications/twilio_service.py`
- **Reproduce:** `pip show twilio` → not found; `TwilioService._get_client()` / `build_ivr_twiml()` do `from twilio.rest import Client` / `from twilio.twiml.voice_response import VoiceResponse` → `ImportError` the moment `TWILIO_ENABLED=true`.
- **Impact:** Outbound SMS/calls and IVR TwiML crash on a clean install; inbound signature validation unaffected (stdlib implementation by design).
- **Fix:** Pinned `twilio==9.10.9` in both manifests; installed in `.venv`.
- **Verification:** `build_ivr_twiml("test alert")` returns valid TwiML; `test_matches_official_twilio_sdk_algorithm` (previously skipped via `importorskip`) **now executes and passes** — the stdlib signature algorithm is verified against the official `RequestValidator`.

### AUD-005 — P3 — Duplicate OpenAPI operation ID for IVR webhook

- **File:** `backend/app/api/v1/endpoints/notifications.py`
- **Reproduce:** `app.openapi()` → `UserWarning: Duplicate Operation ID ivr_twiml_webhook_…` (GET+POST shared one `api_route` function).
- **Fix:** Split into `ivr_twiml_webhook_get`/`ivr_twiml_webhook_post` over a shared `_ivr_twiml_response` helper; signature dependency unchanged.
- **Verification:** `app.openapi()` → 115 operations, **0 duplicates, no warnings**; routes 121→122; contract check still 0 errors.

### Working-file repair (mid-edit breakage)

- **File:** `frontend/lib/utils.ts` — an editor session left a dangling ` * … */` comment fragment and a duplicated `AQI_BANDS`/`AQIBand` block (tsc-breaking). Removed the duplicate, preserved the newly added `AQI_MAX` constant and the pre-existing `AQI_SCALE_MAX`. `tsc` clean, tests pass.

## Documented — not modified

### AUD-006 — P3 — Redis tests unmarked for the no-DB lane

`test_redis_client_thread_safety.py` (2 tests) issues real `SET/GET` against `localhost:6379` but is not `integration`-marked, so `pytest -m "not integration"` can never go green without Redis. `pytest.ini` defines the marker as Postgres-specific, so these were **left unmodified and classified environment-blocked**; recommend either a `redis` marker or `skipif` on connectivity. CI has a Redis service → passes there by design.

### N2 — P3 — Cross-user notification ops return 403 (ID-existence confirmation)

Ownership checks are enforced, but a valid ID belonging to another user returns 403 rather than 404 — an enumeration nuance. Contract is documented; changing to 404 is a deliberate contract decision (owner: Rohan).

### `callsWithoutTypedResponse: 1`

One frontend API call lacks a typed response; contract checker counts it as an allowance, not an error. Recommend typing it to reach zero.

## Confirmed-open security items (match prior docs — do not silently close)

| ID | Item | State |
|---|---|---|
| S9 | Per-account login lockout; rate limiter fails closed | Not implemented — `RateLimitMiddleware` fails **open** on Redis outage by code comment; no lockout counter |
| S10 | WebSocket per-city authorization | Token authn only; any user may subscribe to any city (`/ws/live/{city}`) |
| — | Impact Ledger / City Action Brief | Design-only: `InterventionOutcome` written solely by `seeder`; `confidence_score` default `0.8` still in `enforcement.py` |
| — | `weather_measurements` | Dead table — migration exists, no model/writer; weather-persistence decision unresolved |
| — | Stored-forecast `artifact_id` | API returns `model_artifact` in response; DB-row linkage absent |
| — | Existing model artifacts | 9 joblibs, **no `.meta.json`** sidecars (predate tooling; retraining was intentionally deferred) |

## Verification commands (re-run)

```bash
cd backend && .venv/Scripts/python -m compileall -q app
.venv/Scripts/python -m black --check app && .venv/Scripts/python -m isort --check-only app && .venv/Scripts/python -m ruff check app
.venv/Scripts/python -m pytest -m "not integration" -q          # 691 passed, 2 env-fail
cd ../frontend && npm test && npx tsc --noEmit && npx eslint . && npm run build && npm run contract:check
```
