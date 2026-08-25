import type Cookies from "js-cookie";

/**
 * Shared cookie attributes for auth token storage.
 *
 * `secure: true` in production ensures the cookie is only ever sent over
 * HTTPS (never in cleartext); disabled for local http://localhost dev where
 * there is no TLS. `sameSite: "strict"` stops the cookie being attached to
 * cross-site requests at all, which is the strongest available mitigation
 * given these are plain (non-httpOnly) cookies read by client JS to build
 * the Authorization header — see app/core/csrf.py on the backend for why
 * Bearer-token auth doesn't need double-submit CSRF protection *in addition*
 * to this, as long as the cookie itself isn't ambient across sites.
 */
export function secureCookieOptions(expiresInDays: number): Cookies.CookieAttributes {
  return {
    expires: expiresInDays,
    path: "/",
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
  };
}
