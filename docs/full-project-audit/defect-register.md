# Full Project Audit — Defect Register (deduplicated)

Status: **OPEN / VERIFIED-FIXED / BLOCKED-INFRA / ACCEPTED-RISK / NOT-REPRODUCED**
Category: **VERIFIED-DEFECT / SUSPECTED / DESIGN-GAP / TECH-DEBT / INFRA-BLOCKER**

## Open defects

| ID | Sev | Cat | Defect | Evidence | Impact | Remediation | Status |
|---|---|---|---|---|---|---|---|
| F-01 | P2 | VERIFIED | **46 pip-audit findings across 10 pkgs** (was 173/16) | `pip-audit.json` | starlette(14, needs FastAPI major), langgraph-stack(15, agents majors), chromadb(5, no fix), mcp(6)+json-repair(1, crewai-pinned), black(3)+pytest(2, dev-only) | per-package dispositions in dependency-remediation-report.md | **PARTIALLY-FIXED — 127 closed; remainder owner-decision/accepted-risk** |
| F-02 | P2 | VERIFIED | npm: 5 findings (braces chain) — postcss+next RESOLVED via override | `npm audit` | braces DoS is dev-only, **no patched release exists** | accepted-risk + monitor upstream | **PARTIALLY-FIXED — next@16 NOT needed (was npm's false suggestion)** |
| F-03 | P3 | INFRA-BLOCKER | Coverage gate 80% unmet locally (70.39%) | pytest cov report | gate only meaningful with services | run full suite in CI with db+redis | **BLOCKED-INFRA** |
| F-04 | P3 | TECH-DEBT | Dual package-lock → Next infers wrong root | `next build` warning | warning noise; could misresolve in edge cases | **`outputFileTracingRoot` set → warning gone**; stray root package.json flagged for owner removal | **FIXED** (root files remain, owner to delete) |
| F-05 | P4 | TECH-DEBT | `POST /enforcement` + `POST /alerts` use in-handler citizen-403 vs `RequireStaff` dep | `enforcement.py:130` | style inconsistency only — same protection | swap for declarative dep | **OPEN — cosmetic** |
| F-06 | P4 | DESIGN-GAP | City Action Brief absent; password-reset flow absent | grep — no endpoints | missing features | **DEFER decisions recorded** — e2e-release-readiness-report §5.2/5.3; verified nothing implies they exist | **RESOLVED — deferred with documented rationale** |
| F-09 | P4 | VERIFIED | No request-correlation IDs; thin app metrics | code inspection | hard to trace requests | **IMPLEMENTED** — CorrelationIdMiddleware + RequestMetricsMiddleware + 13 tests | **FIXED** |
| F-07 | P4 | DESIGN-GAP | Per-process rate-limit/login fallback multiplies cap ×replicas | documented | weakened abuse bound at scale | Redis HA or distributed counter | **ACCEPTED-RISK** (documented) |
| F-08 | P4 | TECH-DEBT | No request-correlation IDs; minimal app metrics | code inspection | thin observability | correlation middleware + instrument | **OPEN — backlog** |

## Verified fixed this cycle (re-verified this audit)

| ID | Sev | Defect | Fix | Verification |
|---|---|---|---|---|
| D-01 | P0 | Empty `api/v1/__init__.py` → app won't import | restored aggregator | 124 routes load |
| D-02 | P1 | `lib/utils.ts` duplicate AQI_BANDS breakage | deduped | tsc+49 tests |
| D-03 | P0 | Weather fetch discarded, table writerless | model+service+task wiring | 8 mapper tests; live write BLOCKED |
| D-04 | P0 | Rate-limit fail-open on Redis outage | fail-closed auth + bounded fallback | W3 tests |
| D-05 | P1 | No login throttle | per-identifier 5/300s→429 | W3 tests |
| D-06 | P1 | WS any-city subscription | citizen→own-city 4403 | W3 tests |
| D-07 | P1 | `twilio` undeclared | pinned 9.10.9 both manifests | sig tests |
| D-08 | P2 | Duplicate OpenAPI op-IDs (IVR) | split GET/POST handlers | 0 dups |
| D-09 | P1 | Impact Ledger write path absent | outcome endpoints+schemas+client+card | contract clean |
| D-10 | P1 | python-jose PYSEC-2025-185 | PyJWT 2.15.1, jose uninstalled | round-trip+31 tests |
| D-11 | P2 | Redis tests polluting unit lane | `integration` marked | deselected correctly |

## Audit-time suspected defects → resolved as NOT defects

| Suspected | Investigation | Verdict |
|---|---|---|
| Unauthenticated `/metrics` | METRICS_TOKEN Bearer + prod-404 + schema-hidden | correct by design |
| Citizen `POST /enforcement` | in-handler `if CITIZEN → 403` found at :130 | protected (style note F-05) |
| Weather model ↔ migration mismatch | line-by-line column compare | matches exactly |
| role_checker without get_current_user | nests it — auth enforced | no bypass |

## Census

**Open:** 2 P2 (dependency decisions) · 1 P3 blocked · 3 P4 (cosmetic/scope/backlog) + 1 P3 accepted + 1 P4 accepted · **Fixed-verified:** 11 · **New verified defects found this audit:** 0
