# QA new-bugs PDF (`frompage6(newbugs)(1).pdf`): status on 2026-10-16

- **Base:** `main` at `a287d17`.
- **Branch:** `fix/qa-pdf-bugs`.
- **Method:** each item was checked against the current code before any change.

**Most items no longer reproduce on current `main`.** The QA run used a build from about
2026-09-17. For example, the mock dashboard and the catalog `window.confirm` were removed in
`d83a8b7`, and the customer validation was added in `1043f99`. For every such item this branch adds
a regression test, so it stays fixed.

**Statuses:**
- **Fixed:** a code change on this branch, with a regression test.
- **Already fixed + test:** fixed earlier; this branch adds the missing regression test.
- **Already fixed:** fixed and already covered by tests.

| # | Page and issue | Status | Fix and evidence |
|---|---|---|---|
| 1 | Customers: phone and postal code not validated | Already fixed + test | Frontend and backend rules existed. Added postal-code tests and a per-country phone length cap (`PhoneInput limitMaxLength`) |
| 2 | Customers: numeric-only display name accepted | Already fixed | `test_numeric_only_display_name_rejected`; BUG-09 letters still pass |
| 3 | Customers: website "dfsdg" accepted | Already fixed | `validateUrl` / `validate_website_url` and their tests. A bare `acme.com` is still auto-prefixed to `https://` on purpose |
| 4 | Customers: contact name accepts invalid values | **Fixed** | New person-name rule for contacts only (`validate_person_name` / `validatePersonName`). Digits and symbols are rejected; any script's letters pass |
| 5 | Customers: contact phone length | Fixed (UI) | `limitMaxLength`. Backend validation is still 7–15 digits only, not per country (see Remaining) |
| 6 | Dashboard shows mock data for a new org | **Fixed** (remaining part) | The mock data was gone. The all-zero 12-month trend now shows the empty state, and the draft slice is labelled "Draft", not "Cancelled" |
| 7 | Catalog: Archive uses a native confirm | Already fixed | `ConfirmDialog`. No `window.confirm` or `alert` is left in `frontend/src` |
| 8 | Catalog: editing an offering with brackets → "unexpected error" | Already fixed + test | Cause was Decimal values in the JSON column (fixed in `d83a8b7`). New API tests for volume and graduated brackets |
| 9 | Catalog: Price Book search does not filter | **Fixed** (remaining part) | The backend filter existed. A slower earlier-prefix reply could overwrite the results; now only the newest request is applied. Frontend test fails without the fix; backend search test added |
| 10 | Quotes: issue date in the past | Already fixed | `min` attribute, `validateDateNotPast` and backend `create_quote`. Also fixed `validateDateNotPast` for browsers west of UTC |
| 11 | Quotes: expiry on or before the issue date | Already fixed | `test_quote_date_merge_validation.py` |
| 12 | Quotes: issue date moved past the expiry | By design | The editor moves the expiry by the validity period instead of erroring; the backend rejects a bad pair. **Product decision** if an error is wanted instead |
| 13 | Invoices: Record Payment allows a future date | Already fixed + hardening | `max={todayIso()}` and the backend `reject_future_datetime`. `validateDateNotFuture` fixed for browsers west of UTC (test fails without the fix) |
| 14 | Invoices: Qty not editable; rate and amount reset to ₹0 | **Fixed** (remaining part) | Clearing the box zeroed the line (invoice) or snapped it back to 1, so typing 5 gave 15 (quote). Qty is now a draft until a valid number is entered. Tests in both forms |
| 15 | Invoices: summary cards and tabs show 0 | Already fixed + test | `test_invoice_summary_matches_list.py` uses QA's exact mix: sent, void, partially paid |
| 16 | Plans & Pricing: absurd quantity | Already fixed (simulator) + **fixed** (CPQ) | CPQ deal lines are now capped at 1,000,000. They used to return 500; now 422 |
| 17 | CPQ: "Total Discounts (0%)" | Already fixed | The percentage is computed from `discount_amount` |
| 18 | CPQ: overlay does not cover the top | Already fixed | `!m-0` on the overlay. It is still a hand-rolled overlay, not `ModalShell` (see Remaining) |
| 19 | CPQ: Convert to Quote uses a native confirm | Already fixed | `ConfirmDialog` |
| 20 | Quotes: print includes the app shell | **Fixed** (remaining part) | The trial and platform-access banners were still printed; they are now `no-print`. Test added |
| 21 | Quotes: Edit loses expiry, discount and terms | **Fixed** | For quotes converted from CPQ: lines now carry net prices, the deal discount is kept, expiry is +30 days, default terms are added, and an unchanged save does not reprice. A line whose offering is beyond the picker's first 100 no longer shows as "Custom Item". Backend and frontend tests |
| 22 | Subscriptions: duplicate subscription to the same plan | **Fixed** (remaining paths) | The guard existed. Added a past-due slot and `Idempotency-Key` on create, which the frontend now sends |
| 23 | Trials: a trial is created as an active subscription | Already fixed | `7548d00`; `SubscriptionFormPage.test.tsx` |
| 24 | Subscriptions: Draft tab has no count | **Fixed** | Badges were hidden for a count of 0; every known count is now shown. The backend draft count is already tested |
| 25 | Recurring expenses: 3-dot menu clipped | Already fixed + test | Body-portal menu. Added `role="menu"` and ARIA attributes |
| 26 | Timesheets: end time before start time | Already fixed + test | Frontend and backend; frontend test added |
| 27 | Settings: Dark theme reverts to Light | Already fixed + test | Saved on selection; remount test added |
| 28 | Customization: logo missing in preview | Already fixed | `test_template_preview_logo.py`, `TemplateModal.test.tsx` |

## Additional fixes found during the audit

- **Payments, duplicate submissions:** the frontend never sent `Idempotency-Key`, so a 401-refresh replay or a resubmit could record a payment twice. All payment and subscription POSTs now send one.
- **Payments, stuck PENDING:** a stale Razorpay payment whose webhook was lost stayed pending forever. The new scheduler step reconciles it with Razorpay.
- **Uploads:** avatar and logo uploads are read with a size cap. A deleted expense's private receipt file is removed. The uploads restore procedure would have published the private receipts; it now restores the two volumes separately.

## Remaining (not fixed here)

| Item | Severity | Why |
|---|---|---|
| Backend phone validation is not per country | Low | Needs the `phonenumbers` dependency; the UI already validates per country |
| CPQ wizard overlay is hand-rolled (no portal, Escape key or focus trap) | Low | It works visually; moving it to `ModalShell` is a refactor |
| `refunds.gateway_refund_id` has no unique index | Low | Duplicates are prevented by a row lock on PostgreSQL; an index needs a migration and a deploy window |
| Item 12 (issue date after expiry) | Decision | Choose between error and auto-shift |
