# Week 5 — Operations & Reliability Review

## Health & readiness (verified in `main.py`)

`/health` checks **database** and **redis** dependencies separately and returns `status: "healthy" | "degraded"` — dependency failure is surfaced, not collapsed into a 500 or hidden. `health_error_label` deliberately never echoes raw exception text to clients (logged internally with `health.dependency_error`).

## Rate-limit resilience (W3)

Redis outage → auth/admin paths **503 fail-closed**; other paths bounded in-process fallback (default 30 rpm/IP). Recovery is automatic on Redis return; no restart needed. Per-process bound is documented (N×replicas).

## Ingestion resilience

- OpenAQ client enforces 45 rpm / 1700 rph with margin; provider failures logged + cycle skipped (no partial writes).
- Weather persistence is idempotent — a repeated fetch refreshes rather than duplicates.
- Stale AQI reads flagged `is_stale`; UI freshness badges degrade honestly (live/recent/stale/demo/unavailable).

## Token/session resilience

Refresh-token family rotation in Redis: every refresh rotates the active `jti`; presenting a stale `jti` → whole family revoked (theft response); missing active record → fail closed (logged).

## Logging posture

Structured logger (`app.core.logging`) with warning paths for security events (`refresh_token.reuse_detected`, `health.dependency_error`). **No passwords, tokens, provider secrets, or raw private payloads are logged** — verified across touched files.

## Gaps (documented, not silently claimed)

| Gap | Status |
|---|---|
| No metrics/Prometheus export | NOT IMPLEMENTED — health endpoint is the only probe |
| No request/correlation IDs | NOT IMPLEMENTED |
| Graceful shutdown semantics on workers | unverified — scheduler runs fixed-interval loops |
| Retry/backoff policy on providers | per-provider timeouts exist; no unified bounded-retry policy |
| Startup config validation | partial — `SECRET_KEY` min-length + insecure-default rejection exist |
