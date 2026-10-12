# Week 5 — Security Hardening Report

## Fixes applied this week

### 1. python-jose → PyJWT (PYSEC-2025-185) — FIXED

| Step | Evidence |
|---|---|
| Scope | `app/core/security.py` was the **only** jose importer (grep-verified across `app/` incl. tests) |
| Change | `from jose import JWTError, jwt` → `import jwt` + `from jwt.exceptions import PyJWTError as JWTError` — `JWTError` alias keeps `except` semantics identical; PyJWT's `PyJWTError` is the base of `ExpiredSignatureError`/`InvalidTokenError`, so `decode_token` still maps every token failure to `ValueError` |
| Manifests | `python-jose[cryptography]==3.3.0` → `PyJWT==2.15.1` in `requirements.txt` + `pyproject.toml` (no `[crypto]` extra — ALGORITHM is HS256, symmetric) |
| Removal | `pip uninstall python-jose` — gone from the env, nothing else depended on it |
| Claims preserved | `sub`(str), `exp`(datetime→int auto), `type`, `jti`, `fam` — same payload shape; `algorithms=[settings.ALGORITHM]` allowlist unchanged (no alg-confusion surface — this was the actual exposure path the advisory covered, but staying on an unmaintained lib was untenable) |
| Validation | `python -c` round-trip: access+refresh decode, claims asserted, tampered token rejected; `pytest test_security.py test_week3_security_integration.py …` → **31 passed** |

### 2. Redis-test classification — FIXED

`test_redis_client_thread_safety.py` needed a live Redis but ran in the `-m "not integration"` lane → 2 spurious failures every run. Added `pytest.mark.integration` to `pytestmark`. Now: `-m "not integration"` → `2 deselected`; the unit lane is truthful. The tests themselves are correct — they run in CI where the redis service exists.

## Carried verification (W3, still valid)

Rate-limit fail-closed/bounded fallback (tested Redis-down), login throttle (5/300s→429, no account oracle), WS per-city authz (citizen 4403 on foreign city), Twilio signature fail-closed, refresh-token rotation+family revocation with Redis, registration pins `citizen`, refresh tokens rejected on access-token surfaces.

## Residual risks (explicit)

| Risk | Severity | Disposition |
|---|---|---|
| Rate-limit fallback is per-process | MED | Documented cap N×replicas; Redis HA or distributed counter is the real fix — needs infra decision |
| 167 pip findings (post-jose removal; recount at next audit) | VARIES | Owner-driven triage; no blind bulk bump |
| 2 npm vulns requiring next@16 (breaking) | MED | **Owner decision required** |
| Live Twilio signature verification never run | LOW | Needs credentials; logic tested against official SDK cross-validation |
| Multi-replica login throttle | MED | In-process fallback caps per-node; Redis path is already distributed — consistent |

## Rules honored

No secrets logged; authz enforced server-side (frontend role-policy is UX-only, documented); no check marked passed that didn't run.
