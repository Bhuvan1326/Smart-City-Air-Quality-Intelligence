import json
rows=json.load(open('docs/week-1/tools/routes.json'))
ab={'city_administrator':'ADM','pollution_control_officer':'OFF','field_inspector':'INS'}
api=[r for r in rows if r[0].startswith('/api/v1') and r[2]!='(mount/ws)']
def yn(rs,r): return 'Y' if r in rs else '-'
L=["# Role-Permission Matrix (Admin / Officer / Inspector / Citizen)\n",
"Generated 2026-10-09 by introspecting the **running FastAPI app** (`app.routes` + each route's dependency tree), not by reading frontend navigation. Source of truth: `backend/app/api/deps.py`. Regenerate with `docs/week-1/tools/gen_docs1.py`.\n",
"**Legend:** `Y` = allowed by the route dependency; `-` = rejected with 403. Routes that pass only `get_current_user` are listed separately because any further restriction lives inside the handler. ADM=city_administrator, OFF=pollution_control_officer, INS=field_inspector, CIT=citizen.\n",
"> **Dependency names (renamed in Week 2 so names match behaviour):** `RequireStaff` = ADM+OFF+INS, `RequireInspectorOnly` = INS only, `RequireAnalyst` = ADM+OFF, `RequireAdmin` = ADM. (Before Week 2, `RequireOfficer` meant all staff and `RequireInspector` meant inspector-only. A before/after runtime snapshot of all 121 route/role entries was identical.)\n",
"## Dependency-level role gates\n","| Method | Path | ADM | OFF | INS | CIT |\n|---|---|---|---|---|---|"]
for p,m,a,n in api:
    if a.startswith('ROLES'):
        rs=set(a.replace('ROLES:','').split('|'))
        L.append(f"| {m} | `{p[7:]}` | {yn(rs,'city_administrator')} | {yn(rs,'pollution_control_officer')} | {yn(rs,'field_inspector')} | - |")
notes={'/api/v1/auth/login':'Global per-IP rate limit only; no per-account lockout.','/api/v1/auth/register':'Always creates `citizen`; a `role` in the body is ignored (regression-tested).','/api/v1/auth/refresh':'Requires a valid refresh token.','/api/v1/metrics':'Token-protected / 404 in production after Week 1 fix.','/api/v1/notifications/ivr/{alert_id}':'Twilio webhook; unauthenticated, no signature validation; returns alert text. OPEN RISK (medium/low).'}
L+=["\n## Public (unauthenticated) API routes\n","| Method | Path | Notes |\n|---|---|---|"]
for p,m,a,n in api:
    if a=='PUBLIC': L.append(f"| {m} | `{p[7:]}` | {notes.get(p,'')} |")
L.append("\nOutside `/api/v1`: `GET /health` (public; reports dependency status), `/docs` `/redoc` `/openapi.json` (public in every environment; see audit), `/media/*` static evidence files (**unauthenticated**; protected only by unguessable URLs), WebSocket `/api/v1/ws/live/{city}` (token required, any active user, any city; nothing in application code currently broadcasts to it).\n")
L+=["## Handler-level rules (routes that pass `get_current_user` only)\n","| Endpoint | Rule enforced in handler | Verified by |\n|---|---|---|",
"| `POST /alerts` | CIT -> 403 | code read + `test_citizen_cannot_use_staff_write_routes` |",
"| `POST /enforcement` | CIT -> 403 | code read + same test |",
"| `GET /civic/issues` | CIT sees **only own** reports (server-enforced since Week 1); staff see the city queue | `test_citizen_list_never_includes_other_citizens_reports`, `test_staff_still_see_full_queue` |",
"| `GET /civic/issues/{id}` | CIT -> 404 unless reporter | `test_citizen_cannot_read_or_act_on_another_citizens_report` |",
"| `POST /civic/issues/{id}/citizen-verify` | only the reporter, else 403 | same test |",
"| `/notifications/*` | queries scoped to `current_user.id` | code read only; no dedicated test (Week 2) |",
"| `/drone/*` | ADM+OFF+INS (fixed in Week 1; previously any authenticated user) | `test_drone_planning_is_staff_only` |",
"| `GET/POST /notifications/ivr/{id}` | valid `X-Twilio-Signature` (Week 2; public route, fail-closed) | `test_week2_ivr_signature.py` |",
"| `GET /media/evidence/...` | staff: any; citizen: own issues only; else 404; or valid signed link (Week 2) | `test_week2_media_access.py` |",
"\n## Authenticated routes with no role restriction (any role including citizen)\n","| Method | Path |\n|---|---|"]
for p,m,a,n in api:
    if a=='ANY_AUTHENTICATED': L.append(f"| {m} | `{p[7:]}` |")
L.append("\n**Needs a product decision (not changed):** whether citizens should be able to read `/sources`, `/exposure/*`, `/sensors/health*`, `/gis/*`, `/replay/*` and similar city-wide operational data. They currently can.\n")
L.append("## Action-class summary\n\n| Action class | ADM | OFF | INS | CIT |\n|---|---|---|---|---|\n| Read air quality, forecast, alerts | Y | Y | Y | Y |\n| Read analytics, reports; run simulator, AI agents | Y | Y | - | - |\n| List/create/update enforcement, upload evidence | Y | Y | Y | - |\n| Create alert | Y | Y | Y | - |\n| Alert thresholds, municipalities, ward offices/boundaries/representatives, demographics, water resources (writes) | Y | - | - | - |\n| Triage/resolve civic issue | Y | Y | Y | - |\n| Submit civic issue; verify own resolution | Y | Y | Y | Y (own only) |\n| Run civic escalation | Y | - | - | - |\n| Assignment | No dedicated assignment endpoint exists; status transitions are the only workflow lever. |\n")
open('rbac-permission-matrix.md','w').write('\n'.join(L))
C=["# API Contracts (as implemented)\n","Generated from the running app on 2026-10-09 and cross-checked against `frontend/lib/api/services.ts`. Field-level request/response schemas are the Pydantic models in `backend/app/schemas/*` and the live `/openapi.json`; they are not duplicated here to avoid drift. Success envelope: `APIResponse[T]`; HTTP errors use FastAPI's default `{\"detail\": ...}`.\n",
"**Auth:** `Authorization: Bearer <access_token>` from `POST /api/v1/auth/login`; refresh via `/auth/refresh`. Absent token -> 403 (`HTTPBearer`), invalid token -> 401, wrong role -> 403 `Access requires one of: [...]`.\n",
f"**Count:** {len(api)} HTTP route/method pairs under `/api/v1`.\n","## Endpoint inventory\n","| Method | Path | Handler | Auth |\n|---|---|---|---|"]
for p,m,a,n in api:
    au='public' if a=='PUBLIC' else ('any user' if a=='ANY_AUTHENTICATED' else '/'.join(ab[r] for r in a.replace('ROLES:','').split('|')))
    C.append(f"| {m} | `{p[7:]}` | `{n}` | {au} |")
C+=["\n## Frontend <-> backend consistency check (mechanical)\n","Method: regex-extracted every helper call (`get/post/patch/del/...`) in `frontend/lib/api/services.ts` (84 distinct calls), normalised path parameters, and compared with the runtime route table. **Result: all 84 match an existing backend path and HTTP method.** (One apparent miss, `POST /civic/escalation/run${city ...}`, is a regex artefact of a template literal containing an inline query; the backend route exists.) This verifies **paths and methods only**. Field-level shapes were not diffed (open item).\n",
"Backend routes with no caller in `services.ts` (informational): `/agents/run-graph`, `/aqi/india`, `/aqi/stations`, `/auth/refresh` (axios interceptor), `/civic/{escalation/run,municipalities,representatives,ward-boundaries,ward-offices}`, `/drone/*`, `/enforcement/{id}/evidence`, `/gis/*`, `/metrics`, `/notifications` (list), `/notifications/ivr/{id}`, `/notifications/push-token`, `/reports/export`, `/sensors/health*`, `/ws/live/{city}`. Some are called from components outside `services.ts`; not individually verified.\n",
"## Contract changes made in Week 1\n\n| Endpoint | Change | Compatibility |\n|---|---|---|\n| `GET /civic/issues` | Citizens always receive only their own reports; `only_mine` ignored for citizens | Schema unchanged. Behavioural change for citizens only; the UI toggle was removed accordingly. |\n| `/drone/plan`, `/drone/plans`, `/drone/plans/{id}/geojson` | 403 for citizens (previously any authenticated user) | No frontend caller exists. |\n| `GET /metrics` | Requires `Authorization: Bearer $METRICS_TOKEN` if set; 404 in production if unset | Dev unchanged. A production Prometheus scraper must be given the token. |\n| App startup | Demo users no longer seeded in production unless `SEED_DEMO_USERS=true` | Dev/staging unchanged. |\n",
"## Forecast contract (defects in `forecasting-audit.md`)\n\n- Served by `app/ml/inference.py` from the newest `ml_models/xgb_forecast_*.joblib`; **statistical fallback** if no artifact loads.\n- Target: ward-level **AQI** (CPCB-style index, unitless, 0-500), 1-hour model applied **recursively** to reach horizon *h*. Spatial unit: ward id (`W01`...).\n- Model input, 8 features, positional (artifacts store no feature names; `n_features_in_ = 8` verified on the shipped files): `[current_aqi, hour_of_day, day_of_week, is_weekend, is_industrial, temperature, humidity, wind_speed]`. Training (`workers/tasks/forecast.py`) and inference use the same order.\n- Response includes `predicted_aqi`, a **heuristic** confidence and interval (not calibrated) and `pm25_forecast` (= 0.55 x AQI; not a measured conversion).\n- Unavailable model: statistical fallback, with random noise (non-deterministic). Responses do not say which path produced the value.\n",
"## Unresolved contract decisions\n\n1. A privacy-preserving public community issue feed for citizens (no reporter id or photo), since the old All Reports view was removed.\n2. Add `source: model|statistical_fallback` and `generated_at` to forecast responses.\n3. Standard error envelope.\n4. Field-level contract tests (schema diff between `schemas/*.py` and `services.ts`).\n"]
open('api-contracts.md','w').write('\n'.join(C))
print('ok')
