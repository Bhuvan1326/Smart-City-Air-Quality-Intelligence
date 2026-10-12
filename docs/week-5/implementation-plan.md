# Week 5 — Implementation Plan (verified baseline)

**Baseline:** `main` @ ff33c0f + uncommitted W3 implementation + W4 docs + this week's PyJWT migration. Environment unchanged: Windows, Python 3.12.10, Node 24.21.0 — **no Docker/Postgres/Redis/Playwright locally**; `docker-compose.yml` + `ci.yml` already provision `timescaledb-ha:pg16` + `redis:7-alpine`, so the infra *config* exists — the local *machine* can't run it.

## Risk re-verification (actual, not assumed)

| Risk | Verified status now |
|---|---|
| Rate-limit fail-open | **FIXED W3** — fail-closed on auth/admin, bounded fallback elsewhere |
| Login throttling | **FIXED W3** — 5/300s per-identifier → 429 |
| WS authorization | **FIXED W3** — citizens pinned to `user.city`, close 4403 |
| python-jose PYSEC-2025-185 | **FIXED W5** — migrated to `PyJWT==2.15.1` (this session); jose uninstalled; token round-trip + 31 security tests pass |
| Weather persistence | **FIXED W3** — writer+model+task wiring; live write BLOCKED no-DB |
| Real ML eval data | **BLOCKED** — no populated obs DB; pipeline verified on fixture |
| Impact Ledger workflow | **PARTIAL** — outcome API + ledger card shipped W3; full ops workflow slice (city action brief) still absent |
| E2E + DB integration | **BLOCKED** locally; CI services configured |
| Migration/ORM drift | `schema_drift` tool exists; live check BLOCKED |
| Dependency vulns | jose removed (one advisory closed); remaining pip findings + 2 npm (next@16) still open |

## W5 work items

| ID | Item | Owner | Status |
|---|---|---|---|
| W5-1 | python-jose→PyJWT migration | Rohan | **DONE** — single import point swapped, manifests updated, jose uninstalled, 31/31 sec tests |
| W5-2 | Redis tests misclassified in unit lane | Rohan | **DONE** — `pytestmark += integration`; unit lane now deselects them |
| W5-3 | DB reliability + CI service docs | Vinyak | DOCS — services already in compose/CI; local blocked |
| W5-4 | Weather pipeline doc + unsupported scenarios | Vinyak | DOCS |
| W5-5 | ML reliability report + model interface | Bhuvan | DOCS |
| W5-6 | Operational workflows (Impact Ledger / CAB) | Aryan+Adwait | DOCS — ledger partial, CAB design-only |
| W5-7 | Observability review | — | Health endpoint already degrades on dep failure; documented |
| W5-8 | CI/CD + deployment readiness doc | Aryan | DOCS |
| W5-9 | Release-readiness report | All | DOCS |

**Not attempted (documented, not silently dropped):** docker-based local integration run (no docker daemon), live Twilio (no credentials), real-data ML eval (no populated DB), Playwright (no browsers), blind dependency bulk-upgrade (compat risk), next@16 major (owner decision).
