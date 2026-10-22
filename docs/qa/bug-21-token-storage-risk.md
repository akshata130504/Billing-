# BUG-21: sign-in tokens in browser storage

**Severity:** P3 (production QA, 2026-10-09; re-verified on release `6dbf7d1`, 2026-10-12)
**Status:** open. Needs a product-owner decision: fix now, or accept the risk for the pilot with the pilot risk-acceptance record below.

## Finding

| Session | Where the token lives | Lifetime today | Readable by page scripts? |
|---|---|---|---|
| Tenant web app | `localStorage` keys `rooman.access_token` and `rooman.refresh_token` | Access 30 min (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 30). Refresh up to 30 days, rotating (`REFRESH_TOKEN_EXPIRE_DAYS`). | Yes |
| Customer portal | `localStorage` key `rooman.portal_token`, plus non-secret `rooman.portal_user` and `rooman.portal_customer_name` | 7 days, **hard-coded** in `customer_portal_service.py` | Yes |
| Platform console (Super Admin) | httpOnly, Secure, SameSite=Strict `__Host-` cookies with a CSRF token | 10 min | No |

The platform console is not affected.

## Exploitability

Tokens in `localStorage` are exposed only if an attacker can run script in the app's origin (XSS) or has an unlocked browser profile. They are not exposed to other sites: same-origin policy applies, and CORS refuses foreign origins with credentials. No XSS was found in either production audit.

If XSS happened, an attacker could:
- read the access token and call the API as that user until it expires (30 minutes)
- read the refresh token and keep minting access tokens until rotation reuse detection revokes the session family (up to 30 days)
- read the portal token and act as that customer in the portal for up to 7 days or until logout

## Existing mitigations (verified)

| # | Control | Verification |
|---|---|---|
| C1 | Strict CSP: `script-src 'self' https://checkout.razorpay.com`, no `unsafe-inline` or `unsafe-eval`, on web and API responses (BUG-25 fixed) | Production, 2026-10-12 |
| C2 | React output escaping; no `dangerouslySetInnerHTML` in app code; template previews sandboxed without `allow-scripts` | Code search, and every injection attempt in both audits rendered as text |
| C3 | HTML and formula characters rejected in names, prefixes, checkout templates and custom CSS (BUG-09/47/48/50 fixed) | Production |
| C4 | Refresh rotation with reuse detection; logout revokes server-side; users can revoke sessions | An old token returned 401 after logout on production |
| C5 | Tenant tokens rejected by platform APIs, portal tokens rejected by tenant APIs (401) | Production |

## Remediation

The fix is the design already documented in [`docs/security-roadmap.md`](../security-roadmap.md), section "Designed, not implemented: httpOnly cookie + CSRF authentication". This record does not define a separate design. In summary:

- refresh token in an httpOnly `__Host-rb_refresh` cookie
- access token kept in memory only
- CSRF protection on the cookie-reading endpoints (refresh and logout)
- the customer portal token handled the same way in a second phase
- a staged rollout and the tests listed in the roadmap

Effort has not been estimated against this design.

| Option | Notes |
|---|---|
| **A. Fix before the pilot** | Implement the roadmap design. |
| **B. Accept the risk for the pilot** | Use the compensating controls above, apply mitigation C6 below (needs approval), and add a CI check that the CSP never gains `unsafe-inline` or `unsafe-eval`. Implement option A in the first release after the pilot. |

**Recommendation:** option B, with a named owner and the review date below.

## Pilot risk-acceptance record (PROPOSED, unsigned)

**Status:** proposed, not approved. Nothing here has been applied to production. Scope: the limited pilot only, until the review date.

### Mitigation C6: 15-minute tenant access token (proposed, not applied)

| Item | Detail |
|---|---|
| Change | Set `ACCESS_TOKEN_EXPIRE_MINUTES=15` in the production environment file. **No code change.** |
| Applies on | Backend restart (the setting is read at start-up). Tokens issued before the restart keep their original expiry, at most 30 minutes. |
| User impact | The web app silently refreshes on a 401, with one refresh in flight at a time. Expected: one extra refresh call per user about every 15 minutes and no forced sign-outs. **[Assumption, to confirm after the change.]** |
| Not changed | Refresh-token lifetime (30 days), portal session (7 days; needs a code change), platform console |
| Rollback | Set the value back to 30 and restart the backend |
| Approval needed | Production configuration change: **product owner and server owner**, before anyone applies it |
| Post-change check | Sign in as a QA Owner and check that the access token's `exp - iat` is 900 s, in the browser, without sharing the token. Stay idle for more than 15 minutes, then confirm the next action succeeds after a silent refresh with no sign-out. |

Optional, also needs approval: reduce `REFRESH_TOKEN_EXPIRE_DAYS` (for example 30 → 7). Users would then sign in again weekly.

### Closure criteria

BUG-21 is closed only when all of these hold on production, per the roadmap design:
- no tenant or portal token in `localStorage` or `sessionStorage`
- the refresh token only in an httpOnly, Secure, SameSite=Strict `__Host-` cookie
- the access token held in memory only
- a cookie-authenticated refresh or logout without a valid CSRF token, or from a foreign `Origin`, is refused (403)
- refresh, logout and session revocation behave as before, and a replayed refresh cookie revokes the session family
- the customer portal token is moved off web storage (roadmap phase 2)
- CSP unchanged or stricter
- automated tests cover all of the above

### Review and triggers

| Item | Value |
|---|---|
| Review date | **2026-11-15** or the end of the pilot, whichever is earlier |
| Re-open immediately if | Any XSS or HTML-injection finding; any CSP weakening (`unsafe-inline`, `unsafe-eval`, new script origins); the pilot is widened beyond the agreed organisations; a token is found in logs or error reports |
| At review | Either option A is deployed and the closure criteria are met, or a new dated decision is recorded. The acceptance does not renew automatically. |

### Sign-off (to complete)

Applying C6, or any other production setting, requires this record to be signed first.

| Role | Name | Decision | Date |
|---|---|---|---|
| Risk owner (accountable for the remediation date) | `<NAMED OWNER>` | | |
| Product owner | `<name>` | Accept for pilot / Fix before pilot | |
| Server owner (applies C6) | `<name>` | C6 applied: yes / no | |
| Security reviewer | `<name>` | | |
