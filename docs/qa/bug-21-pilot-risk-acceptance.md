# BUG-21: pilot risk-acceptance record (PROPOSED)

| | |
|---|---|
| Status | **Proposed, not approved.** Nothing in this record has been applied to production. |
| Risk | Tenant and customer-portal sign-in tokens are stored in browser `localStorage`, readable by any script running in the app's origin |
| Severity | P3 (production QA, 2026-10-09; re-verified on release `6dbf7d1`, 2026-10-12) |
| Background | [bug-21-token-storage-risk.md](bug-21-token-storage-risk.md) |
| Scope of acceptance | Limited pilot only, until the review date below |

## 1. What is being accepted

| Session | Stored in | Lifetime today | Exposure if script runs in the app origin |
|---|---|---|---|
| Tenant web app | `rooman.access_token`, `rooman.refresh_token` | Access 30 min (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 30). Refresh 30 days, rotating (`REFRESH_TOKEN_EXPIRE_DAYS`). | Calls as the user until the access token expires. Refresh token lets the attacker keep minting access tokens until rotation reuse detection revokes the family. |
| Customer portal | `rooman.portal_token` | 7 days, **hard-coded** (`customer_portal_service.py`) | Portal actions as that customer for up to 7 days or until logout |
| Platform console | httpOnly `__Host-` cookies | 10 min | **Not affected** |

Exploiting this needs an XSS in the app origin or access to an unlocked device. No XSS was found in either production audit.

## 2. Compensating controls

| # | Control | State | Verification |
|---|---|---|---|
| C1 | Strict CSP: `script-src 'self' https://checkout.razorpay.com`, no `unsafe-inline` / `unsafe-eval`, on web and API responses | In place | Verified on production 2026-10-12 |
| C2 | React output escaping. No `dangerouslySetInnerHTML` in app code. Template previews sandboxed without `allow-scripts`. | In place | Code search (0 uses outside tests) and injection tests in both audits |
| C3 | HTML and formula characters rejected in names, prefixes, templates and custom CSS | In place | BUG-09/47/48/50 verified fixed |
| C4 | Refresh rotation with reuse detection; logout revokes server-side; users can revoke sessions | In place | Old token returned 401 after logout on production |
| C5 | Tenant tokens rejected by platform APIs, portal tokens rejected by tenant APIs | In place | 401 verified on production |
| **C6** | **Tenant access token lifetime reduced from 30 to 15 minutes** | **Proposed: not applied** | See section 3 |

## 3. Mitigation C6: 15-minute tenant access token

| Item | Detail |
|---|---|
| Change | Set `ACCESS_TOKEN_EXPIRE_MINUTES=15` in the production environment file. **No code change.** |
| Applies on | Backend restart (the setting is read at start-up). Tokens issued before the restart keep their original expiry, at most 30 minutes. |
| User impact | The web app silently refreshes on a 401 (one refresh in flight at a time). Expected: one extra refresh call per user about every 15 minutes, no forced sign-outs. **[Assumption, to confirm after the change.]** |
| Not changed | Refresh-token lifetime (30 days), portal session (7 days, needs a code change), platform console |
| Rollback | Set the value back to 30 and restart the backend |
| Approval needed | Production configuration change: **product owner and server owner**, before anyone applies it |
| Post-change check | Sign in as a QA Owner and decode the access token's `exp - iat` (900 s) in the browser, without sharing the token. Stay idle more than 15 minutes, then confirm the next action succeeds after a silent refresh with no sign-out. |

Optional, also needs approval: reduce `REFRESH_TOKEN_EXPIRE_DAYS` (e.g. 30 → 7). Users would then have to sign in again weekly.

## 4. Remediation plan (cookie-based sessions)

Move tenant and portal web sessions to the same model as the platform console.

| Step | Work | Estimate |
|---|---|---|
| 1 | Backend: on web sign-in, refresh and portal sign-in, set the access and refresh tokens as httpOnly, Secure, SameSite=Strict `__Host-` cookies (opt-in header `X-Auth-Mode: cookie`). Keep Bearer/JSON for API integrations. | 6–8 h |
| 2 | Backend: double-submit CSRF token required on every state-changing request authenticated by cookie; refresh reads the cookie; logout clears the cookies and revokes the session | 4–5 h |
| 3 | Frontend: stop writing tokens to `localStorage`, send credentials with requests, add the CSRF header, multi-tab logout via `BroadcastChannel`, clear the legacy keys on first load | 5–6 h |
| 4 | Portal: same changes; make the 7-day lifetime a setting | 2–3 h |
| 5 | Tests: cookie flags, CSRF refusal (403), refresh, logout, multi-tab, legacy-key cleanup; update about 14 frontend tests | 3–4 h |
| 6 | Release: deploy backend first (accepts both modes), then frontend; one forced re-login; production verification | Coordinated window |

Total: about 20–26 engineering hours. Target: **first release after the pilot**, no later than the review date.

## 5. Closure criteria

BUG-21 is closed only when every item below holds on production:
- No tenant or portal token in `localStorage`, `sessionStorage` or any script-readable cookie
- Session cookies are httpOnly, Secure, SameSite=Strict and `__Host-` prefixed
- A state-changing request without a valid CSRF token is refused (403)
- Refresh, logout (all tabs) and session revocation behave as before
- CSP unchanged or stricter
- Automated tests cover all of the above

## 6. Review and triggers

| Item | Value |
|---|---|
| Review date | **2026-11-15** or the end of the pilot, whichever is earlier |
| Re-open immediately if | Any XSS or HTML-injection finding; any CSP weakening (`unsafe-inline`, `unsafe-eval`, new script origins); the pilot is widened beyond the agreed organisations; a token is found in logs or error reports |
| At review | Either the cookie remediation is deployed and closure criteria are met, or a new dated decision is recorded. Acceptance does not renew automatically. |

## 7. Sign-off (to complete)

| Role | Name | Decision | Date |
|---|---|---|---|
| Risk owner (accountable for the remediation date) | `<NAMED OWNER>` | | |
| Product owner | `<name>` | Accept for pilot / Fix before pilot | |
| Server owner (applies C6) | `<name>` | C6 applied: yes / no | |
| Security reviewer | `<name>` | | |

Applying C6 or any other production setting requires this record to be signed first.
