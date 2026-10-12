# Decisions and Contracts (Aryan)

## B1 assumptions from Week 1 — status
No stakeholder decision has been recorded. Nothing below is marked "accepted".

| Assumption | Implemented as | Status |
|---|---|---|
| Demo users off in production by default | `SEED_DEMO_USERS` auto = off in production. **Week 2 hardened it:** seeding also requires `DEMO_USER_PASSWORD` (>= 12 chars); with it unset no demo user is ever created and no default password exists. | **Awaiting decision** (implemented; reversible via env) |
| ML fix is training-code only; artifacts untouched | Training uses `build_training_frame`/`chronological_split`; the 9 shipped artifacts were not modified or retrained. | **Awaiting decision**. Note the artifacts remain unvalidated (see evaluation status). |
| Frontend aligned to backend roles | `lib/role-policy.ts` mirrors `RequireAnalyst`; tabs/routes hidden or redirected. | **Awaiting decision** |

## Citizen community-feed contract (unresolved, privacy-preserving default kept)
Currently citizens see **only their own** reports (`GET /civic/issues`). No privacy relaxation was introduced. Options for the product owner:

| Option | Citizen sees | Public fields | Never exposed | Server-side rule |
|---|---|---|---|---|
| A (current) | Own reports only | all own fields | others' reports | `reporter_id == caller` |
| B | Own reports (full) + a redacted feed of others' | `issue_type`, `ward_id`, `status`, `created_at`, ward-level (not point) location | `reporter_id`, photo/evidence URLs, free-text description, exact coordinates | separate endpoint + field-level redaction schema; rate limit; no pagination beyond N |
| C | Own reports + aggregate counts per ward/type | counts only | everything per-report | aggregation query only |

Recommendation (not a decision): C or B, behind a new endpoint (never by loosening `GET /civic/issues`). Owner: Aryan with Rohan (privacy review) and Adwait (UI).

## Contract changes introduced in Week 2
| Endpoint / interface | Change | Compatibility |
|---|---|---|
| `GET/POST /notifications/ivr/{alert_id}` | Requires a valid `X-Twilio-Signature` (403 otherwise). Now accepts **POST** as well (Twilio's default for `calls.create(url=...)`; previously GET-only, so real IVR calls would have received 405). | Only Twilio calls it. Requires `TWILIO_AUTH_TOKEN` + `TWILIO_STATUS_CALLBACK_URL` = public base URL. |
| `GET /media/evidence/...` | No longer public. Bearer auth with ownership (staff: any; citizen: own issues; others 404) **or** a valid signed link `?exp=&sig=`. | No frontend caller existed. |
| `POST /api/v1/media/signed-url` | New. Mints a link (default 300 s) for evidence the caller may already read. | additive |
| `GET /api/v1/kpi/data-freshness?city=` | New. K1 KPI (schema `DataFreshnessKPI`). Any authenticated user. | additive |
| Forecast responses | New fields `source` (`trained_model` \| `model_statistical_blend` \| `statistical_fallback`) and `model_artifact` (live path only). `source` is **derived** from `model_version` + horizon by `app/ml/provenance.py`. | additive; frontend treats `source` as optional |
| `/docs`, `/redoc`, `/openapi.json` | Disabled in production unless `ENABLE_API_DOCS=true`. | The CI contract check uses `python -m app.tools.dump_openapi`, not the HTTP endpoint. |
| `/health` | In production, dependency errors are reported as `"error"` (no exception text). | |
| `FORECAST_ALIGN_FEATURES_TO_ORIGIN` | New flag, **default off** (M4). | no behaviour change by default |
| `DEMO_USER_PASSWORD`, `METRICS_TOKEN`, `SEED_DEMO_USERS`, `ENABLE_API_DOCS`, `MEDIA_SIGNED_URL_TTL_SECONDS` | New settings; documented in `.env.example`. | |
| Frontend `authApi.register` type | `role?` removed (backend never accepted it; no callers). | |

## Limitation: forecast artifact provenance for stored forecasts
`forecast_grids` rows do not record which artifact produced them, so `model_artifact` is `null` for stored forecasts. Recording it needs a migration (shared-schema change) — proposed for Week 3, owner Aryan + Bhuvan.
