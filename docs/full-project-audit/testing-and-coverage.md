# Testing & Coverage Audit

## Commands actually executed (this audit session)

| Command | Exit | Result |
|---|---|---|
| `python -m compileall -q app` | 0 | PASS |
| `python -m black --check app` | 0 | 275 files clean |
| `python -m isort --check-only app` | 0 | clean |
| `python -m ruff check app` | 0 | 0 errors |
| `pytest app/tests -m "not integration" -q` | 1 | **716 passed, 2→now-deselected (Redis integration-marked), 1 skipped, 220.9s** |
| `pytest test_week3_* test_security.py -m "not integration"` | 0 | **39 passed** (post-user-edit re-verify) |
| `pytest test_security.py test_week3_security_integration.py …` | 0 | 31 passed (PyJWT) |
| `python -c "from app.main import app"` | 0 | 124 routes, 0 dup op-IDs |
| `app.openapi()` → openapi.json | 0 | regenerated |
| `npm run contract:check` | 0 | 93 calls / 1232 fields / 0 err / 0 warn |
| `npm test` (node --test) | 0 | **49 pass / 0 fail** |
| `npx tsc --noEmit` | 0 | clean |
| `npm run lint` | 0 | 0 err / 12 warn (earlier session, unchanged paths) |
| `npm run build` | 0 | PASS (lockfile-root warning) |
| `python -m app.ml.evaluation --csv <fixture>` | 0 | artifact written |

## Coverage reality

- Configured gate: `--cov-fail-under=80` (`pytest.ini`).
- Measured in the reduced local lane: **70.94%** → gate FAILS locally.
- Correct interpretation: the 259 `integration` tests exercise DB/Redis paths that dominate uncovered lines; the 80% number is only meaningful with services. **Not** a code defect — an environment artifact (D-15).
- Highest-risk under-covered paths (by inspection, not %): live ingestion writes, WS handshake, outcome persistence, token-family Redis paths — all need the integration lane.

## Test architecture notes

- `integration` marker correctly separates service-dependent tests; fixed this cycle: `test_redis_client_thread_safety.py` was unmarked and failed the unit lane — now `pytestmark += integration` → lane truthful.
- Asyncio auto mode; global coverage in pytest.ini.
- Frontend: `node --test tests/*.test.mjs` (49 tests) — vitest is NOT the runner (a mistaken `npx vitest run` produces import errors; use `npm test`).

## BLOCKED lanes (never claimed)

`pytest -m integration` (259) · live schema-drift · Playwright `role-walkthrough` · docker-compose stack · live provider ingestion · Twilio live · full coverage gate.
