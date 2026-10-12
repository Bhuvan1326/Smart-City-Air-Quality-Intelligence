# Dependency Remediation Report

## Reproduced findings (this session — not historical)

- `pip-audit --format json` → **173 vulns / 16 pkgs** at start → **46 vulns / 10 pkgs** after remediation (artifact: `pip-audit.json`).
- `npm audit` → **7 findings** at start (was "2" in the old report — counts move with advisory DBs) → **5 findings** after the postcss override.

## Python — dispositioned per package

| Package | Was → Now | Vulns | Disposition |
|---|---|---|---|
| ecdsa | 0.19.2 → **uninstalled** | 2→0 | **FIXED** — orphaned jose transitive, zero imports |
| aiohttp | 3.11.10 → **3.14.3** | 66→0 | **FIXED** — provider-path HTTP client; all dependents' constraints open |
| jinja2 | 3.1.4 → **3.1.6** | 6→0 | **FIXED** — instructor transitive compat |
| python-multipart | 0.0.12 → **0.0.31** | 14→0 | **FIXED** — mcp constraint open |
| Pillow | 11.0.0 → **12.3.0** | 33→0 | **FIXED** — pdfplumber/reportlab/weasyprint constraints open |
| weasyprint | 62.3 → **REMOVED** | 6→0 | **FIXED via removal** — zero imports; reportlab is the actual PDF path; also unimportable on Windows (needs Pango system libs) |
| starlette | 0.41.3 | 14 | **DEFERRED — owner decision**: needs FastAPI ≥0.127 (0.115.5→0.14x framework upgrade + full retest). Reachability: core framework path → highest-priority deferred item. |
| chromadb | 1.1.1 | 5 | **NO FIX EXISTS** — crewai transitive; agents feature. Monitor. |
| langchain-core | 0.3.86 | 3 | **DEFERRED** — 1.x major; agents stack |
| langgraph | 0.2.60 | 3 | **DEFERRED** — 0.3/1.0 majors; agents stack |
| langgraph-checkpoint | 2.1.2 | 6 | **DEFERRED** — 3.x/4.x majors |
| langgraph-sdk | 0.1.74 | 3 | **DEFERRED** — 0.3/0.4 minors+ |
| mcp | 1.26.0 | 6 | **BLOCKED** — `crewai 1.15.1` hard-pins `~=1.26.0`; bumped→conflict→reverted. Fix = crewai upgrade (owner decision). |
| json-repair | 0.25.3 | 1 | **BLOCKED** — `crewai` pins `~=0.25.2`; same reverted bump |
| black | 24.10.0 | 3 | **ACCEPTED-RISK** — dev-only formatter; fixes only in 26.x major |
| pytest | 8.3.4 | 2 | **ACCEPTED-RISK** — dev-only runner; fix 9.0.3 major |

**Every remaining finding has an explicit disposition; none silently ignored.**

## npm — dispositioned

| Finding | Path | Disposition |
|---|---|---|
| postcss (4 advisories: XSS, file-read, path-traversal ×2) | `next→postcss@8.4.31` | **FIXED** — `overrides.postcss>=8.5.29`; nested dep now dedupes to 8.5.29. PostCSS is semver-8 compatible; the `next` flag itself was a dependent-path artifact — **next@16 upgrade NOT required** (documented decision: Option A-via-override, not the npm-suggested Option B-major) |
| braces GHSA-vfj7 (stack-exhaustion DoS) | `eslint-config-next→@next/eslint-plugin-next→fast-glob→micromatch→braces` | **ACCEPTED-RISK — unfixable**: braces@3.0.3 is latest, advisory range `*` (no patched release exists). Reachability: dev/lint-time only, requires attacker-controlled glob inputs. Owner: monitor for upstream fix. |
| eslint-config-next, @next/eslint-plugin-next, fast-glob, micromatch | same chain | container entries — cleared automatically when braces patches |

## Regression verification (post-changes)

- Full non-integration lane: **716 passed, 0 failed** — zero upgrade regressions.
- `app.main` imports: 124 routes. `ruff/black/isort`: clean. Frontend: 49/49, tsc clean.
- `weasyprint` removal verified: zero `weasyprint`/`WeasyPrint` imports in `app/` (grep); reports endpoint uses reportlab.

## Reproducible installs

`backend/requirements.txt` + `pyproject.toml` updated to the exact installed versions; `frontend/package-lock.json` regenerated via `npm install` (lockfileVersion 3 intact).
