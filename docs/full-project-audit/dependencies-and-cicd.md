# Dependencies & CI/CD Audit

## Python dependencies

| Check | Result |
|---|---|
| `pip-audit` | ~178→**167 findings / 17 pkgs** after jose removal (recount at next full audit; headline advisory PYSEC-2025-185 closed by PyJWT migration) |
| `twilio` | was imported-but-undeclared → added `twilio==9.10.9` both manifests (D-07 fixed) |
| `python-jose` | **removed** — `PyJWT==2.15.1` in requirements+pyproject; uninstalled from env; zero `jose` imports remain |
| `prometheus_client` | optional-import pattern (graceful ImportError in `/metrics`) — acceptable |
| Unused | none found beyond the above |
| Version policy | pins `==` throughout (no floating ranges); new pins ≥7 days old |

## npm dependencies

- `npm audit fix` earlier reduced 8→2 findings; remaining 2 require **breaking `next@16`** — owner decision, documented (D-13).
- Dual lockfile (root + `frontend/`) → Next root-inference warning (D-14, accepted risk).

## CI integrity (`.github/workflows/ci.yml` — config verified, no run observed)

| Stage | Present | Detail |
|---|---|---|
| Postgres svc | ✅ | `timescale/timescaledb-ha:pg16`, health-gated |
| Redis svc | ✅ | `redis:7-alpine`, `redis-cli ping` |
| Scratch-DB migrations | ✅ | `airquality_migrations` |
| Schema-drift | ✅ | `app.tools.schema_drift --database-url` |
| Backend suite | ✅ | `TEST_DATABASE_URL`/`REDIS_URL` env — integration lane runnable |
| Frontend | ✅ | test + build jobs |
| OpenAPI artifact | ✅ | generated in job |

**No GitHub Actions run was observed** — CI "green" is not claimed anywhere. Config review found no exit-code-swallowing (`&&` chains, no `continue-on-error` on critical steps observed in the inspected sections).

## Deployment config

- `docker-compose.yml`: db (timescale pg16) + redis7 + backend + frontend; healthchecks on infra.
- Env-driven config; `SECRET_KEY` validated (min-32, insecure-default reject); `ALLOW_DEMO_SEED` gates demo users; `is_production` toggles HSTS.
- Rollback: Alembic-versioned downgrades (unexecuted); model artifacts file-versioned.
