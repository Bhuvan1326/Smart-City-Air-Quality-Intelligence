# API Key & Service Credential Audit — 2026-11-08

Read-only audit. Verified via each provider's official authentication or a minimal read-only request. No key values are recorded here or anywhere.

| Variable | Provider | Status | HTTP | Verification method |
|---|---|---|---|---|
| `OPENAQ_API_KEY` | OpenAQ | WORKING | 200 | `GET /v3/locations?limit=1` (X-API-Key) — earlier 401 reports are now resolved; key authenticates |
| `NEXT_PUBLIC_MAPBOX_TOKEN` | Mapbox | WORKING | 200 | `GET /styles/v1/mapbox/streets-v12` |
| `NUGEN_API_KEY` | Nugen | WORKING | 200 | `GET /api/v3/models/base` (Bearer) — also proven by deployed aligned-model inference |
| `GEMINI_API_KEY` | Google Gemini | WORKING | 200 | `GET /v1/models` (key param) |
| `ANTHROPIC_API_KEY` | Anthropic | WORKING | 400 | Auth probe `POST /v1/messages` empty body → 400 (key accepted, request invalid); 401 would mean rejected |
| `NASA_FIRMS_MAP_KEY` | NASA FIRMS | WORKING | 200 | `GET /api/area/csv` — real CSV returned |
| `SENTINEL_HUB_CLIENT_ID` + `SENTINEL_HUB_CLIENT_SECRET` | Sentinel Hub | **INVALID** | 401 | `POST /oauth/token` client_credentials — rejected |
| `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` | Twilio | WORKING | 200 | `GET /2010-04-01/Accounts/{SID}.json` (basic auth) |
| `FIREBASE_CREDENTIALS_JSON` | Firebase | **MISSING** | — | Value is a file path, not JSON; referenced file does not exist on disk |
| `FIREBASE_PROJECT_ID` | Firebase | UNVERIFIED | — | No safe check without working credentials |
| `ENERGY_API_KEY` / `ENERGY_BASE_URL` | Energy provider | UNVERIFIED | 404 | Base host reachable but root returns 404; no documented auth endpoint identified |
| `SMTP_HOST` / `SMTP_USERNAME` / `SMTP_PASSWORD` | SMTP | NETWORK_ERROR | — | Hostname does not resolve; credentials untestable |
| `SECRET_KEY` | Local JWT signing | WORKING | — | Local-only; auth login flow verified working |
| `DATABASE_URL` | PostgreSQL/TimescaleDB | WORKING | — | `/health` reports `database: ok` |
| `REDIS_URL` | Redis | WORKING | — | `PING` → `PONG`; `/health` `redis: ok` |
| `OPEN_METEO_BASE_URL` | Open-Meteo | N/A | 200 | Keyless API — no credential required; endpoint reachable |
| `NUGEN_ALIGNED_MODEL_ID` | Nugen (config) | WORKING | — | Deployed model verified via `/ai/nugen-status` → DEPLOYED |

## Notes

- Sentinel Hub: OAuth explicitly rejects the client pair (401). Either regenerate in the Sentinel dashboard or leave unused — satellite features depending on it will fail.
- Firebase: `FIREBASE_CREDENTIALS_JSON` must contain the service-account JSON inline or point to an existing file — currently neither.
- SMTP: configured hostname doesn't resolve from this machine — alerts-by-email will fail until a valid host is set.
- Twilio: creds are valid but check `TWILIO_ENABLED` before assuming alerts send.
- No credential was modified, rotated, or exposed during this audit.
