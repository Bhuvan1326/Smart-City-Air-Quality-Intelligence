# Role-Permission Matrix (Admin / Officer / Inspector / Citizen)

Generated 2026-10-09 by introspecting the **running FastAPI app** (`app.routes` + each route's dependency tree), not by reading frontend navigation. Source of truth: `backend/app/api/deps.py`. Regenerate with `docs/week-1/tools/gen_docs1.py`.

**Legend:** `Y` = allowed by the route dependency; `-` = rejected with 403. Routes that pass only `get_current_user` are listed separately because any further restriction lives inside the handler. ADM=city_administrator, OFF=pollution_control_officer, INS=field_inspector, CIT=citizen.

> **Dependency names (renamed in Week 2 so names match behaviour):** `RequireStaff` = ADM+OFF+INS, `RequireInspectorOnly` = INS only, `RequireAnalyst` = ADM+OFF, `RequireAdmin` = ADM. (Before Week 2, `RequireOfficer` meant all staff and `RequireInspector` meant inspector-only. A before/after runtime snapshot of all 121 route/role entries was identical.)

## Dependency-level role gates

| Method | Path | ADM | OFF | INS | CIT |
|---|---|---|---|---|---|
| GET | `/agents/carbon-estimate` | Y | Y | - | - |
| GET | `/agents/carbon-estimate/enforcement` | Y | Y | - | - |
| GET | `/agents/model-registry` | Y | Y | - | - |
| POST | `/agents/run` | Y | Y | - | - |
| POST | `/agents/run-graph` | Y | Y | - | - |
| GET | `/agents/status` | Y | Y | - | - |
| POST | `/alerts/thresholds` | Y | - | - | - |
| DELETE | `/alerts/thresholds/{threshold_id}` | Y | - | - | - |
| PATCH | `/alerts/thresholds/{threshold_id}` | Y | - | - | - |
| GET | `/analytics` | Y | Y | - | - |
| GET | `/analytics/comparison` | Y | Y | - | - |
| POST | `/civic/escalation/run` | Y | - | - | - |
| POST | `/civic/issues/{issue_id}/resolve` | Y | Y | Y | - |
| PATCH | `/civic/issues/{issue_id}/status` | Y | Y | Y | - |
| POST | `/civic/municipalities` | Y | - | - | - |
| POST | `/civic/representatives` | Y | - | - | - |
| POST | `/civic/ward-boundaries` | Y | - | - | - |
| POST | `/civic/ward-offices` | Y | - | - | - |
| POST | `/drone/plan` | Y | Y | Y | - |
| GET | `/drone/plans` | Y | Y | Y | - |
| GET | `/drone/plans/{plan_id}/geojson` | Y | Y | Y | - |
| GET | `/enforcement` | Y | Y | Y | - |
| GET | `/enforcement/{action_id}` | Y | Y | Y | - |
| PATCH | `/enforcement/{action_id}` | Y | Y | Y | - |
| POST | `/enforcement/{action_id}/evidence` | Y | Y | Y | - |
| POST | `/exposure/demographics` | Y | - | - | - |
| PATCH | `/exposure/demographics/{demographics_id}` | Y | - | - | - |
| GET | `/reports` | Y | Y | - | - |
| POST | `/reports/export` | Y | Y | - | - |
| POST | `/simulator/whatif` | Y | Y | - | - |
| POST | `/water/resource` | Y | - | - | - |
| PATCH | `/water/resource/{resource_id}` | Y | - | - | - |

## Public (unauthenticated) API routes

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/login` | Global per-IP rate limit only; no per-account lockout. |
| POST | `/auth/refresh` | Requires a valid refresh token. |
| POST | `/auth/register` | Always creates `citizen`; a `role` in the body is ignored (regression-tested). |
| GET | `/metrics` | Token-protected / 404 in production after Week 1 fix. |
| GET | `/notifications/ivr/{alert_id}` | Twilio webhook; unauthenticated, no signature validation; returns alert text. OPEN RISK (medium/low). |
| POST | `/notifications/ivr/{alert_id}` | Twilio webhook; unauthenticated, no signature validation; returns alert text. OPEN RISK (medium/low). |

Outside `/api/v1`: `GET /health` (public; reports dependency status), `/docs` `/redoc` `/openapi.json` (public in every environment; see audit), `/media/*` static evidence files (**unauthenticated**; protected only by unguessable URLs), WebSocket `/api/v1/ws/live/{city}` (token required, any active user, any city; nothing in application code currently broadcasts to it).

## Handler-level rules (routes that pass `get_current_user` only)

| Endpoint | Rule enforced in handler | Verified by |
|---|---|---|
| `POST /alerts` | CIT -> 403 | code read + `test_citizen_cannot_use_staff_write_routes` |
| `POST /enforcement` | CIT -> 403 | code read + same test |
| `GET /civic/issues` | CIT sees **only own** reports (server-enforced since Week 1); staff see the city queue | `test_citizen_list_never_includes_other_citizens_reports`, `test_staff_still_see_full_queue` |
| `GET /civic/issues/{id}` | CIT -> 404 unless reporter | `test_citizen_cannot_read_or_act_on_another_citizens_report` |
| `POST /civic/issues/{id}/citizen-verify` | only the reporter, else 403 | same test |
| `/notifications/*` | queries scoped to `current_user.id` | code read only; no dedicated test (Week 2) |
| `/drone/*` | ADM+OFF+INS (fixed in Week 1; previously any authenticated user) | `test_drone_planning_is_staff_only` |
| `GET/POST /notifications/ivr/{id}` | valid `X-Twilio-Signature` (Week 2; public route, fail-closed) | `test_week2_ivr_signature.py` |
| `GET /media/evidence/...` | staff: any; citizen: own issues only; else 404; or valid signed link (Week 2) | `test_week2_media_access.py` |

## Authenticated routes with no role restriction (any role including citizen)

| Method | Path |
|---|---|
| GET | `/alerts` |
| POST | `/alerts` |
| GET | `/alerts/thresholds` |
| POST | `/aqi/compare-routes` |
| GET | `/aqi/health-risk` |
| GET | `/aqi/history` |
| GET | `/aqi/india` |
| GET | `/aqi/india/heatmap` |
| GET | `/aqi/india/states` |
| GET | `/aqi/live` |
| GET | `/aqi/recommend-locations` |
| GET | `/aqi/route-analysis` |
| GET | `/aqi/stations` |
| GET | `/aqi/traffic-pollution` |
| POST | `/assistant/chat` |
| GET | `/attribution/history` |
| GET | `/attribution/live` |
| POST | `/auth/logout` |
| GET | `/auth/me` |
| GET | `/civic/issues` |
| POST | `/civic/issues` |
| GET | `/civic/issues/{issue_id}` |
| POST | `/civic/issues/{issue_id}/citizen-verify` |
| GET | `/civic/municipalities` |
| GET | `/civic/representatives` |
| GET | `/civic/ward-offices` |
| GET | `/dashboard/overview` |
| GET | `/energy/fuel-mix` |
| GET | `/energy/grid-carbon-intensity` |
| GET | `/energy/renewable-trend` |
| POST | `/enforcement` |
| GET | `/exposure/demographics` |
| GET | `/exposure/map` |
| GET | `/forecast` |
| GET | `/forecast/{ward_id}` |
| GET | `/gis/buffer-analysis` |
| GET | `/gis/geofence-check` |
| GET | `/gis/hotspot-clusters` |
| GET | `/gis/nearest-stations` |
| GET | `/gis/pollution-hotspots` |
| GET | `/gis/route-optimise` |
| GET | `/gis/ward-boundaries` |
| GET | `/green-infrastructure/priority` |
| GET | `/heat/current` |
| GET | `/heat/forecast` |
| GET | `/heat/history` |
| GET | `/heat/hourly` |
| GET | `/heat/wards` |
| GET | `/kpi/data-freshness` |
| POST | `/media/signed-url` |
| GET | `/mitigation/recommendations` |
| GET | `/model-performance/active` |
| GET | `/model-performance/history` |
| GET | `/notifications` |
| POST | `/notifications/push-token` |
| POST | `/notifications/read-all` |
| GET | `/notifications/unread-count` |
| DELETE | `/notifications/{notification_id}` |
| POST | `/notifications/{notification_id}/read` |
| GET | `/replay/anomalies` |
| GET | `/replay/aqi-history` |
| GET | `/replay/root-cause-timeline/{anomaly_id}` |
| GET | `/sensors/health` |
| GET | `/sensors/{station_id}/health/history` |
| GET | `/simulator/scenarios` |
| GET | `/simulator/twin/dispersion` |
| GET | `/sources/construction-dust-risk` |
| GET | `/sources/industrial-risk` |
| GET | `/sustainability/score` |
| GET | `/system/data-sources` |
| GET | `/traffic/correlation` |
| GET | `/traffic/current` |
| GET | `/waste-burning/events` |
| GET | `/waste/circularity` |
| GET | `/water/current` |
| GET | `/water/history` |
| GET | `/water/resource` |

**Needs a product decision (not changed):** whether citizens should be able to read `/sources`, `/exposure/*`, `/sensors/health*`, `/gis/*`, `/replay/*` and similar city-wide operational data. They currently can.

## Action-class summary

| Action class | ADM | OFF | INS | CIT |
|---|---|---|---|---|
| Read air quality, forecast, alerts | Y | Y | Y | Y |
| Read analytics, reports; run simulator, AI agents | Y | Y | - | - |
| List/create/update enforcement, upload evidence | Y | Y | Y | - |
| Create alert | Y | Y | Y | - |
| Alert thresholds, municipalities, ward offices/boundaries/representatives, demographics, water resources (writes) | Y | - | - | - |
| Triage/resolve civic issue | Y | Y | Y | - |
| Submit civic issue; verify own resolution | Y | Y | Y | Y (own only) |
| Run civic escalation | Y | - | - | - |
| Assignment | No dedicated assignment endpoint exists; status transitions are the only workflow lever. |
