# E2E & Release Readiness Report (Priority 5)

## 5.1 — Playwright role walkthrough: BLOCKED

`frontend/e2e/role-walkthrough.spec.ts` exists (citizen/officer/inspector/admin journeys + forbidden-rejection assertions) but **no Playwright browsers are installed and no running stack exists** on this machine. Not executed — never claimed. Unblock: `npx playwright install` + `docker compose up` + demo seed in CI or a capable host.

## 5.2 — City Action Brief scope: **DECISION — DEFER (drop from release scope)**

Rationale: CAB was design-only since Week 2 — no data contract, no recommendation engine spec, no agreed evidence semantics. Building it now would mean inventing product behavior to fill a page — exactly what this audit forbids. **Action taken:** documented as out-of-scope; verified no UI/API implies it exists (no endpoint, no route, no navigation entry found in code sweep). If leadership wants it, it needs a written spec first (data sources → deterministic content rules → authz → UI states), then implementation as a proper slice.

## 5.3 — Password reset scope: **DECISION — DEFER (documented omission)**

Rationale: correct implementation needs an email/delivery channel (provider, credentials, abuse policy) that doesn't exist in this project yet — a password-reset flow without delivery is theater, and a weak one is a security hole. **Action taken:** documented; verified no docs claim it exists. When scheduled, the contract is: expiring single-use token (hashed storage), enumeration-resistant response, throttle, audit event, refresh-family revocation on reset.

## 5.4 — Observability: **IMPLEMENTED + TESTED** (see `implementation-summary.md`)

- `X-Request-ID` correlation: validated-or-generated, log-injection-proof, structlog-bound, echoed on every response.
- Bounded metrics: `http_requests_total{method,status_class}` + `http_request_duration_seconds{method}` via `/metrics` (token-gated, prod-404) — no path labels (documented cardinality decision).
- Diagnosis paths: `rate_limit.redis_unavailable`, `health.dependency_error`, `refresh_token.reuse_detected` log events + `/health` per-dependency status.

## 5.5 — Multi-replica rate limiting: **VERIFIED-DESIGN + ACCEPTED-RISK documented**

Redis-healthy path is already distributed (correct for N replicas). Redis-outage fallback is per-process (30 rpm/IP default, auth paths fail-closed 503). Owner-visible decision recorded: bounded-but-multiplied is acceptable for this release; Redis HA or a distributed fallback counter is the follow-on. Documented in `security-audit.md` + defect F-07.

## 5.6 — Release configuration cleanup: DONE

- `outputFileTracingRoot` pinned → **multi-lockfile warning eliminated** (verified in `npm run build` output — warning absent).
- Root `package.json`/`package-lock.json` flagged as stray (eslint-only, no scripts) — owner removal recommended, not deleted unilaterally.
- `npm run build` re-verified PASS post-override (47 routes, no warnings regressions beyond the pre-existing 12 eslint warns).

## Role coverage matrix (backend-verified; browser lanes blocked)

| Journey | Citizen | Officer | Inspector | Analyst/Admin |
|---|---|---|---|---|
| Login/register | ✅ throttled | ✅ | ✅ | ✅ |
| Dashboard/forecast/GIS reads | ✅ | ✅ | ✅ | ✅ |
| Civic reports (own) | ✅ own-only | ✅ scoped | ✅ | ✅ |
| Alerts subscribe | ✅ | ✅ | ✅ | ✅ |
| Thresholds write | 403 | staff | staff | staff |
| Enforcement create | 403 | ✅ | ✅ own-visibility | ✅ |
| Outcome record | 403 | ✅ any | ✅ own-only | ✅ |
| Analytics/reports/ledger list | 403 | ✅ | 403 | ✅ |
| WS `?city=` | own city only | any | any | any |
| Admin endpoints | 403 | 403 | 403 | ✅ |

Every row verified server-side via `deps.py` + in-handler checks — the matrix is backend truth, not frontend hiding.
