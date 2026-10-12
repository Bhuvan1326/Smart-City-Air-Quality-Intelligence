# Backend & API Audit

## Application integrity (verified live)

- `from app.main import app` → **124 routes**, imports clean.
- `app.openapi()` regenerates → **0 duplicate operation IDs**; 93 typed calls matched by the contract checker.
- Router aggregator `app/api/v1/__init__.py` intact — includes all 34 endpoint modules + kpi + media_links.
- `/api/v1/enforcement/outcomes` registered **before** `/{action_id}` (literal-before-param verified at runtime).

## Dependency/auth model (verified)

`get_current_user` → AuthService token pipeline (signature → exp → `type=="access"` → user exists → active). Role guards: `RequireAdmin`, `RequireStaff` (3 staff roles), `RequireInspectorOnly`, `RequireAnalyst` (admin+officer). `require_roles()` nests `get_current_user` — **no endpoint can be reached unauthenticated through a role guard**.

## Endpoint-permission matrix (from live route dependants)

| Guard pattern | Endpoints | Reachable by |
|---|---|---|
| Public (get_db only) | `/auth/login`, `/auth/register`, `/auth/refresh` | anyone (throttled) |
| `get_current_user` | 60+ citizen-facing reads: aqi/*, alerts GET, civic issues GET/POST, dashboard, exposure map, forecast GET, gis/*, heat/*, india, notifications own, replay, sensors, sustainability, traffic, waste, water GET, kpi freshness, media signed-url POST | any authenticated user incl. citizen |
| `role_checker` (no explicit user dep shown = nested) | staff mutations: thresholds, drone/*, enforcement list/patch/outcomes/evidence, civic staff ops, exposure POST/PATCH, simulator whatif, water resource mutations, reports, analytics | staff roles per guard instance |
| `get_current_user` + in-handler 403 | `POST /enforcement` (citizen→403), `POST /alerts` | citizens blocked in-handler |
| Twilio signature dep | `/notifications/ivr/{id}` GET+POST | webhook only |
| Token-gated, schema-hidden | `/metrics` — METRICS_TOKEN Bearer, else 404-in-prod/open-in-dev | infra |
| Signed-URL HMAC | `/media/{rel_path}` | signature or owner |

## Inconsistency note (P4)

`POST /enforcement` and `POST /alerts` use in-handler `if role == CITIZEN → 403` rather than `RequireStaff`/`RequireAnalyst`. Same protection, less declarative — a WouldBeNice refactor, not a defect.

## Contract & error surface

- `APIResponse[T]` envelope used consistently for business endpoints; `PaginatedResponse[T]` for lists.
- 422s come from Pydantic v2 schemas; auth failures 401 with `WWW-Authenticate`; role failures 403; ownership failures 404 (not 403 — correct anti-enumeration).
- Login 401/429 bodies are constant — no account-existence oracle.
- `/health` hides raw exception text (`health_error_label` logs internally).
- GZip, CORS (env `ALLOWED_ORIGINS`), security headers, CSRF (cookie-flows only), rate limit, audit-log on all mutating calls.

## Checked negative results

- No route shadowing found; `/outcomes` vs `/{action_id}` ordering correct.
- No public route removed during W3 work; OpenAPI diff = +2 calls only.
- Error bodies sampled: no stack traces, SQL, or secrets surfaced.
