# Release decision report: 2026-10-12

| | |
|---|---|
| Production release | `6dbf7d1`. Nothing below is deployed. |
| Method | Review and read-only investigation only. No production data, settings, accounts or automation were changed. |

Labels used below: **[V]** verified fact (evidence given) · **[A]** assumption · **[R]** recommendation

## 1. PR #39: BUG-10 and BUG-11 (currency display)

| Item | Finding |
|---|---|
| Diff | 8 frontend files. **[V]** Correct and minimal. Catalog list, offering picker and price-book picker use `formatMoney(base_price, currency)`. Expense and recurring-expense summaries keep one amount per currency and render with the existing `formatPerCurrency`. No currency conversion anywhere. |
| Security | **[V]** Display-only change; no new inputs, endpoints or rendering of HTML. |
| CI | **[V]** All 4 checks pass on head `78af0a0`. CI log: frontend **884 passed (91 files)**, tsc OK, vite build OK; backend **2,020 passed, 34 skipped**; Docker build; gitleaks. Matches the locally reported results. |
| Regression tests | **[V]** 2 new cases (catalog list INR/USD/AED; mixed-currency expense summary). Both fail on `6dbf7d1` and pass with the fix. |
| Test gaps | **[V]** No tests for the offering picker, the price-book picker, or the recurring-expense summary per currency. |
| Design limits | **[V]** "INR first" ordering and a "₹0.00" empty state are hard-coded. An organization whose base currency is not INR would see INR ordering. Minor. |
| Reviews / protection | **[V]** No reviews. GitHub reports no branch protection on `main`, so approval is not enforced by GitHub. |
| **Readiness** | **[R] Ready for approval as scoped** (BUG-10 catalog list and pickers, BUG-11 expenses). It does **not** close the wider currency-display problem (NEW-01). |

### NEW-01 (P2, new, verified on production read-only)

Invoice and quote detail pages show **₹ for non-INR documents**.
- **[V]** AED invoice INV-000002 shows rate "₹367.25", IGST "₹66.11", total and balance "₹433.36".
- **[V]** Code: hard-coded "₹" in `InvoiceDetailPage.tsx` (17 places), `QuoteDetailPage.tsx` (9), `QuoteFormPage.tsx` (8), `CPQPage.tsx` (13; includes catalog base prices in offering cards), `QuotesListPage.tsx`, `ReceiptModal.tsx`, `ImportExpenseModal.tsx`, `PlansPricingPage.tsx` (KPI).
- Public pages use the document currency correctly.
- **[R]** Separate PR: replace these with `formatMoney(…, document.currency)`, plus tests on an AED invoice, a USD quote and CPQ offering cards.

## 2. PR #40: audit documentation

| Item | Finding |
|---|---|
| Scope | 4 files under `docs/qa/` |
| CI | **[V]** All 4 checks pass (head `d4a4b1b`) |
| Sensitive data | **[V]** No tokens, passwords, OTPs or secrets. Personal QA addresses and the platform-admin login replaced with placeholders. Repository is **private**. Docs describe open weaknesses (BUG-21, BUG-36, BUG-46); acceptable in a private repo. |
| Accuracy | **[V]** Release-audit statuses match the production evidence (37 PASS · 3 PARTIAL · 10 FAIL · 4 NOT VERIFIED · 2 BLOCKED · 3 EXCLUDED = 59). Email and payment paths are marked EXCLUDED, not passed. Blocked checks are listed separately. |
| Defect 1 | **[V]** `production-qa-audit-2026-10-09.md` section 2 still shows **P3 21 / P4 19**. Correct is **P3 22 / P4 18** (BUG-26 is P3); `release-audit-6dbf7d1.md` already uses 22/18. |
| Defect 2 | **[V]** References to screenshots and logs (`evidence/...`) point to files that are not in the repository. |
| Missing | NEW-01 (above) is not in #40. |
| **Readiness** | **[R] Approve after a one-line correction** of the P3/P4 counts and a note that evidence files are retained outside the repo. |

## 3. Org A paused billing automation (read-only investigation)

**[V] Cause:** the approved suspend/reactivate test on 2026-10-09. `reactivate` deliberately sets `jobs_paused = true` (`platform_org_service.py`: "nothing that fell due while suspended is replayed until a Platform Administrator resumes it").

**[V] State on 2026-10-12** (tenant API, GET only):

| Area | State |
|---|---|
| Subscriptions | SUB-000002 active, next billing 2026-11-09, `cancel_at_period_end` = true. SUB-000003 active, next billing 2026-11-09. SUB-000001 cancelled. |
| Open invoices | 6, none past due. Earliest due dates 2026-10-24 (INV-000004 ₹59, INV-000006 ₹3,540). |
| Payment methods | None saved for any customer, so **no charge is possible**. |
| Scheduled plan changes | None pending (the scheduled resize was cancelled). |
| Other queues | Dunning not entitled; webhook deliveries none; action center empty. |
| Modules | Automation, recurring expenses and dunning are not in Org A's plan. |

**What resuming would do** (scheduler jobs gated by `jobs_paused`, `scheduler.py`):

| When | Effect |
|---|---|
| Immediately | **[V]** No renewals, trial conversions, overdue marking or scheduled changes are due. **[A]** Outbox events queued during the pause would be delivered, but no webhook endpoints exist, so nothing external. |
| From 2026-10-25 | **[V]** INV-000004 and INV-000006 become overdue: invoices marked overdue, subscription may become past_due. **[A]** **Reminder emails to the QA customer address**, per `DUNNING_REMINDER_INTERVAL_DAYS`. |
| 2026-11-09 | **[V]** SUB-000003 renews: new invoice, usage finalised first. SUB-000002 ends (cancel at period end). **[A]** Renewal invoice email. No charge (no card). |
| Irreversible actions | Invoices and emails (QA addresses only). No payments, refunds or data deletion. |

**Safeguards:**
- Resume is Platform Administrator only, with password step-up, and recorded in the platform audit.
- Per-org guard: automation never runs for trial or suspended orgs.
- Org A has no saved cards.

**[R]** Leaving Org A paused is safe; it is a QA org. Resume only when you want to observe renewal behaviour on 9 Nov (that would cover blocked check C-A8). If you prefer no emails, keep it paused and let the QA org be cleaned up instead.

## 4. BUG-21: token storage

| Item | Finding |
|---|---|
| Storage | **[V]** Tenant: `rooman.access_token` (30 min), `rooman.refresh_token` (rotating, 30 days) in localStorage. Portal: `rooman.portal_token` (7 days, **hard-coded** in `customer_portal_service.py`). Platform: httpOnly cookies, 10-min access, not affected. |
| Exposure | **[V]** Requires XSS in the app origin or access to the device. No XSS found in either audit. CSP blocks inline and foreign scripts. Logout revokes server-side. Refresh reuse detection exists. |
| Shorten access token to 10–15 min | **[V]** Supported **without code change**: environment variable `ACCESS_TOKEN_EXPIRE_MINUTES`; the web app refreshes once on 401 (single in-flight refresh). **[A]** Effect: a refresh roughly every 10–15 minutes; no logouts expected. |
| Other lifetimes | Refresh lifetime is `REFRESH_TOKEN_EXPIRE_DAYS`. Portal 7 days needs a small code change. Platform staff unaffected. |
| Cookie fix | **[A]** ~20–26 h: backend cookie and CSRF layer, frontend client changes, about 14 updated frontend tests, new backend cookie/CSRF tests, browser QA, backend-then-frontend deploy, one forced re-login. Design in `bug-21-token-storage-risk.md`. |
| **Options** | **(A)** Fix before pilot: about 3 days. **(B)** **Accept temporarily for the pilot [R]**: set `ACCESS_TOKEN_EXPIRE_MINUTES=15` (approved environment change), keep CSP checks, fix in the first post-pilot release. |

**Decision record (to complete):**
- Decision: A / B
- Owner: `<name>`
- Mitigation applied: access-token lifetime 15 min (yes/no); CSP unchanged (verified)
- Review date: `<pilot end or 2026-11-15>`
- Acceptance criteria for closure: no tenant or portal token in web storage; httpOnly `__Host-` cookies with CSRF on writes; tests for cookie flags, CSRF refusal, refresh, logout and multi-tab; production check that storage holds no tokens
- Approved by / date:

## 5. Untested roles: account plan (nothing created)

| Role | Created by | Approved by | Least privilege (per `platform_deps.py` and design doc) | Blockers |
|---|---|---|---|---|
| Viewer (tenant) | QA Org A Owner invites from Users & Roles | Product owner (QA org change) | Read-only on every module. **[V]** Server enforces role rank. | **[V]** Org A at 4/4 seats: the never-accepted Viewer invite holds a seat (deactivate it, or raise the limit by plan change). **[V]** Two Viewer invitation emails never arrived (BUG-26); check spam, else SMTP logs. |
| Platform Operations | Server owner, via `python -m backend.app.cli.platform_staff create --role platform_operations --password-stdin` (no API by design) | Product owner **and** server owner | Organizations read; suspend/reactivate with reason; revoke sessions; scheduler read. **No** approvals, Create Admin, deletion, staff or editor publish. | No account exists |
| Platform Support | Same CLI with `--role platform_support` | Same | Read; request tenant access grants (Owner-approved, time-limited). Nothing else. | No account exists |

Rules: dedicated QA addresses only, passwords via stdin (never on the command line or in chat), deactivate after the audit.

## 6. Remaining release blockers and prioritised actions

| # | Item | Severity | Owner | Next action |
|---|---|---|---|---|
| 1 | NEW-01: ₹ on non-INR invoice/quote/CPQ screens | P2 | Engineering | New PR (scope above) |
| 2 | Approve and deploy #39 (BUG-10/11), then production retest | P2 | Product owner | Review, approve, merge, deploy (your approval) |
| 3 | BUG-21 decision | P3 | Product owner | Option A or B and complete the record |
| 4 | Viewer / Operations / Support verification | Coverage | Product + server owner | Approve accounts per section 5 |
| 5 | Remaining failing P3/P4: BUG-23, 24, 27, 29, 34, 36, 46 | P3/P4 | Engineering | Fix or formally accept each |
| 6 | Partial / not-verified items: BUG-15, 22, 32, 35, 38, 55, 56 | — | QA | Targeted checks once accounts and orgs allow |
| 7 | #40 count correction (P3 22 / P4 18) | Docs | Engineering | One-line fix, then approve |
| 8 | BUG-03 payment gateway | Excluded | Office | Approval outside this scope |
| 9 | Org A automation paused | Info | Product owner | Keep paused, or resume when testing renewals |

**[R] Release recommendation is unchanged: CONDITIONALLY READY (limited pilot, no email or online payments).** Items 1–4 should be done before wider use.
