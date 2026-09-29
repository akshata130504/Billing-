# Browser QA checklist

Automated tests cover the API and component logic; this checklist covers what only a person
in a browser can confirm. Run it on **staging** (or production with a dedicated test
organization) after every release that changes UI or billing flows. Record the build SHA,
browser, date and tester. **Browser QA is not complete until every row below has been ticked.**

For every screen: open DevTools and confirm **no console errors** and **no failed (red) network
requests**; check the loading state, the empty state and one error state; resize to a phone
width (~375 px) and confirm nothing overflows or becomes unusable.

## 1. Accounts and security
- [ ] Sign up: request code -> email arrives -> verify -> lands on dashboard
- [ ] Resend code (after the cooldown); wrong code rejected; 5 wrong codes lock the code
- [ ] Login / logout; session expiry redirects to login and returns to the original page
- [ ] Forgot password -> email link -> reset -> old sessions end
- [ ] 2FA: enable (authenticator app), login with code, disable (needs password + code)
- [ ] Settings > Security: active sessions list, sign out another session
- [ ] Invite a team member (new email and existing account); accept both ways
- [ ] Role gating: as a Viewer, create/edit/delete buttons are hidden or show "View only"

## 2. Customers and catalog
- [ ] Customers: create, edit, search, paginate, view detail, delete blocked when referenced
- [ ] CSV import: dry run shows errors per row; real import
- [ ] Catalog / Plans & Pricing: create flat, per-unit, volume, tiered and package offerings
- [ ] Overlapping or inverted tiers are rejected with a clear message
- [ ] Plan price preview matches the saved price for in-gap and above-last-tier quantities

## 3. Subscriptions and billing
- [ ] Create a subscription from a legacy plan and from a Plans & Pricing plan (both listed)
- [ ] Upgrade / downgrade with proration; the next renewal uses the new plan
- [ ] Pause, resume (first period invoiced), cancel now (optional prorated credit), cancel at period end
- [ ] Trials: convert, extend, fallback plan
- [ ] Usage: create meter with a unit price, record usage, finalize a billing cycle from the picker

## 4. Quotes and CPQ
- [ ] Quote: create, discount above threshold -> approval request; approver != requester
- [ ] Quote PDF downloads and opens; quote email sent (or clear "email not delivered" warning)
- [ ] Public quote link: view marks VIEWED, accept/decline
- [ ] Convert accepted quote -> invoice; convert accepted quote -> subscription; second click
      shows the existing record (no duplicate)
- [ ] CPQ deal: configure, approve (not by the creator), convert to quote once

## 5. Invoices, payments, credit notes
- [ ] Invoice: create, edit draft, send, PDF (GSTIN/CGST/SGST/IGST correct), void, delete latest draft
- [ ] Record a manual payment (double-click does not create two)
- [ ] Public pay link: partial and full payment in Razorpay **test mode**; invoice status updates
- [ ] Close the browser right after paying -> the invoice still becomes paid (webhook)
- [ ] Refund (full and partial) updates the payment and re-opens the invoice
- [ ] Credit notes: create (with invoice link), apply to an invoice, over-apply blocked, void;
      list shows "X of Y" and the summary tiles
- [ ] Dunning: retry now; collections: promise to pay, activity log

## 6. Operations screens
- [ ] Dashboard figures match the Invoices / Payments / Subscriptions lists (per currency, MRR, churn)
- [ ] Reports: date ranges (this month, custom), CSV export
- [ ] Projects: create with a customer, log time, add expense, create invoice (real invoice appears)
- [ ] Expenses: real customer/project pickers, receipt upload + download, add to invoice
- [ ] Timesheets: log, approve (not your own), generate invoice
- [ ] Automation: create a rule and a schedule; webhook action shows its secret once
- [ ] Customization: document template preview, number series
- [ ] Notifications: bell read/dismiss persists after refresh and in another browser;
      preferences save; SMS templates show "Not available"
- [ ] Help: "Contact support by email" opens a mail draft (or "Contact your administrator")
- [ ] Global search finds customers, invoices, projects, expenses

## 7. Customer portal
- [ ] Invite a customer, activate, login
- [ ] Sees only their own invoices (no drafts), payments, subscriptions; PDF download
- [ ] Expired session redirects to portal login with a message

## 8. Tenant isolation (two organizations, two browsers)
- [ ] Org B cannot open Org A's customer / invoice / quote / subscription URLs (404)
- [ ] Org B's search, dashboard and reports never show Org A data

## Sign-off
| Build SHA | Browser / device | Tester | Date | Result |
|---|---|---|---|---|
|  |  |  |  |  |
