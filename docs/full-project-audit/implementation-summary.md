# Implementation Summary — release-hardening session (post-audit)

Baseline: `main` @ `ff33c0f` + prior uncommitted W3–W5 work. All changes below are uncommitted, small, and regression-verified.

## Dependency remediation (Priority 2) — EXECUTED

| Change | Manifests | Result |
|---|---|---|
| `ecdsa` uninstalled (orphaned python-jose transitive — `Required-by:` empty, zero imports) | was never pinned | 2 vulns closed |
| `aiohttp` 3.11.10 → **3.14.3** | requirements.txt + pyproject.toml | 66 vulns closed; twilio/instructor/kubernetes constraints open → compatible |
| `jinja2` 3.1.4 → **3.1.6** | both manifests | 6 vulns closed |
| `python-multipart` 0.0.12 → **0.0.31** | both manifests | 14 vulns closed |
| `Pillow` 11.0.0 → **12.3.0** | both manifests | 33 vulns closed; weasyprint/pdfplumber/reportlab constraints open |
| **`weasyprint` REMOVED entirely** | deleted from both manifests | dead dep — zero `weasyprint` imports in `app/` (reportlab is the PDF path); 6 vulns closed + heavy system-lib dep dropped |
| `frontend/package.json` `overrides: {"postcss": ">=8.5.29"}` | package.json + lock regenerated | `next→postcss` now resolves 8.5.29 → **all 4 postcss advisories + the `next` flag cleared**; NO next@16 upgrade needed (npm's `fixAvailable` suggestion was a false requirement — `next` was only flagged as postcss's dependent-path) |
| Reverted (crewai hard-pins): `mcp` 1.28.1→1.26.0, `json-repair` 0.60.1→0.25.3 | unchanged | `crewai 1.15.1` requires `mcp~=1.26.0`, `json-repair~=0.25.2` — bumping breaks the agents feature; documented |

**Net pip-audit: 173 → 46 findings** (details in `dependency-remediation-report.md`). npm: 7 → 5 (remaining = unfixable dev-only `braces` chain).

## Observability (Priority 5.4) — IMPLEMENTED

- `app/core/correlation.py` — `CorrelationIdMiddleware`: reuses a safe inbound `X-Request-ID` (`^[A-Za-z0-9_-]{1,64}$` — rejects log-injection payloads), else generates uuid4-hex; binds to structlog contextvars (logger already has `merge_contextvars` → every log line gets `request_id`); echoes on response.
- `app/core/request_metrics.py` — `RequestMetricsMiddleware`: `http_requests_total{method,status_class}` + `http_request_duration_seconds{method}` — **no path labels** (parameterized routes → unbounded cardinality is itself a DoS surface); no-ops cleanly if prometheus_client absent (it's in manifests → active).
- Registered outermost→inner: Correlation → Metrics → Audit → RateLimit → CSRF → SecHeaders → GZip → CORS.
- Tests: `app/tests/test_observability.py` — **13 non-DB tests** (validation, injection rejection, contextvar bind/unbind, counter increments by class) — all pass.

## Config fix (Priority 5.6) — IMPLEMENTED

- `frontend/next.config.ts`: `outputFileTracingRoot: path.join(__dirname)` — eliminates the multi-lockfile root-inference warning. Root `package.json`/`package-lock.json` is a stray eslint-only install (no scripts, no root eslint config); flagged for owner removal rather than deleted unilaterally.

## Files changed

```
backend/app/core/correlation.py            (new)
backend/app/core/request_metrics.py        (new)
backend/app/tests/test_observability.py    (new)
backend/app/main.py                        (+2 middleware registrations)
backend/requirements.txt                   (aiohttp/multipart/Pillow/jinja2 bumps, weasyprint removed, PyJWT kept)
backend/pyproject.toml                     (same)
frontend/package.json                      (+overrides.postcss)
frontend/package-lock.json                 (regenerated)
frontend/next.config.ts                    (+outputFileTracingRoot)
```

## Regression evidence

- Backend non-integration lane **post-all-changes**: 716 passed, 0 failed, 1 skipped (70.39% cov — env artifact).
- New observability tests: 13/13. Security W3 set: 16/16. Combined spot run: 29/29.
- App boot: 124 routes. Contract: 93 calls / 1232 fields / 0 errors.
- Frontend: 49/49 tests, tsc clean (build re-running at write time).
- ruff/black/isort: clean on all touched files.
