# Security Audit

## Authentication lifecycle — verified

| Control | State | Evidence |
|---|---|---|
| Hashing | passlib CryptContext bcrypt | `security.py` |
| Token lib | **PyJWT 2.15.1** (migrated off python-jose this audit cycle) | manifests + `pip list` shows only PyJWT; zero `jose` imports remain (grep-verified across `app/`) |
| Algorithm | HS256 via `settings.ALGORITHM`, decode allowlist `algorithms=[...]` — no alg-confusion | `decode_token` |
| Claims | sub(str), exp(datetime→int), type, jti, fam | round-trip verified |
| Tamper | modified token → ValueError → 401 | executed |
| Refresh rotation | single-use jti, family revocation on reuse, fail-closed on missing record | `validate_and_rotate` + warning log `refresh_token.reuse_detected` |
| Login throttle | 5 fails/300s → 429 + Retry-After; Redis-primary, in-process fallback; constant bodies | `login_throttle` + tests |
| Account enumeration | registration pins citizen; login error identical for missing vs wrong password | `auth.py` |
| Password reset | **NOT IMPLEMENTED** — no endpoints | — |
| Demo users | only under `ALLOW_DEMO_SEED`; prod creates none | seeder gate |
| Weak secrets | `SECRET_KEY` min-32 + known-insecure rejection | `config.py` |

## Authorization (endpoint-level, server-side)

- Role matrix enforced in `deps.py`; nested `get_current_user` inside `require_roles` — no guard bypass.
- Ownership: civic reports (owner+staff), notifications (own only), media (owner or valid signature), enforcement (field_inspector own actions for outcomes).
- City scoping: citizens pinned to `user.city` on WS (4403 close) and civic queries server-side.
- Frontend `role-policy.ts` hides tabs but is **not** the boundary — backend re-checks (BUG 012 regression-tested).

## Rate limiting & abuse

- Redis-primary sliding window; **on Redis outage**: `/api/v1/auth/*` + `/api/v1/admin/*` → 503 fail-closed; all else → bounded in-process fallback (`RATE_LIMIT_FALLBACK_RPM`, default 30/IP/min; auth paths stricter cap).
- Recovery on Redis return is automatic. Per-process bound documented (N×replicas caveat).
- Tested: Redis-down → 503 on auth path; fallback cap enforced; per-IP isolation.

## Web security surface

| Vector | Posture |
|---|---|
| SQLi | SQLAlchemy parameterized throughout; raw SQL uses bound params (sampled) |
| XSS | React-escaped rendering; CSP `default-src 'none'` on API; no `dangerouslySetInnerHTML` in user paths |
| CSRF | Double-submit middleware, correctly scoped: only enforces when `session` cookie present (Bearer isn't ambient — sound reasoning) |
| SSRF | Provider URLs are config-constant, not user-derived; media path normalized + verified before storage read |
| Path traversal | `normalise_rel_path` rejects `..`/absolute before storage read |
| Uploads | No raw upload endpoints — presigned-URL design; storage read behind signature/owner |
| Redirects | No `RedirectResponse` to user input found |
| Headers | nosniff, X-Frame DENY, Referrer-Policy, Permissions-Policy, strict CSP (relaxed only /docs), HSTS production-only |
| CORS | env allowlist, credentials-capable |
| Media | HMAC-SHA256 `sign/verify` + exp (default TTL 300s), timing-safe compare |
| Deserialization | joblib artifacts — local trusted files only; note: joblib unpickles (standard caveat, acceptable for self-produced artifacts) |
| Logs | no passwords/tokens/secrets; `health_error_label` never echoes raw exceptions |

## Vulnerability register (open)

| ID | Sev | Item | Status |
|---|---|---|---|
| S-01 | MED | ~167 pip-audit findings / 17 pkgs (post-jose) | OPEN — owner triage, no blind bump |
| S-02 | MED | 2 npm vulns requiring `next@16` (breaking) | OPEN — owner decision |
| S-03 | LOW | Per-process rate-limit/login fallback across replicas | DOCUMENTED-ACCEPTED |
| S-04 | LOW | joblib artifact trust boundary | DOCUMENTED — artifacts are self-produced |
| S-05 | — | python-jose PYSEC-2025-185 | **CLOSED this audit** (PyJWT verified) |

**No exploited or confirmed-exploitable findings.** Secrets scan clean; no credentials in code/logs/frontend bundle paths.
