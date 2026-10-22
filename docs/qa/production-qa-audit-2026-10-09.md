# Rooman Billing: Production QA Audit Report

| | |
|---|---|
| Production URL | https://billing.futureacad.ae |
| Build under test | `main` @ `a7a67b7` (PR #33). PR #32 is merged but **not deployed** (CI on `main` failed; fix in PR #34, open) |
| Test window | 8 Oct 2026 18:30 UTC to 9 Oct 2026 ~06:00 UTC (00:00–11:30 IST) |
| Browser | Chromium 153 (Playwright), headed windows with DevTools network/console capture; separate clean processes for external-customer tests |
| Viewports | 1440, 1366, 1280 (console), 390, 375; editor preview at desktop/tablet/mobile (390) |
| Method | Production UI + production network traffic (3,917 API calls logged, redacted) + synthetic QA data only |
| Release decision | **NOT READY** (see section 2) |

No passwords, OTPs, JWTs, invitation/reset/activation tokens or secrets appear in this report. Tokens in URLs are shown as `[TOKEN]`.

---

## 1. Executive summary

The product's **security foundations are strong**:
- tenant isolation holds in both directions
- server-side role checks work, with self-approval blocked
- the platform console uses step-up re-authentication, CSRF protection and httpOnly `__Host-` cookies
- the platform audit trail is append-only and detailed
- XSS input is rendered as text everywhere tested

The **core money maths is correct** for single-currency documents: quotes, invoices, partial payments, credit notes and timesheet invoices all reconcile to the paisa. The new **trial → subscription request → approval → Create Admin** flow works end to end, as do suspension and reactivation.

It is **not ready for real paying customers**, for three reasons:
1. **No organization can collect money online.** The payment gateway is not configured in production (`GATEWAY_NOT_CONFIGURED`, 503).
2. **Multi-currency totals are wrong.** Reports, Collections and the **customer portal** add INR and AED together and show the result as ₹. The customer portal tells a customer they owe ₹4,942.56, an amount that does not exist.
3. **Internal pricing leaks to customers.** The public quote and invoice APIs, and the merchant's portal-invite API, expose data that should not leave the tenant.

GST document typing (Bill of Supply with IGST charged) also needs qualified review before Indian customers rely on these invoices.

## 2. Release decision: **NOT READY**

Totals below include the continuation on 9–10 Oct (section 24). Each bug is counted once.

| Severity | Original audit | Continuation | **Total** |
|---|---|---|---|
| Critical (P0) | 0 | 0 | **0** |
| High (P1) | 3 | 3 | **6** |
| Medium (P2) | 10 | 3 | **13** |
| Low (P3) | 13 | 9 | **22** |
| Cosmetic/enhancement (P4) | 12 | 6 | **18** |
| **Bugs total** | 38 | 21 | **59** |
| Passed checks | 65 | 33 | **98** |
| Partial | 0 | 1 | **1** |
| Blocked | 7 | 2 | **9** |
| Not applicable | 2 | 2 | **4** |

Why NOT READY rather than READY WITH MINOR FIXES:
- The essential billing outcome, being paid online, does not work for anyone (BUG-03).
- Customer-facing financial figures are wrong whenever an org bills in more than one currency (BUG-01, BUG-02).
- Internal pricing data is exposed publicly (BUG-04).

None of these is a minor fix.

## 3. QA accounts and organizations

| Item | Value |
|---|---|
| Org A | **ROOMAN QA AUDIT 2026-10-08**: `d47d8fcf-0c40-4f6d-9d7f-30a42456cc53`, slug `rooman-qa-audit-2026-10-08` |
| Org B | **ROOMAN QA AUDIT B 2026-10-08**: `52e279ba-3559-4b05-80dc-69fdf9bcf994`, slug `rooman-qa-audit-b-2026-10-08` |
| Org A Owner | <qa-inbox>+qaowner@<qa-domain> (active) |
| Org A Finance | <qa-inbox>+qafinance@<qa-domain> (active) |
| Org A Admin | <qa-inbox>+qaadmin@<qa-domain> (provisioned by Super Admin, active) |
| Org A Viewer | <qa-inbox>+qaviewer@<qa-domain> (**invited, never accepted**: email not received) |
| Org B Owner | <qa-inbox>+qaownerb@<qa-domain> (active) |
| External customer | QA Customer A, <qa-inbox>+qacustomer@<qa-domain> (portal activated) |
| Platform | Platform Administrator `<platform-administrator>` (signed in by the account owner; password never handled by the tester) |
| Operations / Support | **Do not exist in production** (staff list shows only the Administrator) |

Synthetic data created in Org A:
- customers CUS-000001 to 000005
- offerings QA-ALPHA-01, QA-ZERO, QA-USD, QA-AED, QA-XSS
- quotes QT-000001 (accepted) and QT-000002 (approved, then declined)
- invoices INV-000001 to 000004
- payments PAY-000001 to 000004 (manual, no real money)
- credit note CN-000001
- subscription SUB-000001
- project "QA Audit Project T&M"
- 2 time entries and 3 expenses

Org B: customer CUS-000001 (QA Customer B), quote QT-000001.

## 4. Route inventory (all tested)

**Public:**

| Route | Result |
|---|---|
| `/` and `/landing` | 200, CMS-driven |
| `/login`, `/signup`, `/forgot-password` | OK |
| `/reset-password` | Incomplete link → clear message; bad token → form, then server 422 |
| `/accept-invitation` | Bad token → "not valid" |
| `/quote/:token`, `/pay/:token`, `/checkout/:token`, `/portal/activate` | Bad token → "isn't valid" pages |
| `/portal` | → `/portal/login` |
| `/platform-access` | OK |
| `/superadmin` | → `/superadmin/login` |
| Unknown routes | → `/login` (signed out) or "Page not found" (signed in) |
| `/docs`, `/openapi.json`, `/redoc` | **Not exposed** (SPA fallback) |

**Tenant (46 routes × 1440 + 390 px, as Owner):** no console errors, no failed API calls, no crash screens, no horizontal scroll.
- Routes: dashboard, customers (+new), catalog, quotes (+new), cpq, invoices (+new), credit-notes, payments, collections, plans-pricing (+simulator), subscriptions (+new), trials, usage, proration, dunning, customer-lifecycle, customer-portal, hosted-payment-pages, expenses (+recurring), projects, timesheets, revenue-intelligence, reports, ai-billing, activity, platforms/mobile, platforms/desktop, control-center/{action-center, approvals, calendar, reconciliation, audit-log, migration}, automation, customization, integrations (→ settings tab), settings, subscription.
- `/profile` and `/recurring` are route fragments that correctly show "Page not found".

**Platform console (10 pages):** dashboard, organizations, subscription-requests, staff, audit, website, visual-editor, access-grants, health, account. All load with no errors.

## 5. Six dashboards

| Dashboard | Result | Evidence |
|---|---|---|
| Organization `/dashboard` | **PASS** (single currency); Outstanding card correctly shows "₹4,509.20 · AED 433.36"; **FAIL** trend chart | Revenue ₹2,111.51 = sum of 4 cash payments (credit note correctly excluded); trend "invoiced" mixes currencies (BUG-01) |
| Collections `/collections` | **FAIL** | Aging buckets correct with one currency; after the AED invoice, Current = "₹4,942.56" (INR+AED, BUG-01); collection rate disagrees with Reports (BUG-14) |
| Customer portal `/portal` | **FAIL** | Own invoices/subscriptions only (PASS); outstanding ₹4,942.56 mixes currencies (BUG-02) |
| Platform dashboard | **PASS** | Counts only, no tenant financials; pending-request banner works |
| Revenue Intelligence | **PASS** (limited) | MRR/ARR ₹0 with no INR subscriptions; AED MRR kept separate in the API; became "not in your plan" after approval without it (correct) |
| Reports & Analytics | **FAIL** | Totals correct for INR-only data; Total invoiced ₹7,644.07 and Outstanding ₹4,942.56 mix currencies (BUG-01). CSV/PDF export controls were not found or verified (see Blocked) |

## 6. Authentication

| Check | Result |
|---|---|
| Signup + email OTP → org created immediately, **ACTIVE, 3-day trial, Owner, no approval** | PASS (`status: active`, `access.status: trial`, `trial_ends_at` = +72 h) |
| OTP never returned by the API; email masked on screen | PASS |
| Expired OTP | PASS (rejected); P4 wording: "No pending signup found…" |
| Login, wrong password | PASS (401 "Invalid email or password", no user enumeration) |
| Forgot password | PASS (identical 202 for existing and non-existing email) |
| Full reset (Org B Owner) | PASS (email delivered; reset 204; new password 200; old password 401; link reuse 422) |
| Invalid reset token | PASS server-side (422 "invalid or has expired"); P4 UX (form shown before validation) |
| Logout | PASS (204; tokens cleared; old access token → 401; protected route → `/login`) |
| Protected routes signed out | PASS (→ `/login`; API 401) |
| Invitation link reuse | PASS (404 "already used") |
| Platform session idle expiry | PASS ("Your platform session has ended") |

## 7. Subscription lifecycle

| Step | Result |
|---|---|
| Trial starts at signup, no approval | PASS (both orgs) |
| Trial expiry | **BLOCKED**: cannot wait 72 h; expiry date and banner verified |
| Request: modules / dependency (Timesheets → Projects) / seats / cycle | PASS |
| Seats below members in use | PASS (UI disabled; API 409 "at least 3") |
| Unknown module | PASS (422) |
| Second open request | PASS (409 `SUBSCRIPTION_REQUEST_OPEN`) |
| Super Admin approve **with changes** (−Reports, +Collections +Portal, seats 5→4, quarterly→monthly) | PASS; step-up 403 → password → 200 |
| Approved entitlements reach tenant | PASS (`module_access: entitled`, `seat_limit: 4`, exact module list) |
| Entitlement enforcement | PASS (API 403 `FEATURE_NOT_ENTITLED`; sidebar hides; direct URL shows "not in your plan") |
| Reject with reason (Org B) | PASS (empty reason blocked; reason shown to tenant; org stays on trial) |
| Billing during trial | PASS (Razorpay order 403 "not accepting online payments yet"); P3 wording on the public page (BUG-15) |

## 8. Admin provisioning

| Check | Result |
|---|---|
| Create Admin only after approval | PASS (button absent before) |
| Organization and Role read-only, role fixed to Admin; request body contains only name and email | PASS |
| Step-up | PASS (within the 15-min window) |
| Duplicate email | PASS (409 "already an active member", audited as DENIED) |
| Response has no token/link/password; `email_delivered: true` | PASS |
| Admin is a tenant user, not platform staff | PASS |
| Owner remains | PASS |
| Seat limit (4/4) | PASS (409 `SEAT_LIMIT_REACHED`) |
| Admin accepts invitation, signs in, sees only approved modules, approves discount | PASS |
| Deactivate Admin → sign-in refused | PASS (401 "not an active member") |
| Reactivate Admin | PASS |
| Audit: initiated / provisioned / invitation sent / activated | PASS (actor `<platform-administrator>`) |
| Operations / Support cannot create Admin | **BLOCKED** (accounts do not exist) |

## 9. Quotes / CPQ (financial verification)

**QT-000001**
- Lines: 3 × 1,234.50 = 3,703.50; 2.5 × 1,234.50 = 3,086.25
- Subtotal 6,789.75; 10% discount 678.975 → 678.98; taxable 6,110.77
- 18% tax 1,099.9386 → **1,099.94** (line taxes 599.97 + 499.97); total **7,210.71**: all match

Other checks:

| Check | Result |
|---|---|
| Send → email delivered → customer view (no internal fields rendered) → accept with name and confirmation | PASS |
| Accept again | PASS (idempotent) |
| Decline after accept | PASS (409) |
| **QT-000002**: 4 × 250.25 = 1,001.00; 25% = 250.25; tax 135.135 → 135.14; total **885.89** | PASS (matches) |
| Discount above the 20% threshold → pending approval | PASS |
| Owner self-approval | PASS (403 blocked) |
| Finance approval | PASS (403, needs Admin+) |
| Admin approval | PASS (200) |
| Send → customer declines with reason; accept after decline | PASS (409) |
| Emailed quote link resolves to the right quote | PASS |
| Invalid quote token | PASS (404 page) |
| Quote PDF | Not separately downloaded (invoice PDF verified) |

## 10. Invoices, payments, credit notes

**INV-000001** (from QT-000001): identical totals, due +30 days; sent, email delivered; PDF totals correct.

**Payments:**
- Partial 2,000.50 → partially_paid, due 5,210.21 ✓
- Overpay by 0.01: 422 ✓
- Zero / negative: 422 ✓
- Future date: 422 ✓
- Idempotency-Key replay: same PAY-000004 ✓
- Duplicate bank reference: accepted silently (BUG-18)
- 1.005: silently stored as 1.01 (P4)
- Paid total 2,000.50 + 1.01 + 100 + 10 = 2,111.51 ✓

**CN-000001:**
- 500 + 18% IGST = 590.00 ✓
- Applied 300 then 290 ✓
- Over-apply 300 against 290, or 290.01: 409 ✓
- Invoice due 7,210.71 − 2,111.51 − 590 = **4,509.20** ✓

**Timesheet invoice INV-000003:**
- 2.5 h × 100 = 250 + 45 = **295.00** ✓
- Draft, rejected and already-billed entries cannot be invoiced (UI and API, 409) ✓

**Subscription SUB-000001:**
- AED 367.25 + 18% = AED 433.36 ✓
- But billed in AED to an INR customer without warning (BUG-12)

**Payments online:** no gateway configured (BUG-03). The customer pay page degrades gracefully ("Online payment unavailable… contact them").

## 11. Customer portal

| Check | Result |
|---|---|
| Activation from invitation | PASS |
| Own invoices, payments and subscriptions only | PASS |
| Another customer's invoice | PASS (404) |
| Tenant API rejects portal token | PASS (401) |
| Used/replaced activation link | PASS ("already been used") |
| 375 px | PASS (no horizontal scroll) |
| Pay Now | Opens `/pay/[TOKEN]` in a new tab (gateway unavailable message) |
| Outstanding amount | **FAIL** (BUG-02) |
| Portal quotes | Not offered (no portal quotes section/API); customers act on quotes via the emailed link |

## 12. Role and permission matrix (server-side verified)

| Action | Owner | Admin | Finance | Viewer | Customer (portal) | Platform Admin |
|---|---|---|---|---|---|---|
| Read customers/invoices | ✅ | ✅ | ✅ | BLOCKED | own only ✅ | ❌ (metadata only) |
| Create customer | ✅ | ✅ | ✅ | BLOCKED | ❌ | n/a |
| Approve discount > threshold | own ❌ (403) | ✅ | ❌ (403) | BLOCKED | n/a | n/a |
| Approve time entry | own ❌ (403) | n/t | ✅ | BLOCKED | n/a | n/a |
| Invite team member | ✅ | ✅ (seat limit) | ❌ (403) | BLOCKED | n/a | n/a |
| Edit organization | ✅ | ✅ | ❌ (403) | BLOCKED | n/a | n/a |
| Submit subscription request | ✅ | n/t | ❌ (403) | BLOCKED | n/a | n/a |
| Platform API with tenant token | ❌ (401) | ❌ (401) | ❌ (401) | BLOCKED | ❌ | ✅ |
| Approve/reject requests, Create Admin, suspend | n/a | n/a | n/a | n/a | n/a | ✅ with step-up |

Operations and Support: **BLOCKED** (no such accounts in production).

## 13. Tenant isolation

| Probe | Result |
|---|---|
| Org B → Org A (customer GET/PATCH/DELETE, portal-access, quote GET, quote send, offering GET, approval approve, team member DELETE, quote creation with A's customer or offering) | 404 or 422 on every attempt; no data returned |
| Org A → Org B (customer GET/PATCH, quote GET/DELETE/send) | 404 |
| `X-Organization-ID` / `X-Org-Id` / `X-Tenant-ID` spoofing | Ignored |
| Search for A's customer from B | Empty |

## 14. Security

| Check | Result |
|---|---|
| HTTPS + HSTS (1 year, includeSubDomains) | PASS |
| CSP present; `frame-ancestors 'self'`; `nosniff`; Referrer-Policy; Permissions-Policy | PASS |
| **Duplicate and conflicting headers on API responses** | P4 (BUG-25): two CSPs (app adds `script-src 'unsafe-inline'`, nginx's is stricter); browsers enforce both, so the stricter wins. `X-Frame-Options` sent as both DENY and SAMEORIGIN; superseded by CSP `frame-ancestors`. Recommend emitting each header once. |
| CORS | PASS (foreign origin gets no `Access-Control-Allow-Origin`) |
| CSRF on platform API | PASS (403 "Missing or invalid CSRF token") |
| Platform cookies | PASS (`__Host-`, httpOnly, Secure, SameSite=Strict) |
| Tenant and portal tokens | P3 (BUG-21): stored in `localStorage` (access + refresh; portal token) |
| XSS / HTML injection (catalog name, expense title, customer fields, editor heading, public quote) | PASS: rendered as text, no dialogs, no injected elements |
| CSV-formula customer name | Rejected by validation |
| Open redirect `/login?next=…` | PASS (stays on `/login`) |
| Platform step-up | PASS (`STEP_UP_REQUIRED` → password → 15-min window, audited) |
| Information leaks | **FAIL**: BUG-04 (public `pricing_explanation`), BUG-06 (merchant receives customer portal activation link) |

## 15. Email

Delivered and confirmed by the inbox owner:
- signup OTP (Org A, and Org B twice)
- quote QT-000001 and QT-000002 emails (link verified)
- invoice INV-000001 email
- Finance invitation
- Admin invitation
- portal invitation
- password reset (link verified end to end)

Not received: Viewer invitation, **twice** (original and resend). Cause unconfirmed, possibly mailbox filtering (BUG-26, P3).

Not inspected: subscription approval and rejection emails to the Owner. The app reports sending them.

## 16. Audit log

| Check | Result |
|---|---|
| Platform audit covers: login, step-up required/succeeded, request approved-with-changes (with reason and ticket), admin provisioning initiated / DENIED duplicate / provisioned / invitation sent / activated, deactivate/reactivate, suspend/reactivate, organization viewed | PASS |
| Actor, role, org and result on each entry; append-only by design | PASS |
| **Tenant-originated events** (organization created, trial started, subscription request submitted) | Show actor **"unknown"** (BUG-16) |

## 17. Visual editor (draft/preview only, as instructed)

| Check | Result |
|---|---|
| 41 pages selectable; component tree; desktop/tablet/mobile (390 px) preview | PASS |
| `<script>`, `<img onerror>` and `javascript:` in heading → rendered as literal text, no execution | PASS |
| Undo returned to the published state; Save draft and Publish disabled | PASS: nothing saved, published or rolled back |
| Draft save / reload / publish / history / rollback | **NOT APPLICABLE** (excluded by instruction) |

## 18. DevTools findings

| Area | Finding |
|---|---|
| Console | No JavaScript exceptions or React crashes across the audit. Console "failed to load resource" lines correspond to expected 4xx from security probes and invalid-token pages. |
| Network | 3,917 API calls. One 5xx: `POST /expenses` with amount 1e15 → 500 (BUG-19). No duplicate POSTs observed; Idempotency-Key honoured; no requests after logout; no cross-tenant data in any response. |
| Application | Tenant `rooman.access_token` / `rooman.refresh_token` and portal `rooman.portal_token` in localStorage (BUG-21). Platform uses httpOnly cookies. No passwords, OTPs or reset/invite tokens persisted in storage. |

## 19. Responsive

| Check | Result |
|---|---|
| 46 tenant routes at 390 px | No horizontal scroll |
| Public pages at 390 px | No horizontal scroll |
| Portal at 375 px | No horizontal scroll |
| Platform console | No horizontal scroll at 1440 |

## 20. Bugs

| ID | Sev | Area | Summary |
|---|---|---|---|
| BUG-01 | **P1** | Reports / Collections / Invoice summary / Customer report / Dashboard trend | Totals add different currencies and label the sum ₹ |
| BUG-02 | **P1** | Customer portal | "Outstanding ₹4,942.56" and "Pay Outstanding (₹4,942.56)" mix INR + AED |
| BUG-03 | **P1** (config) | Payments | Payment gateway not configured in production; no org can collect online |
| BUG-04 | P2 | Public quote/invoice API | `pricing_explanation` exposes catalog base price and price-book adjustments |
| BUG-05 | P2 | Quote/invoice detail (internal) | Raw pricing JSON rendered under every line item |
| BUG-06 | P2 | Customer portal invite | Merchant API returns the customer's activation link (`invite_url`) on invite and on GET portal-access |
| BUG-07 | P2 | Invoice PDF (GST) | Titled "BILL OF SUPPLY" yet charges IGST; org without GSTIN can charge GST. **Needs qualified GST review** |
| BUG-08 | P2 | Quote form | Preview shows CGST 9% + SGST 9%; saved quote is IGST 18% inter-state |
| BUG-09 | P2 | Customers | Names with accented, Arabic or Chinese letters, `#` or `/` rejected (e.g. "Müller GmbH", "شركة الاختبار") |
| BUG-10 | P2 | Catalog list | USD and AED offerings displayed with ₹ |
| BUG-11 | P2 | Expenses | Currency not validated ("XYZ" accepted); list totals sum currencies as ₹ |
| BUG-12 | P2 | Subscriptions | INR customer silently subscribed and invoiced in AED (no currency mismatch warning) |
| BUG-13 | P2 | Quote form | Added line inherits the previous line's offering; typed price replaced by catalog price on quantity change |
| BUG-14 | P3 | Collections vs Reports | Collection rate 37.47% vs 29.28% (credit notes counted differently) |
| BUG-15 | P3 | Public invoice (trial org) | Says "account temporarily unavailable… no changes can be made" instead of "online payments not enabled yet" |
| BUG-16 | P3 | Platform audit | Tenant-originated events show actor "unknown" |
| BUG-17 | P3 | Console org page | "Billing automation: Running" shown for a trial org whose billing is held |
| BUG-18 | P3 | Payments / Customers | Duplicate payment reference and duplicate customer email accepted without warning |
| BUG-19 | P3 | Expenses API | Very large amount → 500 instead of 422 |
| BUG-20 | P3 | Expenses | "Incurred this month ₹0" while three expenses are dated this month |
| BUG-21 | P3 | Auth storage | Tenant/portal tokens in localStorage (XSS-reachable; mitigated by strict CSP) |
| BUG-22 | P3 | Accessibility | Unlabelled inputs on expense, timesheet and portal sign-in forms |
| BUG-23 | P3 | Timesheets | Project is free text, not linked to Projects records |
| BUG-24 | P3 | Currency coverage | Quotes INR/USD/EUR/GBP only; expenses INR/USD/EUR; offering form has no currency; AED/SGD/AUD/CAD missing despite a `.ae` deployment |
| BUG-25 | P4 | HTTP headers | Duplicate/conflicting CSP and X-Frame-Options on API responses |
| BUG-26 | P3 | Email | Viewer invitation email not received twice (others delivered) |
| BUG-27 | P4 | Reset password | Invalid token shows the form; rejected only on submit (server-side behaviour correct) |
| BUG-28 | P4 | Invoice | Invoice keeps quote terms "Quote valid for 30 days" |
| BUG-29 | P4 | Formatting | ₹1234.50 (no separator) in catalog; "₹1,234.5" on quote; expenses drop paise; quote form total rounded to ₹7,211 |
| BUG-30 | P4 | Payments | 1.005 silently rounded to 1.01 (offerings reject 3 decimals) |
| BUG-31 | P4 | Signup | Expired OTP message "No pending signup found" instead of "code expired" |
| BUG-32 | P4 | Console | "Reactivate" action shown for an invited (never active) Admin |
| BUG-33 | P4 | Console health | Scheduler "Enabled: No" while it runs every 15 min |
| BUG-34 | P4 | Team | No explicit "Resend invitation" (re-inviting the same email works) |
| BUG-35 | P4 | Payments API | Plain-date `paid_at` between 00:00 and 05:30 IST rejected as future (UI unaffected) |
| BUG-36 | P4 | Visual editor | Preview iframe sandbox `allow-scripts allow-same-origin` (no exploit found; content is text-only) |
| BUG-37 | P4 | Admin invitation | Name entered by Super Admin not prefilled on the invitation form |

### Reproduction and recommendations (P1/P2)

**BUG-01: currencies mixed in reports and dashboards**
- Repro: in one org, create an INR invoice (₹7,210.71) and an AED subscription invoice (AED 433.36). Open Reports, Collections and the Dashboard trend.
- Network: `GET /reports/dashboard` → `total_invoiced: "7644.07"`, `outstanding_receivables: "4942.56"`; `GET /collections/dashboard` → `total_outstanding: "4942.56"`.
- Fix: group every monetary aggregate by currency (the dashboard Outstanding card already does), or convert with explicit FX and label it.

**BUG-02: wrong amount in the customer portal**
- Repro: portal for a customer with INR and AED invoices; the overview shows ₹4,942.56.
- Fix: show per-currency balances; never offer "Pay Outstanding" across currencies.

**BUG-03: no payment gateway**
- Evidence: System health "Payment gateway not configured"; `POST /public/invoices/[TOKEN]/razorpay-order` → 503 `GATEWAY_NOT_CONFIGURED`.
- Fix: configure Razorpay live keys (operational change, owner approval required), then re-test checkout in Razorpay test mode first.

**BUG-04: public pricing leak**
- Repro: `GET /api/v1/public/quotes/[TOKEN]` or `/public/invoices/[TOKEN]`; each item has `pricing_explanation` with `catalog_base_price` and `price_book_adjustment`.
- Fix: drop it from public schemas.

**BUG-05: raw JSON on internal pages**
- Fix: render the explanation as a tooltip or table, or hide it.

**BUG-06: customer activation link given to the merchant**
- Repro: Customer → Send Invitation; the response `invite_url` contains the activation token. `GET /customers/{id}/portal-access` returns it again.
- Fix: return it only when email delivery fails, and only to Admin+. Never on GET.

**BUG-07: GST document type**
- Repro: org without a GSTIN; invoice to a GST-registered customer; the PDF says "BILL OF SUPPLY" with IGST ₹1,099.94.
- Fix: decide with a GST adviser. Either block GST for unregistered suppliers, or require a GSTIN and title it "TAX INVOICE".

**BUG-08: tax split changes on save**
- Fix: compute the preview with the same supply rules as the server (org state unset → inter-state).

**BUG-09: international names rejected**
- Repro: `POST /customers` with `display_name: "Müller GmbH"` → 422 "contains invalid characters".
- Fix: allow Unicode letters (`\p{L}`) and common punctuation; keep the HTML/formula guards.

**BUG-10 to BUG-12: currency handling**
- Display the offering's own currency; validate ISO 4217 codes; warn or prevent when the plan currency differs from the customer currency.

**BUG-13: quote line price overwritten**
- Repro: new quote → line 1 select an offering → Add Item → line 2 enter a description, quantity 2.5 and price 999.99 → saved line 2 has the offering's 1,234.50.
- Fix: new lines default to "Custom Item"; don't overwrite a manually entered price.

## 21. Blocked / not applicable

| Item | Status | Reason |
|---|---|---|
| Viewer role tests | BLOCKED | Invitation email not received (twice) |
| Operations / Support platform roles | BLOCKED | Accounts do not exist in production |
| Trial expiry → subscription-only screen | BLOCKED | Requires waiting 72 h in production |
| Online checkout, webhooks, refunds, receipts | BLOCKED | Gateway not configured; no real money allowed |
| Dunning / renewal automation runs | BLOCKED | Scheduler-driven; not observable within the window without real collection |
| Report CSV/PDF exports | BLOCKED | Export controls not located before Reports was removed from Org A's plan |
| Subscription decision emails | BLOCKED | Not inspected in the mailbox |
| Visual editor save/publish/rollback | NOT APPLICABLE | Excluded by instruction (preview only) |
| PR #32 features in production | NOT APPLICABLE | #32 not deployed (CI fix PR #34 awaiting authorized merge) |

## 22. Cleanup status

**Not completed. Both QA organizations remain ACTIVE.**

Mechanism (verified, dialog opened and cancelled): **Schedule deletion** in the platform console moves an org to *Pending deletion*. It is cancellable, stops billing automation, and needs a reason, a ticket reference and step-up. The final purge is a separate server-side step **not available in the console**, so full removal cannot be completed through the UI either way.

Attempt 1:
- Org A's schedule-deletion returned 403 `STEP_UP_REQUIRED`.
- The step-up password was then entered six times, but every attempt returned 401 "Platform authentication required": the platform session had idle-expired while the dialog was open.
- The dialog kept showing the error instead of sending the user to sign in (BUG-38, P3).

Attempt 2: a script waited 10 minutes for platform sign-in; no sign-in occurred and it timed out. No state-changing request was sent.

Remaining cleanup (post-audit task):
- Schedule deletion for `d47d8fcf-0c40-4f6d-9d7f-30a42456cc53` (ROOMAN QA AUDIT 2026-10-08) and `52e279ba-3559-4b05-80dc-69fdf9bcf994` (ROOMAN QA AUDIT B 2026-10-08) from the console.
- The final purge needs the server-side process owner.

| BUG-38 | P3 | Console step-up | When the platform session has expired, the password dialog repeats "Platform authentication required" on every attempt instead of redirecting to sign-in; users think their password is wrong |

## 23. Evidence

**Evidence files are not in this repository.** Screenshots, PDFs, CSV exports and logs can contain customer-like data, session details and personal QA addresses, so they are kept in the QA team's private audit archive and are not committed. File names in this document (for example in the "Evidence" columns of sections 5 and 24) identify files in that archive; they are not links. Ask the QA owner for access.

Archive contents:
- 155 screenshots (public pages, 92 tenant route captures, console pages, editor preview, portal, quote/invoice/payment states)
- `inv1.pdf` (invoice PDF)
- `netlog.jsonl` (redacted network/console log, 3,917 API calls)
- `sweep_owner/sweep.json`
- `public_pass.json`

---

## 24. Continuation: 9–10 Oct 2026 (outstanding checks)

Fresh browser sessions as the Org A and Org B Owners, production only, build `a7a67b7` (unchanged; PR #34 still open and not deployed). All data synthetic and inside the two QA organizations.

Areas not in Org A's plan (Reconciliation, Automation, Reports) were tested in Org B, which is still on its all-module trial. No real payments, refunds or external emails beyond the QA Gmail aliases.

**Tester error, disclosed:** while inspecting dialogs, a "Cancel" button lookup also matched "Confirm Cancellation", and **SUB-000001** (QA, AED) was cancelled immediately. That result is used as the immediate-cancel test (C-A7).

### 24.1 Checks run

File names in the Evidence column refer to the private audit archive (section 23), not to files in this repository.

| ID | Area / page | Org | Steps and result | Status | Evidence |
|---|---|---|---|---|---|
| C-A1 | Subscription create (INR) | A | SUB-000002, 2 × ₹1,000 → ₹2,360; UI snapshot = API = INV-000005 | PASS | netlog |
| C-A2 | Upgrade / downgrade (UI) | A | Proration picker lists only the current plan; no catalog or Plans & Pricing plan can be chosen | **FAIL (BUG-42)** | c_proration_picker.png |
| C-A3 | Upgrade via API (`target_offering_id`) | A | Credit ₹2,000 (+tax ₹2,360, CN-000002), charge ₹5,000 (+tax ₹5,900, INV-000006); due ₹3,540 = net ₹3,000 + 18%; no charge (no card) | PASS | netlog |
| C-A4 | Downgrade immediate | A | INV-000007 ₹2,360 fully offset by CN-000003 ₹5,900; ₹3,540 credit left | PASS | netlog |
| C-A5 | Scheduled resize (end of term) and cancel it | A | Saved as `scheduled` for 2026-11-09, quantity unchanged; cancel → `cancelled` | PASS | netlog |
| C-A6 | Pause / resume | A | Paused (next billing cleared); renew while paused → 409; resume restores the date | PASS | netlog |
| C-A7 | Cancel immediately / at period end | A | Immediate: status cancelled, `ended_at` set (record keeps MRR, BUG-55). Period end: stays active, `cancel_at_period_end: true` | PASS | c_sub_cancelled.png |
| C-A8 | Manual renew | A | 409 "not due for renewal yet" although the button offers it (BUG-45). Successful renewal needs 9 Nov | BLOCKED (time) + FAIL (BUG-45) | netlog |
| C-A9 | Proration preview maths | A | 31-day period, day 0: credit 2,000, charge 3,000, net 1,000 | PASS | netlog |
| C-A10 | Trial subscription | A | 7-day trial: `trialing` 9→16 Oct, no invoice, on Trials page; MRR excludes trial; Convert → active, INV-000008 ₹1,180 unpaid, no payment attempt | PASS | netlog |
| C-A11 | Usage meters | A | Meter created (code lowercased); event 100; same idempotency key returns the same event; 50 more; negative → 422 | PASS | c_usage.png |
| C-A12 | Usage visibility | A | After reload, no events or totals shown; "The API does not list historical events" | **FAIL (BUG-44)** | c_usage.png |
| C-A13 | Finalize cycle | A | 150 × ₹0.50 = ₹75 → usage invoice ₹88.50. Re-finalizing a "frozen" cycle deletes and re-issues the invoice: INV-000009 and INV-000010 consumed, INV-000011 current | **FAIL (BUG-43)** | netlog |
| C-B1 | Reconciliation model | B | Allocation-based; page states no bank or gateway feed is ingested | NOT APPLICABLE (bank import) | c_recon_B.png |
| C-B2 | Matched / unmatched / exception counts | B | 1 matched, 1 unmatched (advance ₹300), 1 exception (₹220 unapplied); unallocated ₹520; persists after refresh; UI = API | PASS | c_recon_B.png |
| C-B3 | Manual allocation (UI) | B | ₹200 to INV-000002 → paid 200 / due 272; picker lists only same-customer invoices | PASS | netlog |
| C-B4 | Allocation guards | B | Over payment, paid invoice, duplicate line, zero and negative → 422 | PASS | netlog |
| C-B5 | Cross-customer allocation | B | Customer B's payment applied to Customer B2's INV-000004 → 200, due 118 → 108 (reverted) | **FAIL (BUG-39, P1)** | netlog |
| C-B6 | Cross-currency allocation | B | INR payment applied to USD INV-000003 → 200, $5 marked paid (reverted) | **FAIL (BUG-40, P1)** | netlog |
| C-C1 | Checkout session | A | Created (₹2,360, 2 h); draft invoice → 409; 0 h / 10,000 h → 422; form lists drafts (BUG-58); relative link (BUG-60) | PASS | netlog |
| C-C2 | Checkout page (anonymous, 390 px) | A | "Online payment is currently unavailable"; disabled button; no horizontal scroll; no console errors | PASS | c_checkout_390.png |
| C-C3 | Checkout templates | A | Server stores `javascript:` / external redirect and `javascript:` logo; session creation with the `javascript:` redirect → 422; HTML button text escaped | **FAIL (BUG-47)** | netlog |
| C-C4 | Live payment, webhooks | — | No gateway configured | BLOCKED | — |
| C-D1 | Automation rule CRUD | B | Create (condition total > 100, email to QA alias), edit persists after reload, toggle off, delete | PASS | netlog |
| C-D2 | Webhook SSRF | B | 169.254.169.254, localhost, 10.x and `javascript:` refused; plain `http://` allowed (BUG-59) | PASS | netlog |
| C-D3 | Dry-run test | B | total 150 → matches; total 50 → no match; no actions executed | PASS | netlog |
| C-D4 | Trial gate | B | Enabled rule did not fire on a qualifying invoice in the trial org; no logs | PASS | netlog |
| C-D5 | Rule firing in an entitled org | — | Org A not entitled to Automation | BLOCKED | — |
| C-E1 | Document template | A | Created; default invoice template applied to the PDF (header and footer shown, HTML escaped) | PASS | c_inv5_template.pdf |
| C-E2 | Template preview | A | Rendered in `sandbox="allow-same-origin"` iframe without `allow-scripts`; injected script did not run | PASS | c_template_preview.png |
| C-E3 | Custom CSS | A | `</style><script>` and `@import`/`url()` to 169.254.169.254 stored unsanitized; server-side fetch not observable | **FAIL (BUG-48)** | netlog |
| C-E4 | Template document type | A | Invoice template also applied to the **quote** PDF | **FAIL (BUG-49)** | c_quote1.pdf |
| C-F1 | Numbering | A | Lowering next number → 422 "cannot be decreased" (no duplicates); prefix change → QAINV-000013; restored to INV- | PASS | netlog |
| C-F2 | Prefix validation | A | `<b>X</b>` accepted as prefix (restored) | **FAIL (BUG-50)** | netlog |
| C-F3 | GST with org GSTIN and state (KA) | A | Preview CGST 9% + SGST 9% = saved intra_state (111.11 + 111.10 = 222.21); PDF titled TAX INVOICE with org GSTIN; profile restored | PASS (narrows BUG-07/08 to orgs without GSTIN or state; still open) | c_inv_tax.pdf |
| C-G1 | Quote PDF | A | Totals correct, but each catalog line prints `<br/><font color=…>` and the full pricing JSON | **FAIL (BUG-41, P1)** | c_quote1.pdf |
| C-G2 | Report CSV exports (8) | B | All download; values match UI and API; own tenant only; unauthenticated → 401; no currency column, so mixed totals go out unlabeled (BUG-01); no PDF export and no export on Invoices/Customers/Products | PASS (values) / BUG-01 evidence | c_export_*.csv |
| C-H1 | Button-by-button audit | B | 197 non-destructive controls on 39 pages; no write request on cancel or close; no dialog trapped; no console errors; flagged controls rechecked individually. Destructive controls not clicked by policy | PARTIAL | c_button_audit_B.json |
| C-H2 | Quick-action deep links | A/B | Dashboard "Add Customer" → `/customers?action=new` shows the list, not the form; same for `/catalog?new=product` and `/payments?new=1` | **FAIL (BUG-51)** | — |
| C-H3 | Dashboard customization | B | Hiding a widget is not saved (no API call, no storage); reverts on reload | **FAIL (BUG-52)** | — |
| C-I1 | Responsive 1280 / 1024 / 768 | B | 46 routes × 3 widths: no page-level horizontal scroll, no console or API errors; tables and tabs scroll inside their containers | PASS | sweep_responsive_B/ |
| C-I2 | Dashboard at 1024 px | B | Outstanding value truncated ("₹390.00…"), Payment Status legend counts clipped, Quick Actions labels cut to one letter | **FAIL (BUG-53)** | w1024_dashboard.png |

Responsive coverage is now **1440, 1280, 1024, 768, 390 and 375 px**: all six widths.

### 24.2 New bugs

| ID | Sev | Area | Summary | Repro (short) | Fix |
|---|---|---|---|---|---|
| BUG-39 | **P1** | Payments / reconciliation | A payment can be allocated to **another customer's** invoice | `PUT /payments/{payB}/allocations` with Customer B2's invoice → 200; B2's balance drops | Reject allocations whose invoice customer ≠ payment customer (server-side) |
| BUG-40 | **P1** | Payments / reconciliation | A payment can be allocated to an invoice in **another currency**, converted 1:1 | INR payment → USD invoice, ₹5 = $5 paid | Reject currency mismatch, or require explicit FX |
| BUG-41 | **P1** | Quote PDF (customer document) | Raw `<br/><font …>` markup and the full pricing JSON (catalog base price, price-book adjustment) printed on every catalog line | Download the PDF of any quote with catalog items | Strip `pricing_explanation` from customer documents; render descriptions as text |
| BUG-42 | P2 | Proration UI | Upgrade/downgrade picker lists only the current plan; plans from Catalog or Plans & Pricing never appear (they are offerings). Backend accepts `target_offering_id` | Proration → Upgrade tab → only "(Current)" | Feed the picker from plan offerings / plan-options |
| BUG-43 | P2 | Usage billing | Re-finalizing a "frozen" cycle deletes and re-issues the usage invoice, consuming invoice numbers (INV-000009 and 000010 missing) | Finalize the same cycle twice | Make finalize idempotent (return the existing invoice); never delete numbered invoices |
| BUG-44 | P2 | Usage | Recorded usage and running totals are not viewable after reload; no history API | Record usage, reload Usage page | Add event history and per-meter aggregate endpoints and UI |
| BUG-45 | P3 | Subscriptions | "Renew" offered (and promises to advance the period) but the server refuses until the due date | Renew on a current subscription → 409 | Hide or disable Renew until due, or explain |
| BUG-46 | P3 | API validation | Unknown request fields silently ignored (e.g. `effective` → change applied immediately; template `success_url` ignored) | POST with a misspelt field | Reject unknown fields (`extra=forbid`) on write schemas |
| BUG-47 | P3 | Checkout templates | Stores `javascript:` / any external redirect and `javascript:` logo despite "only http(s) accepted"; a `javascript:` redirect is only caught when a session is created | POST /checkout/templates with `redirect_url: javascript:…` → 201 | Validate scheme and allow-list redirect hosts at save time |
| BUG-48 | P3 | Document templates | Custom CSS stored unsanitized (`</style><script>`, `@import`/`url()` to internal IPs); renderer fetch behaviour unverified | Create a template with that CSS | Sanitize CSS; block `@import`/`url()` to non-allow-listed hosts in the PDF renderer |
| BUG-49 | P3 | Document templates | Invoice template applied to quote PDFs | Default invoice template → quote PDF shows its header | Apply templates by document type |
| BUG-50 | P3 | Numbering | Invoice prefix accepts HTML (`<b>X</b>`) | PATCH /organization | Restrict prefixes to `[A-Z0-9-/]` |
| BUG-51 | P3 | Quick actions | Dashboard "Add Customer" and `?new=` deep links land on lists, not forms | Click Add Customer on the dashboard | Honour `action=new` / `new=` params |
| BUG-52 | P3 | Dashboard | Widget customization not persisted | Hide a widget, Done, reload | Persist per user (API) |
| BUG-53 | P3 | Responsive (1024 px) | Dashboard KPI value truncated, legend counts and quick-action labels clipped | 1024 px viewport | Wrap or stack KPI and legend content |
| BUG-55 | P4 | Subscriptions | Cancelled subscription record keeps `mrr` and `auto_renewal: true` (dashboards correctly show 0) | — | Zero MRR on cancel |
| BUG-56 | P4 | Subscriptions | Summary `auto_renew_enabled_count: 0` although auto-renew is on; `trial_end` unchanged after early conversion | — | Fix counters; set `trial_end` on convert |
| BUG-57 | P4 | Proration | One "Preview Change" click sends two identical preview requests | — | De-duplicate |
| BUG-58 | P4 | Hosted payment pages | Session form lists draft invoices (server refuses them) | — | Filter drafts |
| BUG-59 | P4 | Automation | API accepts an empty rule name; plain `http://` webhooks allowed | — | Validate name; prefer https |
| BUG-60 | P4 | Hosted payment pages | Checkout session API returns a relative URL | — | Return an absolute URL |

(BUG-54 not used. CSV exports lacking a currency column are recorded under BUG-01. The allocation picker showing "₹11.80" for a USD invoice is recorded under BUG-40/BUG-10.)

### 24.3 Remaining blockers (verdict unchanged: **NOT READY**)

**P1, must fix:**
1. **BUG-03** No payment gateway in production: no online collection.
2. **BUG-01 / BUG-02** Mixed-currency totals in reports, collections, dashboard, CSV exports and the customer portal.
3. **BUG-39 / BUG-40** Payments can be applied to other customers' and other currencies' invoices (financial integrity).
4. **BUG-41** Internal pricing JSON printed on customer quote PDFs.

**Prioritised remediation:**
1. Server-side allocation guards (customer and currency).
2. Remove `pricing_explanation` from all customer-facing outputs (PDF, public API).
3. Per-currency aggregation everywhere.
4. Configure and test the gateway in Razorpay test mode, then live.
5. GST document type for orgs without a GSTIN (needs GST adviser).
6. Usage finalize idempotency and invoice-number integrity.
7. Plan picker for upgrades and downgrades.
8. Unicode customer names.
9. P3/P4 backlog.

### 24.4 QA data added in the continuation (still to clean up)

**Org A:**
- offerings QA-BASIC-INR, QA-PRO-INR, QA-PLAN-PRO (and its plan records)
- SUB-000001 cancelled; SUB-000002 active, cancel at period end, ₹2,000 MRR; SUB-000003 converted trial
- invoices INV-000005 to 000008, 000011 to 000014 (QAINV-000013); CN-000002, CN-000003; QT-000003
- meter `qa_api_calls`; checkout sessions (3) and templates (5); invoice document template "QA Invoice Template" (default)

**Org B:**
- customer QA Customer B2; invoices INV-000001 to 000005; payments PAY-000001 to 000003
- automation rule "QA invoice over 100 alert (edited)", disabled

Cleanup is **not** part of this continuation. It requires explicit approval and a fresh Super Admin sign-in.
