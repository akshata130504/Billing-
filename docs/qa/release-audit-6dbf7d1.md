# Rooman Billing — Production Release Audit (release 6dbf7d1)

| | |
|---|---|
| Production URL | https://billing.futureacad.ae |
| Release commit | `6dbf7d1129716437a355a7398ce087e47b2bd597` (PR #38 "mvp-release-ready", merged 2026-10-12 06:39 UTC) |
| Audit window | 2026-10-12, ~07:30–08:30 UTC |
| Scope | Whole application **excluding email delivery and payment processing** (excluded, not tested) |
| Method | Production UI and API through Playwright (headed Chromium) with network/console capture; synthetic data in the two QA orgs only |
| **Recommendation** | **CONDITIONALLY READY — limited pilot only. Not "READY FOR USERS"** (section 10) |

## 1. Deployment verification

| Check | Result |
|---|---|
| Deploy workflow for 6dbf7d1 | success, 2026-10-12 06:59 UTC (CI success 06:39) |
| Frontend build served | `Last-Modified: 06:59:11 UTC`, bundle `main-Bs2w-x9M.js` (rebuilt by this deploy) |
| API health | healthy, database connected, environment production |
| Migrations | at head `4c5d6e7f8091` (console System health); the release added no migrations |
| Scheduler | running, last run within interval, 0 errors |

## 2. Roles (8)

From `MemberRole` (owner, admin, finance, viewer), `PlatformRole` (platform_administrator, platform_operations, platform_support) and the portal customer.

| Role | Result | Evidence |
|---|---|---|
| Owner | **PASS** | Full module access per plan; tenant isolation both ways (earlier audit); plan-gated modules 403 |
| Admin | **PASS** | Login 200; org edit 200; invites held by seat limit (409); out-of-plan module 403; platform API 401 |
| Finance | **PASS** | Read/create allowed; org edit, invitations, subscription request 403; platform API 401 |
| Viewer | **BLOCKED** | No Viewer account: the invitation email never arrived (email excluded) |
| Platform Administrator | **PASS** | Sign-in by account owner; step-up on sensitive actions; CSRF; console pages; plan change audited |
| Platform Operations | **BLOCKED** | No such account exists in production (staff are created only via the server CLI) |
| Platform Support | **BLOCKED** | As above |
| Portal customer | **PASS** | Own invoices only; another customer's invoice 404; portal token refused by tenant API (401); per-currency balance |

**Result: 5 PASS, 3 BLOCKED.** The "all 8 roles tested" criterion is **not met**.

## 3. The 59 original bugs

All 59 IDs are present: BUG-01–53 and BUG-55–60 (BUG-54 was never assigned). No duplicates. Severities as originally assigned: P1 6, P2 13, P3 22, P4 18.

Statuses: **PASS** (fixed, verified on production) · **PARTIAL** (part verified) · **FAIL** (still reproducible) · **NOT VERIFIED** · **BLOCKED** · **EXCLUDED** (email/payment).

| Bug | Sev | Status | Production evidence (2026-10-12) |
|---|---|---|---|
| BUG-01 | P1 | **PASS** | Collections base total ₹11,648.20 = independent INR sum, AED in `kpis_by_currency`. Reports UI "₹19,069.71 · AED 433.36". Dashboard trend per currency. CSV has a `currency` column. |
| BUG-02 | P1 | **PASS** | Portal "₹10,409.20 · AED 433.36" = independent sum (4,509.20 + 2,360 + 3,540). No combined pay button. |
| BUG-03 | P1 | **EXCLUDED** | Payments out of scope. Reclassified by product owner as configuration pending office approval. |
| BUG-04 | P2 | **PASS** | Public quote and invoice payloads contain no `pricing_explanation`. |
| BUG-05 | P2 | **PASS** | Quote detail shows no raw JSON. |
| BUG-06 | P2 | **PASS** | GET portal-access `invite_url` is null. |
| BUG-07 | P2 | **PASS** | No-GSTIN org: new invoice tax 0.00; PDF "BILL OF SUPPLY", no GST lines. (Rule per product owner; legal review still advised.) |
| BUG-08 | P2 | **PASS** | No-GSTIN quote preview "GST ₹0" plus notice, matching the server. |
| BUG-09 | P2 | **PASS** | "Müller GmbH", Arabic, "José Ñúñez", "QA-Co_1 / Unit #2" → 201. `<script>`, `=HYPERLINK` → 422. |
| BUG-10 | P2 | **FAIL** | Catalog still shows "QA Service USD … ₹100.00/unit". |
| BUG-11 | P2 | **FAIL (partial)** | Currency "XYZ" now 422 ✓. Expense KPIs still sum currencies as ₹ ("Total ₹3,566.70" = ₹2,360.80 + 1,180.40 (legacy XYZ) + $25.50). |
| BUG-12 | P2 | **PASS** | INR customer on AED plan → 422 with a clear message. |
| BUG-13 | P2 | **PASS** | New quote line = "Custom Item"; typed 999.99 kept after quantity change. |
| BUG-14 | P3 | **PASS** | Collection rate INR 11.1% · AED 0% on both Reports and Collections (API 11.13 / 11.13). |
| BUG-15 | P3 | **NOT VERIFIED** | Needs a trial org's public invoice. Org B's trial expired today, so its APIs are locked. |
| BUG-16 | P3 | **PASS** | Fresh tenant events show actor `<qa-inbox>+qaownerb@<qa-domain>`. (Scheduler "trial expired" still shows "unknown"; separate minor follow-up.) |
| BUG-17 | P3 | **PASS** | Console: "Held - trial (no approved subscription)". |
| BUG-18 | P3 | **PASS** | Duplicate email and duplicate payment reference return warnings. |
| BUG-19 | P3 | **PASS** | Expense amount 1e15 → 422. |
| BUG-20 | P3 | **PASS** | "Incurred this month" no longer ₹0 (inherits the BUG-11 mixing). |
| BUG-21 | P3 | **FAIL** | Tenant and portal tokens still in localStorage. Product-owner decision pending (impact assessed: 20–26 h, recommended post-MVP). |
| BUG-22 | P3 | **PARTIAL** | Timesheet form fully labelled. Expense/portal/usage forms not re-checked. |
| BUG-23 | P3 | **FAIL** | Timesheet project is still free text (no project selector). |
| BUG-24 | P3 | **FAIL** | Quote currencies INR/USD/EUR/GBP only; offering form has no currency. |
| BUG-25 | P4 | **PASS** | API responses carry each security header once. |
| BUG-26 | P3 | **EXCLUDED** | Email. |
| BUG-27 | P4 | **FAIL** | Fake reset link still shows the password form. |
| BUG-28 | P4 | **BLOCKED** | Needs quote send (email) and acceptance. |
| BUG-29 | P4 | **FAIL** | Catalog "₹1234.50" ungrouped; quote form total "₹3,734" (no paise). |
| BUG-30 | P4 | **PASS** | Payment and expense 1.005 → 422. |
| BUG-31 | P4 | **EXCLUDED** | Signup OTP (email). |
| BUG-32 | P4 | **NOT VERIFIED** | No invited Admin exists to show the row. |
| BUG-33 | P4 | **PASS** | Health shows the scheduler running: Yes. |
| BUG-34 | P4 | **FAIL** | Invited member row offers only "Deactivate" (no Resend). |
| BUG-35 | P4 | **PARTIAL** | Future plain date → 422. Early-morning IST acceptance not exercised (would create a payment). |
| BUG-36 | P4 | **FAIL** | Visual editor preview iframe still `allow-scripts allow-same-origin`. |
| BUG-37 | P4 | **BLOCKED** | Needs an invitation link (email). |
| BUG-38 | P3 | **NOT VERIFIED** | Needs an expired platform session during step-up. |
| BUG-39 | P1 | **PASS** | Cross-customer allocation → 422 "belongs to a different customer". Balances unchanged. Create-with-allocation also refused. |
| BUG-40 | P1 | **PASS** | INR payment → AED invoice → 422 "is in AED; this payment is in INR". |
| BUG-41 | P1 | **PASS** | Quote PDF has no pricing JSON or markup. |
| BUG-42 | P2 | **PASS** | Upgrade picker lists "QA Plan Pro … (Upgrade)". |
| BUG-43 | P2 | **PASS** | Finalize twice → same invoice, invoice counter unchanged (16→16), linked invoice exists. |
| BUG-44 | P2 | **PASS** | `/meters/events` lists history; Usage page shows events after reload. |
| BUG-45 | P3 | **PASS** | Renew hidden until due. |
| BUG-46 | P3 | **FAIL (partial)** | Unknown field on subscription change → 422 ✓. Unknown field on customer create → 201. |
| BUG-47 | P3 | **PASS** | `javascript:` redirect and logo → 422. |
| BUG-48 | P3 | **PASS** | Unsafe custom CSS → 422. |
| BUG-49 | P3 | **PASS** | Invoice template header not on quote PDF. |
| BUG-50 | P3 | **PASS** | HTML invoice prefix → 422. |
| BUG-51 | P3 | **PASS** | `?action=new`, `?new=product`, `?new=1` open their forms. |
| BUG-52 | P3 | **PASS** | Widget visibility persists after reload (restored afterwards). |
| BUG-53 | P3 | **PASS** | 1024 px dashboard: no truncation or off-screen elements (screenshot). |
| BUG-55 | P4 | **NOT VERIFIED** | Needs a fresh cancellation. SUB-000001 (accidentally cancelled 9 Oct) left untouched. |
| BUG-56 | P4 | **PARTIAL** | `auto_renew_enabled_count` = 1 ✓. Trial-end-on-convert not re-run. |
| BUG-57 | P4 | **PASS** | One preview request per click. |
| BUG-58 | P4 | **PASS** | Checkout session form lists no draft invoices. |
| BUG-59 | P4 | **PASS** | Empty rule name → 422; `http://` webhook → 422. |
| BUG-60 | P4 | **PASS** | Checkout session URL is absolute https. |

**Totals: PASS 37 · PARTIAL 3 · FAIL 10 · NOT VERIFIED 4 · BLOCKED 2 · EXCLUDED 3 = 59**

Failing bugs by severity:

| Severity | Count | Bugs |
|---|---|---|
| P1 | 0 | — |
| P2 | 2 | BUG-10, BUG-11 |
| P3 | 4 | BUG-21, 23, 24, 46 |
| P4 | 4 | BUG-27, 29, 34, 36 |

The release notes for #38 attribute fixes to BUG-10, 11, 23, 24, 27, 29, 34, 36 and 46. Production shows they did not take effect, or only partly. The streams that produced them were cut off before completion.

## 4. Previously blocked checks (9)

| Check | Status now |
|---|---|
| Trial expiry → subscription-only screen | **PASS**. Org B (expired 12 Oct 02:10 UTC): status `trial_expired`, data APIs 403 `ORGANIZATION_TRIAL_EXPIRED`, allow-list endpoints 200, every page shows "Your free trial has ended…". |
| Report CSV exports | **PASS** (continuation C-G2; re-verified with currency column) |
| Viewer role | BLOCKED (email) |
| Operations / Support | BLOCKED (no accounts) |
| Online checkout, webhooks, refunds, receipts | EXCLUDED (payments) |
| Dunning / renewal automation | EXCLUDED (payment collection) |
| Subscription decision emails | EXCLUDED (email) |
| C-A8 successful renewal | BLOCKED (due 9 Nov) |
| C-D5 rule firing in an entitled org | NOT VERIFIED (not exercised; would execute actions) |

## 5. Production changes made during this audit (all in QA orgs, synthetic)

| Change | Detail |
|---|---|
| Org A temporary plan change, **approved by owner** | +Expenses, Reports, Automation, Reconciliation; seats 4 unchanged → tested → **restored**. Before/after identical (`planA_before.json`, `planA_after.json`). 4 platform + tenant audit entries with reason "QA audit" and ticket "QA-AUDIT-2026-10-12". |
| Org A synthetic records | Customers "Müller GmbH QA", Arabic name, "José Ñúñez QA", "QA-Co_1 / Unit #2", "QA dup email check", "QA extra field"; invoice INV-000015 (draft); advance payments PAY-000005 (₹10) and PAY-000006 (₹1); checkout session (1 h); USD expense "QA v10 USD expense" ($25.50, now hidden with the module) |
| Org B | Subscription request submitted and withdrawn (BUG-16 evidence) |
| Not changed | No real customer data, no email or payment actions, no configuration, no deletions. SUB-000001 left as is. |

## 6. Console, network and security

- No JavaScript errors on the pages exercised.
- 403 and 422 responses were the expected denials.
- Security headers single and strict.
- Tenant isolation, portal isolation, platform/tenant token separation and CSRF unchanged (earlier audit plus spot checks).

## 7. Release recommendation

**CONDITIONALLY READY — suitable for a limited, supervised pilot (excluding email and payment processing). Not "READY FOR USERS".**

Criteria not yet met:
1. **Two P2 defects still reproduce:** BUG-10 (USD prices shown with ₹ in the catalog) and BUG-11 (expense totals mix currencies). Both mislead users about money.
2. **3 of 8 roles untested** (Viewer, Operations, Support).
3. **Further gaps:** 8 P3/P4 defects still fail; 9 bugs are partial, not verified or blocked.
4. **BUG-21** (token storage) awaits a product-owner decision.

**Shortest path to READY:**
1. Fix BUG-10 and BUG-11.
2. Create Viewer, Operations and Support test accounts and verify them.
3. Fix or formally accept the remaining P3/P4 items.
4. Decide BUG-21.
5. Re-run this verification for the changed areas.


## 8. Follow-up investigation (2026-10-12)

**Org A billing automation shows "Resume billing automation": expected behaviour, not a defect.**
- The audit's approved suspend/reactivate test on 2026-10-09 caused it. Network evidence: `POST …/suspend` returned `jobs_paused: false`; `POST …/reactivate` at 10:58:11 returned `jobs_paused: true`.
- This is by design (`platform_org_service.py`, reactivate): *"Keep billing automation paused: nothing that fell due while suspended is replayed until a Platform Administrator resumes it."*
- No change was made. Resuming it is a production action (Super Admin → organization → Resume billing automation, password-confirmed and audited) and needs the owner's approval.
- UX suggestion: the Reactivate dialog could state that billing automation stays paused until resumed.

**BUG-10 / BUG-11:** fixed on branch `fix/p2-currency-display`. Not deployed.

**BUG-21:** risk assessment in `bug-21-token-storage-risk.md`.

**Viewer / Operations / Support accounts:** procedure in `test-accounts-process.md`.
