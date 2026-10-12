# Frontend Route and UX Audit (Week 1)

Method: read `frontend/app/**/page.tsx`, `components/layout/Sidebar.tsx`, `lib/module-access.ts`, `middleware.ts`, `lib/api/services.ts`; ran the existing suites. **No browser/E2E run was performed**; behaviour claims below are from code reading and type-checking unless a test is cited.

## Baseline (before changes; actual results)
| Check | Result |
|---|---|
| `npm test` (node --test) | 41 tests, 41 pass |
| `npx tsc --noEmit` | exit 0 |
| `npx eslint .` | 0 errors, 12 warnings (unused vars/directives) |

## After changes
| Check | Result |
|---|---|
| `npm test` | 43 tests, 43 pass (2 new in `tests/role-policy.test.mjs`) |
| `npx tsc --noEmit` | exit 0 |
| `npx eslint app/dashboard lib tests` | 0 errors, 10 warnings (all pre-existing categories) |
No component-level (React) tests exist in the repo; the changed page logic is covered only by the pure `role-policy` unit tests plus type-checking. **Gap:** guard hooks and page rendering are untested.

## Route -> intended role mapping
Navigation is a sidebar of aggregator pages, each switching tabs with `?module=<id>`. Legacy per-feature URLs (e.g. `/dashboard/forecast`) redirect into aggregators via `middleware.ts`. "Backend" = role set the API behind the tab enforces.

| Route (`?module=`) | Visible to (frontend) | Backend enforcement | Status |
|---|---|---|---|
| `/dashboard` Overview | all | any user | OK |
| `/dashboard/air-quality` (live, india, forecast, heatmap, sources, transparency) | all | any user | OK (see forecast notes) |
| `/dashboard/intelligence?module=analytics` | **ADM, OFF** (was all except citizen) | ADM+OFF | **Fixed** |
| `...intelligence?module=simulator` | **ADM, OFF** (was all) | ADM+OFF | **Fixed** |
| `...intelligence?module=recommendations` | all | any user | OK |
| `/dashboard/mobility` (traffic, routes, smart) | all | any user | OK |
| `/dashboard/environmental` (9 tabs) | all | any user | OK; product decision pending (matrix) |
| `/dashboard/operations?module=civic` | all (citizen sees own reports) | per-handler rules | OK |
| `...operations?module=enforcement`, `officer` | ADM, OFF, INS (citizen blocked + redirected) | ADM+OFF+INS | OK |
| `...operations?module=alerts` | all | create = staff | Create controls for citizens not verified |
| `...operations?module=thresholds` | all | **writes ADM only** | **Open:** write controls likely shown to non-admins (not verified in browser) |
| `/dashboard/ai?module=assistant` | all | any user | OK |
| `/dashboard/ai?module=agents` | **ADM, OFF** (was all) | ADM+OFF | **Fixed** |
| `/dashboard/reports` | **ADM, OFF** nav; page now redirects others to `/dashboard` (was direct-URL reachable, API 403) | ADM+OFF | **Fixed** |
| `/dashboard/administration?module=admin` | ADM, OFF, INS (citizen blocked) | mixed | **Open:** backend admin-only writes; inspector/officer see admin overview (not verified what it shows) |
| `/dashboard/administration?module=settings` | all | n/a | OK |
| `/login` | public | public | OK |

The sidebar itself still lists Intelligence and AI Center for everyone because their non-restricted tabs (Recommendations, Assistant) are valid for every role; restriction is per tab plus a redirect guard.

## Findings
| # | Sev | Observation | Where | Reproduced | Action |
|---|---|---|---|---|---|
| F1 | Med | Tabs backed by analyst-only APIs shown to inspectors/citizens -> 403 dead-ends. | `module-access.ts`, `ai/page.tsx`, `intelligence/page.tsx` | By code read; backend 403 by test | Fixed |
| F2 | Med | `/dashboard/reports` reachable by URL for non-analysts. | `reports/page.tsx` | Code read | Fixed (redirect + query disabled) |
| F3 | High (privacy) | Citizen "All Reports" toggle depended on the server leak (S1). | `civic/page.tsx` | Yes (backend) | Toggle replaced by static "My Reports" label |
| F4 | Low | Frontend role checks are navigation convenience only; authorization remains server-side (verified). | n/a | n/a | Documented in `role-policy.ts` |
| F5 | Med | Forecast page handles `isLoading` but no explicit error/empty/"model unavailable" states were found in `forecast/page.tsx` (child module not audited). | `forecast/page.tsx` | Not run | **Open** (Week 2, Adwait) |
| F6 | Low | No unauthorized (403) or service-unavailable banner pattern; each page handles errors ad hoc. | various | Not run | Open |
| F7 | Low | 12 pre-existing lint warnings. | repo | Yes | Open |

Contract check with the backend: see `api-contracts.md` (84 service calls, all paths/methods match; field-level shapes not diffed).

## Not done
Browser-based verification of any route; accessibility; offline/service-worker behaviour beyond the existing tests; forecast/alert redesign (deliberately deferred to Week 2).
