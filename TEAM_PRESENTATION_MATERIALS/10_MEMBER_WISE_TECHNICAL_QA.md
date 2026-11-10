# Member-wise Technical Q&A

## Member 1 — Ingestion & Geo
1. **Where does station data come from?** OpenAQ v3 — discovered locations + latest measurements via scheduled ingestion.
2. **How do stations get their state?** `india_state_lookup.py` ray-casts coords over 36 real state/UT polygons + 25km coastal fallback — no name guessing.
3. **How do you avoid duplicates?** `openaq_location_id` uniqueness + adopt-before-insert; ingestion is idempotent.
4. **What is quality_flag?** good/stale/synthetic/invalid — drives the real-vs-demo separation everywhere.
5. **Why do real hotspots return empty?** Only ~19 fresh readings — below the spatial+temporal minimum; honest empty, not fabricated.
6. **How is the map built?** Mapbox GL JS 3.8, GeoJSON markers, popups, layer toggles, hardened style lifecycle + retry.
7. **How many stations/states?** 775 stations, 33 states/UTs.
8. **How do you handle OpenAQ rate limits?** Request pacing, local wait on limits, backoff, lock-free dedupe.
9. **What if a coordinate is invalid/outside India?** Rejected/unknown state — never guessed.
10. **Why did stations initially lack states?** OpenAQ doesn't expose state — derived from boundaries instead.
11. **How fresh is 'fresh'?** Timestamp-age classification: current/stale per policy.
12. **Can users see synthetic data?** Yes — opt-in `include_synthetic`, always labeled demo.
13. **What's PostGIS used for?** Nearest-station, buffer analysis, spatial clustering, geometry storage.
14. **How does India discovery scale?** Bounded pagination + resume checkpoints.
15. **What happens if OpenAQ is down?** Graceful ingest failure + last-good data retained + error surfaced.

## Member 2 — Forecasting & Attribution
1. **What model forecasts AQI?** XGBoost regression, versioned `xgb_forecast_*.joblib` registry.
2. **How do you prevent leakage?** Chronological train/test split.
3. **What if the model file is missing?** Statistical fallback — never a crash.
4. **Why no station-level forecast?** BLOCKED: 1–2 real obs/station; hundreds needed — documented, not faked.
5. **What's the horizon/metrics?** Hour-ahead city forecast; MAE/RMSE recorded vs. naive baseline.
6. **How is source attribution computed?** Receptor model v1.2 — per-ward % split of 6 sources.
7. **What if no attribution exists?** Live-fallback → estimated values labeled "model-derived estimate".
8. **Why is city case-insensitive?** `pune`/`mumbai` previously 500'd/emptied — fixed via `func.lower` match.
9. **What's `quality_flag`'s role?** Only `good`/`stale` real readings train/feed forecasts — synthetic excluded.
10. **How are evaluation results stored?** Model metadata sidecar + `model_performance` endpoint.
11. **How does analytics differ from forecast?** Analytics describes (trends/comparison/dispersion); forecast predicts.
12. **What's exposure analysis?** Population-weighted ward exposure — currently demo-only (needs real readings).
13. **What is replay/simulator?** Historical scenario playback + what-if simulation over stored readings.
14. **How often does attribution recompute?** Every 30 minutes (`run-attribution` job).
15. **Accuracy guarantees?** Reported honestly per model version; no fabricated confidence intervals.

## Member 3 — AI
1. **What is Nugen?** An alignment platform — our Qwen2.5-0.5B base was aligned and deployed as `model_01m6xbrq3n8fa8kk`.
2. **Is inference real?** Yes — real requests to the deployed aligned model, not a mock.
3. **What does the validator check?** Numeric provenance, pollutant identity, units, CPCB band, exercise safety, missing data.
4. **What if the model states a wrong number?** Surgically replaced in place or the claim is removed — never left beside a correction.
5. **What's the 8-scenario eval?** Good/moderate/poor/severe AQI, PM-swap, admin recs, missing-data, outdoor — 8/8 clean pass evidence.
6. **Is the key exposed?** No — backend-only env; browser talks to our endpoint only.
7. **What does geographic insight do?** Explains a selected station/hotspot using only its real measurements.
8. **What's the fallback?** Deterministic validated summary when output is unrepairable.
9. **Gemini vs Nugen?** Assistant chat = Gemini; air-quality insights = aligned Nugen — separate paths.
10. **3B model status?** BLOCKED — provider won't deploy the Qwen2.5-3B base; documented.
11. **Anthropic?** Key configured; not yet wired to a live path — flagged unverified.
12. **LangGraph agents?** Analyst-only multi-step agent framework — partial.
13. **How is safety enforced?** Deterministic CPCB band + exercise-safety rules + validation before response.
14. **Can the model hallucinate an AQI?** Blocked — no-supplied-measurement → deterministic unavailable notice.
15. **What are validation_notes?** Per-response log of corrections applied — returned to the client.

## Member 4 — Environmental
1. **Where does weather come from?** Open-Meteo (keyless), 15-min ingest into `weather_measurements`.
2. **What does the heat module show?** `heat_readings` ward heat-island indicators + map.
3. **Satellite data?** NASA FIRMS fire detections → `satellite_observations` (verified working).
4. **Sentinel status?** INVALID credentials (OAuth 401) — documented, not hidden.
5. **Energy data source?** Configured CSV/provider — data depth varies.
6. **Construction dust?** Site/source registry feeding dust attribution + hotspots.
7. **Industrial pollution?** Emission-source records → `hotspot-clusters` layer.
8. **Waste modules?** Burning incidents + circularity metrics.
9. **Traffic?** Traffic-pollution, mobility, smart-mobility analysis pages.
10. **How does environment feed AQI logic?** Weather → dispersion/freshness; emission sources → hotspot evidence.
11. **Why PARTIAL?** Mixed data depth — real pipelines + some estimated surfaces.
12. **Green infrastructure?** Recommendation logic for mitigating interventions.
13. **Water module?** City water-resource monitoring.
14. **Missing provider impact?** Only the Sentinel-imagery path is blocked; everything else functional.
15. **What's the biggest gap?** Denser real environmental observations — same as the whole platform.

## Member 5 — Civic & Enforcement
1. **Civic issue flow?** Submit → cluster → assign → inspect+evidence → enforce → notify → status events.
2. **How are citizens scoped?** Server-side: own city + own records only.
3. **Escalation?** 15-min job auto-escalates SLA-breaching issues.
4. **Evidence?** Photo upload + verification via media storage.
5. **Who creates enforcement actions?** Officers/admin; inspectors submit evidence.
6. **Drone role?** Flight plans + hotspot detection for field ops.
7. **Officer routes?** Inspection assignments per officer/ward.
8. **Notifications?** Threshold breaches → pending alerts → 1-min dispatch; websocket channel.
9. **Thresholds?** Admin-configured pollutant alert thresholds per city.
10. **Mitigation?** Recommendation engine per issue/aqi.
11. **What tracks issue history?** `civic_issue_status_events` — full audit trail.
12. **What if Firebase/SMTP is broken?** Documented — those channels degrade gracefully (config-broken).
13. **Citizen vs inspector vs officer?** Citizen reports; inspector verifies; officer enforces.
14. **Status?** PARTIAL — real flows verified; field workflows less exercised.
15. **Geographic clustering?** Issues cluster spatially to link repeat complaints to hotspots.

## Member 6 — Auth & Admin
1. **How does auth work?** JWT access + single-flight refresh rotation, bcrypt, secure cookies.
2. **Roles?** city_administrator, pollution_control_officer, field_inspector, citizen.
3. **How enforced?** `require_roles` deps; citizens get row-level city/record scoping.
4. **Frontend mirror?** `lib/role-policy.ts` gates nav/modules to match backend.
5. **New admin endpoints?** `/admin/errors(+summary)`, `/admin/users/statistics`, `/admin/system/statistics`, `/admin/system/health`, `/admin/audits` — all RequireAdmin.
6. **Error tracking source?** `audit_logs` via `AuditLogMiddleware` — real captured 4xx/5xx.
7. **Security audit findings?** 0 critical, 1 high (invalid Sentinel creds), 3 medium, 2 low — real evidence.
8. **Reliability audit?** 14/14 endpoints passed, noauth→403, invalid→422, real latencies.
9. **User stats honesty?** `is_active` flag + last_login presence noted — no fabricated "active" count.
10. **Rate limiting?** Redis-backed middleware + login throttle.
11. **Seeder?** Resumable/idempotent — skips existing records, no deletes.
12. **Audit logging?** Every mutating request → `audit_logs` (user, action, response code).
13. **System health?** Live checks — db/redis/xgboost/openaq/nugen/mapbox.
14. **Broken configs?** Sentinel/Firebase/SMTP documented as unavailable, not hidden.
15. **Docker/CI?** Compose stack (backend/frontend/db/redis/migrate) + Black/isort/Ruff/pytest/coverage CI.
