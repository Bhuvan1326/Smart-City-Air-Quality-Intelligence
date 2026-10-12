# Frontend Audit

## Architecture (verified)

- Next.js 15.5 App Router, React 19, TS 5.6 — **43 pages** under `app/` (`login`, root, 41 `dashboard/*` routes).
- Data layer: `lib/api/client.ts` (fetch wrapper, `NEXT_PUBLIC_API_URL` fallback localhost:8000 — env default, not hardcode) → `services.ts` typed API surface → `next.config.ts` rewrites `/api/backend/*` → `${BACKEND_URL}/api/v1/*`.
- State: TanStack Query (server data) + Zustand (`auth`, `city` stores).
- Role UI: `role-policy.ts` + `module-access.ts` guards — UX-only; backend re-enforces (verified).

## Connectivity matrix (sampled against contract)

43 pages ↔ services.ts methods ↔ backend routes — the **contract checker statically verifies every typed call** (93 calls / 1232 fields / 0 errors / 0 warnings). This is stronger evidence than manual spot-checks: any field drift in either direction fails CI.

| Surface | Client | Backend | States |
|---|---|---|---|
| Dashboard AQI + freshness | `aqiApi`, `kpiApi` | `/aqi/*`, `/kpi/data-freshness` | live/recent/stale/demo/unavailable badges |
| Forecast | `forecastApi` | `/forecast*` | model-unavailable explicit state |
| Alerts | `alertsApi` | `/alerts*` | list + staff actions |
| Civic | `civicApi` | `/civic/issues*` | ownership-scoped |
| Analytics + Impact Ledger | `analyticsApi`, `enforcementApi.listOutcomes` | `/analytics*`, `/enforcement/outcomes` | `ImpactLedgerCard`: loading/empty/error + non-causal label |
| Enforcement | `enforcementApi` | `/enforcement*` | staff UI |
| Admin | admin pages | guarded endpoints | RequireAdmin |

## Quality gates (this session)

`tsc --noEmit` 0 err · `npm test` 49/49 · ESLint 0 err/12 warn · `next build` PASS · contract check clean.

## UX-state honesty — verified patterns

- Loading: query `isLoading` → skeleton/pulse, never fake data.
- Empty: explicit "No X recorded yet" (e.g., ledger).
- Error: `extractErrorMessage` + destructive styling — never renders as empty.
- Offline/stale: freshness badge + `is_synthetic` → "Demo data".
- Unauthorized/forbidden: module guards redirect; 403-classified tests exist (`errors classified for 403, 5xx, network` test file).

## Findings

- 12 ESLint warnings (non-blocking, P4).
- Dual lockfile (root + frontend) → Next infers wrong root — warning only (D-14, accepted).
- No `dangerouslySetInnerHTML` on user data; no hydration errors observed in build.
- Playwright `e2e/role-walkthrough.spec.ts` authored — **BLOCKED** (no browsers).
