# Demo & verification scripts

Both talk to a running API over HTTP only — they never touch the database directly.

## `seed_demo.py`
Fills an organization with realistic Indian-SME billing data (products, plans, 12
customers with GSTINs, subscriptions incl. trials/paused/cancelled, quotes,
~38 invoices spread over 8 months with full/partial/overdue payments, timesheets,
lifecycle stages, meters + usage events, dunning policies, automation rules,
document templates, number series, checkout sessions, devices).

```bash
API=http://127.0.0.1:8010 EMAIL=you@example.com PASSWORD=... python3 scripts/seed_demo.py
```
Refuses to run against an org that already has customers unless `FORCE=1`.

## `verify_all.py`
Logs in through the real login form in headless Chrome, then walks every sidebar
route (plus detail/form pages passed via `EXTRA_ROUTES`) and fails on placeholder
text, the not-found page, console errors, or any API response >= 400. Writes a
screenshot per route to `$OUT`.

```bash
OUT=/tmp/shots EXTRA_ROUTES=/invoices/<id>,/quotes/new python3 scripts/verify_all.py
```
Requires `google-chrome` and `pip install websocket-client`.
