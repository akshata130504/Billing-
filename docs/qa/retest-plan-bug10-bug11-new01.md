# Production retest plan: BUG-10, BUG-11, NEW-01

**Status:** plan only. Run it only after #39 and #41 are merged **and** deployed, each with separate approval. Until every step below passes on the live site, the fixes count as **not verified on production**.

## 0. Preconditions

| # | Check | How |
|---|---|---|
| P1 | The deployed build contains both PRs | Note the deployed commit from the deploy run. It must contain the #39 and #41 merge commits. Hard-refresh the app and confirm the new bundle loads (asset hashes differ from release `6dbf7d1`). |
| P2 | Accounts | QA Org A Owner (tenant). Read-only checks only, unless a step says otherwise. |
| P3 | Modules | Catalog, CPQ, Quotes, Invoices and Payments must be in Org A's plan. **BUG-11 needs Expenses**, which Org A's plan does not include. Choose one, **with approval**: (a) a temporary Org A plan change, restored afterwards as in the 2026-10-12 audit; or (b) another QA org that has Expenses. Without either, BUG-11 stays **BLOCKED**, not passed. |
| P4 | Data | Use existing QA records first. Create new synthetic records only if approved, only in QA orgs, and never send them (no emails). |
| P5 | Safety | No payments, refunds, email sends, gateway calls, plan publishes or automation resume. Org A stays paused. |

## 1. NEW-01: document and payment currency

| ID | Screen | Record | Expected | Fails if |
|---|---|---|---|---|
| N1 | Invoice detail | **INV-000002** (AED) | Rate **AED 367.25**, IGST **AED 66.11**, total and balance **AED 433.36**. Same numbers as before; only the symbol changes. | Any "₹" on the page amounts, or any number differs from the API `GET /invoices/{id}` |
| N2 | Invoice detail | An INR invoice (e.g. INV-000004) | ₹ with paise (e.g. ₹59.00) | Missing paise, or a different total |
| N3 | Invoice detail | A USD invoice, if one exists (else mark N/A) | `$` amounts | ₹ shown |
| N4 | Quotes list and quote detail | A non-INR quote, if one exists (else N/A, or an approved synthetic draft) | List total, line amounts, tax lines and total in the quote currency | ₹ on a non-INR quote |
| N5 | Quote form (new, **not saved**) | Switch currency to USD, add a line | Rate/Amount headers show `$`; GST preview and totals show `$` with 2 decimals | ₹ in headers or totals |
| N6 | CPQ → Start New Deal → Offerings step (do **not** create the deal) | Offerings in AED/USD/INR | Each card shows its own currency | All cards show ₹ |
| N7 | CPQ deals list | Existing deals | Total in each deal's currency | ₹ on a non-INR deal |
| N8 | Payments list, payment detail, receipt (view only) | An AED payment if one exists; INR PAY-000005 / PAY-000006 | Each amount in the payment's currency; receipt allocation and refund lines match | ₹ on a non-INR payment, or "(currency unknown)" on any normal record. That text would mean the API returned no currency and must be investigated. |
| N9 | Record Payment dialog (open, then **Cancel**) | Select an AED customer | Label "Amount Received (AED)", prefix "AED"; outstanding invoice rows in their own currency | ₹ prefix for an AED customer |
| N10 | Refund dialog (open, then **Cancel**) | Any payment | Prefix and limits in the payment currency | ₹ on a non-INR payment |
| N11 | Plans & Pricing KPI | — | Average price shown per currency ("₹… · AED …") | One summed figure |

## 2. BUG-10: catalog prices

| ID | Screen | Expected | Fails if |
|---|---|---|---|
| C1 | Catalog list, pricing column | Each offering in its own currency (an AED offering shows AED) | ₹ on a non-INR offering |
| C2 | Offering modal → type Bundle → Add Component (then **Cancel**) | Component options show each offering's currency | ₹ for every option |
| C3 | Price book modal → Add entry (then **Cancel**) | "Base: …" in each offering's currency; "Fixed" label uses the price book currency | ₹ for every option |

## 3. BUG-11: expense totals (needs P3)

| ID | Screen | Expected | Fails if |
|---|---|---|---|
| E1 | Expenses summary cards | One figure per currency, e.g. "₹2,360.80 · $25.50 · AED 1,180.40". Compare each figure with a hand sum of the list, per currency. | A single ₹ figure combining currencies (the pre-fix value was "₹3,566.70") |
| E2 | Recurring expenses summary | Monthly and billable recurring per currency | Summed figure |
| E3 | Org with only INR expenses | Single ₹ figure, unchanged from before | Changed amount |

## 4. Recording results

For each ID record: PASS / FAIL / N/A / BLOCKED, the record number, and a screenshot kept in the private audit archive (not the repository). Redact customer emails. A FAIL on N1, C1 or E1 blocks closing the bug.

## 5. Rollback trigger

Any wrong **amount** (as opposed to a wrong symbol), or a page that fails to load: report it immediately and propose a rollback to the previous release. The rollback itself needs approval.
