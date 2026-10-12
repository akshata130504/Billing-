# BUG-21: sign-in tokens in browser storage

**Severity:** P3 (production QA, 2026-10-09)
**Status:** open. Needs a product-owner decision: fix now, or accept the risk with a dated follow-up.

## Finding

| Session | Where the token lives | Readable by page scripts? |
|---|---|---|
| Tenant web app | `localStorage` keys `rooman.access_token` (30-minute access token) and `rooman.refresh_token` (rotating, up to 30 days) | Yes |
| Customer portal | `localStorage` key `rooman.portal_token` (7-day session), plus non-secret `rooman.portal_user` and `rooman.portal_customer_name` | Yes |
| Platform console (Super Admin) | httpOnly, Secure, SameSite=Strict `__Host-` cookies with a CSRF token | No |

The platform console is not affected. Re-verified on production on release `6dbf7d1` (2026-10-12): both localStorage findings are still present.

## Exploitability

Tokens in `localStorage` are only exposed if an attacker can run script in the app's origin (XSS), or has access to an unlocked browser profile. They are not exposed to other sites: same-origin policy applies, and CORS refuses foreign origins with credentials.

If XSS happened, an attacker could:
- read the access token and call the API as that user until it expires (30 minutes)
- read the refresh token and keep minting access tokens, up to 30 days

**Refresh-token reuse detection** limits this. When the legitimate client and the attacker both use the same refresh token, the session family is revoked.

## Existing mitigations (verified)

1. **Strict CSP on the web app:** `script-src 'self' https://checkout.razorpay.com`, with no `unsafe-inline` or `unsafe-eval`. Since release 6dbf7d1, API responses carry the same single policy (BUG-25 fixed).
2. **Output encoding:** React escapes output. Every injection attempted in both audits rendered as text: customer, offering, expense and template fields; public quote pages; the visual editor preview. Template preview iframes run without `allow-scripts`.
3. **Input validation:** HTML and formula characters are rejected in names, prefixes, checkout templates and custom CSS (BUG-09/47/48/50 fixed).
4. **Session controls:** short access tokens (30 minutes), refresh rotation with reuse detection, logout revokes server-side (verified: an old token returns 401 after logout), and users can revoke sessions.
5. **Separate privilege domains:** a tenant token is rejected by platform APIs (401) and a portal token by tenant APIs (401).

## Remediation options

| Option | Effort | Notes |
|---|---|---|
| **A. Full fix:** move tenant and portal web sessions to httpOnly `__Host-` cookies plus double-submit CSRF, mirroring the platform console | ~20–26 h, plus a coordinated backend-then-frontend deploy and one forced re-login | Keep Bearer/JSON tokens for native apps and API integrations. Design notes: cookie names, CSRF header, refresh from cookie, multi-tab logout via `BroadcastChannel`, `X-Auth-Mode: cookie` opt-in. |
| **B. Accept the risk for MVP** with compensating controls | < 1 h | Shorten `ACCESS_TOKEN_EXPIRE_MINUTES` to 10–15 and consider a shorter `REFRESH_TOKEN_EXPIRE_DAYS` (environment change; needs approval). Add a CI check that the CSP never gains `unsafe-inline`/`unsafe-eval`. Audit for `dangerouslySetInnerHTML`. Schedule option A for the first post-MVP release. |

**Recommendation:** option B now, with a named owner and a date for option A.

**Decision record:**
- Decision (A / B):
- Owner:
- Target release:
- Approved by:
- Date:
