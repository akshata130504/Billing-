"""Seed a Rooman Billing organization with realistic demo data through the public
API only (no direct DB writes), so every page has something real to show.

Usage:
  API=http://127.0.0.1:8010 EMAIL=... PASSWORD=... python seed_demo.py
Re-running is safe: if the org already has customers it exits unless FORCE=1.
"""
import os, sys, uuid, random, json
from datetime import date, datetime, timedelta, timezone
import urllib.request, urllib.error

API = os.environ.get("API", "http://127.0.0.1:8010").rstrip("/") + "/api/v1"
EMAIL = os.environ.get("EMAIL", "khadar.demo@example.com")
PASSWORD = os.environ.get("PASSWORD", "DemoPassw0rd!2026")
FORCE = os.environ.get("FORCE") == "1"
random.seed(42)
TOKEN = None
warnings = []


def call(method, path, body=None, ok=(200, 201, 204), quiet=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={"Content-Type": "application/json"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:300]
        if not quiet:
            warnings.append(f"{method} {path} -> {e.code}: {msg}")
        return None


def login():
    global TOKEN
    r = call("POST", "/auth/login", {"email": EMAIL, "password": PASSWORD}, quiet=True)
    if not r:
        sys.exit(f"login failed for {EMAIL}")
    TOKEN = r["access_token"]


def d(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def dt(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago, hours=random.randint(1, 9))).isoformat()


login()
me = call("GET", "/auth/me")
print(f"Seeding org: {me['organization']['name']} as {me['user']['email']}")
existing = call("GET", "/customers?page_size=1")
if existing and existing.get("total", 0) > 0 and not FORCE:
    sys.exit(f"Org already has {existing['total']} customers; set FORCE=1 to seed anyway.")

# ---------------------------------------------------------------- catalog
products_spec = [
    ("Cloud Hosting", "service", "998315", 18, "Managed cloud hosting and monitoring"),
    ("Payroll SaaS", "subscription", "998313", 18, "Payroll & compliance software"),
    ("GST Filing Service", "service", "998231", 18, "Monthly GST return preparation and filing"),
    ("Implementation Consulting", "service", "998314", 18, "Onboarding and implementation hours"),
    ("Support Plan", "subscription", "998316", 18, "Priority support with SLA"),
    ("Data Backup Storage", "service", "998315", 18, "Encrypted off-site backup, billed per GB"),
    ("POS Terminal", "goods", "84705010", 18, "Android POS terminal with printer"),
    ("Training Workshop", "service", "999293", 18, "On-site staff training"),
]
products = {}
for name, ptype, hsn, tax, desc in products_spec:
    p = call("POST", "/products", {"name": name, "type": ptype, "hsn_sac_code": hsn, "tax_rate_pct": tax, "description": desc,
                                   "sku": name.upper().replace(" ", "-")[:20], "unit": "unit"})
    if p:
        products[name] = p
print(f"  products: {len(products)}")

plans_spec = [
    ("Cloud Hosting", "Hosting Starter", "HOST-STARTER", "monthly", "flat", "4999", 0, 0),
    ("Cloud Hosting", "Hosting Business", "HOST-BIZ", "monthly", "flat", "14999", 0, 0),
    ("Cloud Hosting", "Hosting Business Annual", "HOST-BIZ-Y", "yearly", "flat", "149990", 0, 0),
    ("Payroll SaaS", "Payroll per Employee", "PAY-EMP", "monthly", "per_unit", "149", 0, 14),
    ("Payroll SaaS", "Payroll Enterprise", "PAY-ENT", "yearly", "flat", "240000", 25000, 0),
    ("Support Plan", "Support Silver", "SUP-SILVER", "monthly", "flat", "7500", 0, 0),
    ("Support Plan", "Support Gold", "SUP-GOLD", "quarterly", "flat", "45000", 0, 0),
    ("Data Backup Storage", "Backup per 100GB", "BKP-100", "monthly", "per_unit", "899", 0, 7),
    ("GST Filing Service", "GST Filing Monthly", "GST-M", "monthly", "flat", "2500", 0, 0),
]
plans = {}
for prod, name, code, interval, model, amt, setup, trial in plans_spec:
    if prod not in products:
        continue
    pl = call("POST", "/plans", {"product_id": products[prod]["id"], "name": name, "code": code, "billing_interval": interval,
                                 "pricing_model": model, "unit_amount": amt, "setup_fee": str(setup), "trial_days": trial, "currency": "INR"})
    if pl:
        plans[code] = pl
print(f"  plans: {len(plans)}")

# ---------------------------------------------------------------- customers
customers_spec = [
    ("Bharat Textiles Pvt Ltd", "Bharat Textiles Pvt Ltd", "accounts@bharattextiles.in", "27AABCB1234F1Z5", "Mumbai", "Maharashtra", 30, "Ravi Shah"),
    ("Nandini Dairy Co-op", "Nandini Dairy Cooperative Society", "finance@nandinidairy.coop", "29AAACN5678K1Z2", "Bengaluru", "Karnataka", 15, "Lakshmi Gowda"),
    ("Sunrise Hospitals", "Sunrise Hospitals Limited", "billing@sunrisehospitals.com", "36AABCS9012L1Z8", "Hyderabad", "Telangana", 45, "Dr. Arjun Reddy"),
    ("Kaveri Agro Exports", "Kaveri Agro Exports LLP", "ap@kaveriagro.com", "33AAFCK3456M1Z1", "Coimbatore", "Tamil Nadu", 30, "Meena Iyer"),
    ("Zenith EdTech", "Zenith EdTech Private Limited", "ops@zenithedtech.io", "07AABCZ7890N1Z4", "New Delhi", "Delhi", 15, "Priya Malhotra"),
    ("Rajputana Logistics", "Rajputana Logistics Pvt Ltd", "accounts@rajputanalogistics.in", "08AABCR2345P1Z9", "Jaipur", "Rajasthan", 30, "Vikram Singh"),
    ("Coastal Seafoods", "Coastal Seafoods Exports", "finance@coastalseafoods.in", "32AABCC6789Q1Z3", "Kochi", "Kerala", 30, "Thomas Varghese"),
    ("Metro Retail Chain", "Metro Retail Chain Pvt Ltd", "payables@metroretail.in", "24AABCM1122R1Z7", "Ahmedabad", "Gujarat", 45, "Nilesh Patel"),
    ("Himalaya Pharma", "Himalaya Pharmaceuticals Ltd", "ap@himalayapharma.com", "02AABCH3344S1Z6", "Baddi", "Himachal Pradesh", 60, "Sunita Verma"),
    ("Ganga Steel Works", "Ganga Steel Works Pvt Ltd", "accounts@gangasteel.in", "09AABCG5566T1Z2", "Kanpur", "Uttar Pradesh", 30, "Anil Gupta"),
    ("Deccan Realty", "Deccan Realty Developers", "finance@deccanrealty.in", "36AABCD7788U1Z5", "Hyderabad", "Telangana", 15, "Kiran Rao"),
    ("BlueWave Studios", "BlueWave Studios LLP", "hello@bluewave.studio", "29AAFCB9900V1Z8", "Bengaluru", "Karnataka", 15, "Ananya Krishnan"),
]
customers = []
for disp, legal, email, gstin, city, state, terms, contact in customers_spec:
    c = call("POST", "/customers", {
        "display_name": disp, "company_name": legal, "email": email, "phone": f"+91 98{random.randint(10000000, 99999999)}",
        "gstin": gstin, "pan": gstin[2:12], "currency": "INR", "payment_terms_days": terms,
        "billing_address_line1": f"{random.randint(1, 200)}, {random.choice(['MG Road', 'Industrial Area Phase II', 'Ring Road', 'IT Park'])}",
        "billing_city": city, "billing_state": state, "billing_postal_code": str(random.randint(110001, 695001)), "billing_country": "IN",
        "contacts": [{"name": contact, "email": email, "designation": "Finance Head", "is_primary": True},
                     {"name": "Accounts Desk", "email": "accounts." + email, "designation": "AP Team", "is_primary": False}],
    })
    if c:
        customers.append(c)
print(f"  customers: {len(customers)}")
if not customers:
    sys.exit("no customers created; aborting")

# ---------------------------------------------------------------- subscriptions
subs = []
sub_spec = [
    (0, "HOST-BIZ", 1), (1, "PAY-EMP", 85), (2, "SUP-GOLD", 1), (3, "GST-M", 1), (4, "PAY-EMP", 40),
    (5, "HOST-STARTER", 1), (6, "BKP-100", 12), (7, "HOST-BIZ-Y", 1), (8, "SUP-SILVER", 1), (9, "GST-M", 1),
]
for ci, code, qty in sub_spec:
    if code not in plans or ci >= len(customers):
        continue
    s = call("POST", "/subscriptions", {"customer_id": customers[ci]["id"], "plan_id": plans[code]["id"], "quantity": qty,
                                        "start_date": d(random.randint(20, 160)), "trial_days": 0, "auto_renewal": True, "generate_first_invoice": True})
    if s:
        subs.append(s)
# trialing + paused + cancelled examples
if "PAY-EMP" in plans and len(customers) > 10:
    t = call("POST", "/subscriptions", {"customer_id": customers[10]["id"], "plan_id": plans["PAY-EMP"]["id"], "quantity": 25, "trial_days": 14, "generate_first_invoice": False})
    if t:
        subs.append(t)
if "BKP-100" in plans and len(customers) > 11:
    t = call("POST", "/subscriptions", {"customer_id": customers[11]["id"], "plan_id": plans["BKP-100"]["id"], "quantity": 5, "trial_days": 7, "generate_first_invoice": False})
    if t:
        subs.append(t)
if len(subs) > 5:
    call("POST", f"/subscriptions/{subs[5]['id']}/pause", {"reason": "Customer requested seasonal pause"}, quiet=True) or call("POST", f"/subscriptions/{subs[5]['id']}/pause", quiet=True)
if len(subs) > 8:
    call("POST", f"/subscriptions/{subs[8]['id']}/cancel", {"at_period_end": True, "reason": "Switching to Gold plan next quarter"}, quiet=True) or \
        call("POST", f"/subscriptions/{subs[8]['id']}/cancel", {"reason": "Switching plan"}, quiet=True)
print(f"  subscriptions: {len(subs)}")

# ---------------------------------------------------------------- quotes
quotes = []
quote_items = [
    ("Implementation Consulting", "Implementation & onboarding (hours)", 40, "3500"),
    ("Training Workshop", "On-site training workshop (2 days)", 2, "45000"),
    ("POS Terminal", "Android POS terminal", 6, "18500"),
    ("Cloud Hosting", "Hosting migration one-time", 1, "60000"),
]
for i in range(6):
    cust = customers[(i * 2 + 1) % len(customers)]
    picks = random.sample(quote_items, k=2)
    items = [{"product_id": products[p]["id"], "description": desc, "quantity": q, "unit_price": up, "tax_rate_pct": 18} for p, desc, q, up in picks if p in products]
    q = call("POST", "/quotes", {"customer_id": cust["id"], "title": f"Proposal — {picks[0][1].split(' (')[0]}", "issue_date": d(random.randint(2, 40)),
                                 "expiry_date": d(-random.randint(10, 30)), "discount_pct": random.choice(["0", "0", "5"]), "items": items,
                                 "notes": "Prices exclusive of GST. Delivery within 15 working days of PO.", "terms": "50% advance, balance on delivery."})
    if q:
        quotes.append(q)
for i, q in enumerate(quotes):
    if i in (1, 2, 3, 4):
        call("POST", f"/quotes/{q['id']}/send", quiet=True)
    if i in (2, 3):
        call("POST", f"/quotes/{q['id']}/mark-accepted", quiet=True)
    if i == 3:
        call("POST", f"/quotes/{q['id']}/convert-to-invoice", quiet=True) or call("POST", f"/quotes/{q['id']}/convert", quiet=True)
    if i == 4:
        call("POST", f"/quotes/{q['id']}/mark-declined", quiet=True)
print(f"  quotes: {len(quotes)}")

# ---------------------------------------------------------------- invoices spread over 8 months, with payments
invoice_items = [
    ("Implementation Consulting", "Implementation consulting", (8, 24), "3500"),
    ("GST Filing Service", "GST return filing — monthly", (1, 1), "2500"),
    ("Training Workshop", "Staff training workshop", (1, 2), "45000"),
    ("Data Backup Storage", "Backup storage (100 GB blocks)", (3, 20), "899"),
    ("POS Terminal", "POS terminal units", (2, 10), "18500"),
    ("Cloud Hosting", "Managed hosting — additional environment", (1, 3), "4999"),
]
invoices = []
for n in range(38):
    cust = customers[n % len(customers)]
    age = random.randint(0, 240)
    picks = random.sample(invoice_items, k=random.choice([1, 2, 2, 3]))
    items = []
    for p, desc, (lo, hi), up in picks:
        if p in products:
            items.append({"product_id": products[p]["id"], "description": desc, "quantity": random.randint(lo, hi), "unit_price": up, "tax_rate_pct": 18})
    inv = call("POST", "/invoices", {"customer_id": cust["id"], "issue_date": d(age), "due_date": d(age - cust.get("payment_terms_days", 30) or 30),
                                     "items": items, "notes": "Thank you for your business."})
    if not inv:
        continue
    invoices.append(inv)
    if age < 3 and n % 5 == 0:
        continue  # leave a few drafts
    call("POST", f"/invoices/{inv['id']}/send", quiet=True)
    inv = call("GET", f"/invoices/{inv['id']}") or inv
    total = float(inv.get("total") or 0)
    roll = random.random()
    if age > 60 or (age > 20 and roll < 0.7):
        # paid in full
        paid_after = random.randint(2, min(max(age, 3), 40))
        call("POST", f"/invoices/{inv['id']}/record-payment", {"amount": f"{total:.2f}", "method": random.choice(["bank_transfer", "upi", "razorpay", "cheque"]),
                                                              "paid_at": dt(max(age - paid_after, 0)), "reference": f"UTR{random.randint(10**11, 10**12 - 1)}"})
    elif age > 10 and roll < 0.85:
        # partially paid
        call("POST", f"/invoices/{inv['id']}/record-payment", {"amount": f"{total * random.choice([0.3, 0.5]):.2f}", "method": "bank_transfer",
                                                              "paid_at": dt(max(age - 5, 0)), "reference": f"NEFT{random.randint(10**8, 10**9 - 1)}", "notes": "Part payment against PO"})
    # else: left unpaid -> overdue if due date passed
print(f"  invoices: {len(invoices)}")
if invoices:
    call("POST", f"/invoices/{invoices[-1]['id']}/void", {"reason": "Duplicate of another invoice"}, quiet=True)

# ---------------------------------------------------------------- timesheets
entries = []
for i in range(14):
    cust = customers[i % 4]
    e = call("POST", "/timesheets", {"customer_id": cust["id"], "project_name": random.choice(["ERP Rollout", "GST Automation", "Cloud Migration", "POS Deployment"]),
                                     "date": d(random.randint(0, 25)), "duration_hours": random.choice([2, 3.5, 4, 6, 8]),
                                     "description": random.choice(["Requirement workshop", "Data migration scripting", "UAT support", "Integration testing", "Go-live support", "Training delivery"]),
                                     "billable": i % 5 != 0, "billing_rate": "3500"})
    if e:
        entries.append(e)
for i, e in enumerate(entries):
    if i % 3 != 0:
        call("POST", f"/timesheets/{e['id']}/submit", quiet=True)
    if i % 3 == 1:
        call("POST", f"/timesheets/{e['id']}/approve", quiet=True)
approved = [e for i, e in enumerate(entries) if i % 3 == 1 and e.get("billable")]
by_cust = {}
for e in approved:
    by_cust.setdefault(e["customer_id"], []).append(e["id"])
for cid, ids in list(by_cust.items())[:1]:
    call("POST", "/timesheets/generate-invoice", {"customer_id": cid, "time_entry_ids": ids, "notes": "Consulting hours — approved timesheets"})
print(f"  time entries: {len(entries)}")

# ---------------------------------------------------------------- lifecycle
stages = [("active", "healthy", 92), ("expansion", "healthy", 88), ("renewal_due", "neutral", 70), ("at_risk", "at_risk", 48), ("onboarding", "healthy", 80), ("at_risk", "critical", 30)]
for i, (stage, health, score) in enumerate(stages):
    if i < len(customers):
        call("PATCH", f"/lifecycle/{customers[i]['id']}", {"lifecycle_stage": stage, "health_status": health, "health_score": score,
                                                          "next_action": random.choice(["QBR call", "Renewal proposal", "Escalate overdue invoices", "Upsell Gold support"]),
                                                          "next_action_due": d(-random.randint(3, 20))}, quiet=True)

# ---------------------------------------------------------------- metering
for code, name, unit, agg in [("api_calls", "API Calls", "call", "sum"), ("storage_gb", "Storage Used", "GB", "max"), ("sms_sent", "SMS Sent", "message", "sum")]:
    call("POST", "/meters", {"code": code, "name": name, "unit_name": unit, "aggregation_type": agg, "description": f"Tracks {name.lower()} per customer"}, quiet=True)
for i in range(30):
    cust = customers[i % 6]
    call("POST", "/meters/events", {"meter_code": random.choice(["api_calls", "storage_gb", "sms_sent"]), "customer_id": cust["id"],
                                    "quantity": str(random.randint(50, 5000)), "idempotency_key": str(uuid.uuid4()), "timestamp": dt(random.randint(0, 28))}, quiet=True)

# ---------------------------------------------------------------- dunning, automation, customization, checkout, devices
call("POST", "/dunning/policies", {"name": "Standard Retry Policy", "description": "3 retries over 2 weeks, then suspend", "is_default": True,
                                   "max_retries": 3, "retry_intervals_days": [3, 5, 7], "total_span_days": 15, "final_action": "suspend"}, quiet=True)
call("POST", "/dunning/policies", {"name": "Enterprise Grace Policy", "description": "Longer grace for enterprise accounts", "max_retries": 3,
                                   "retry_intervals_days": [7, 10, 10], "total_span_days": 28, "final_action": "unpaid", "non_autocharge_grace_days": 30}, quiet=True)
# NB: an action needs `name` + `action_type` (email_alert|webhook|field_update)
# + `configuration` — not the {type, params} shape you might expect.
call("POST", "/automation/rules", {"name": "Alert finance on failed payment", "description": "Email the finance desk when an auto-charge fails above Rs 10,000.",
                                   "module": "payments", "trigger_event": "payment_failed", "conditions": {"amount_gte": 10000},
                                   "actions": [{"name": "Email finance desk", "action_type": "email_alert", "configuration": {"to": "finance@roomandemo.in"}, "execution_order": 1}]}, quiet=True)
call("POST", "/automation/rules", {"name": "Escalate invoices overdue 7+ days", "description": "Notify collections and push to CRM once an invoice is a week overdue.",
                                   "module": "invoices", "trigger_event": "invoice_overdue", "conditions": {"days_overdue_gte": 7},
                                   "actions": [{"name": "Email collections", "action_type": "email_alert", "configuration": {"to": "collections@roomandemo.in"}, "execution_order": 1},
                                               {"name": "Notify CRM", "action_type": "webhook", "configuration": {"url": "https://crm.roomandemo.in/hooks/overdue"}, "execution_order": 2}]}, quiet=True)
for mod, nm, prefix, start, pad in [("invoice", "Invoice Series FY26-27", "INV/26-27/", 1, 5), ("quote", "Quotation Series", "QT/", 100, 4), ("credit_note", "Credit Note Series", "CN/26-27/", 1, 4)]:
    call("POST", "/settings/number-series", {"module": mod, "name": nm, "prefix": prefix, "starting_number": start, "padding": pad, "is_default": True}, quiet=True)
call("POST", "/automation/schedules", {"name": "Daily overdue sweep", "frequency": "daily", "target_action": "mark_overdue_invoices"}, quiet=True)
call("POST", "/automation/schedules", {"name": "Weekly statement emails", "frequency": "weekly", "target_action": "send_customer_statements"}, quiet=True)
for name, code in [("Enterprise", "ENT"), ("SMB", "SMB"), ("Government", "GOV"), ("Export", "EXP")]:
    call("POST", "/reporting-tags", {"name": name, "code": code, "description": f"{name} segment"}, quiet=True)
call("POST", "/templates", {"name": "Rooman Standard Invoice", "document_type": "invoice", "layout_type": "modern", "is_default": True,
                            "header_text": "Tax Invoice", "footer_text": "This is a computer generated invoice.", "terms_and_conditions": "Payment due as per agreed terms. Interest @18% p.a. on delayed payments."}, quiet=True)
call("POST", "/templates", {"name": "Quotation — Classic", "document_type": "quote", "layout_type": "standard", "is_default": True, "header_text": "Quotation"}, quiet=True)
call("POST", "/checkout/templates", {"name": "Default Pay Page", "is_default": True, "button_text": "Pay Securely", "thank_you_message": "Thank you! Your payment has been received."}, quiet=True)
open_inv = [i for i in invoices[:12]]
for inv in open_inv[:3]:
    # InvoiceOut nests the customer as a ref object rather than a flat customer_id.
    cust_id = inv.get("customer_id") or (inv.get("customer") or {}).get("id")
    call("POST", "/checkout/sessions", {"purpose": "invoice_payment", "customer_id": cust_id, "invoice_id": inv["id"], "expires_in_hours": 72}, quiet=True)
for ident, plat, name, osv in [("IMEI-8611-2201", "android", "Sales Team Pixel 8", "Android 15"), ("UDID-9F3A-11", "ios", "Finance iPad Pro", "iOS 18.2"),
                               ("WIN-ACC-01", "windows", "Accounts Desktop 01", "Windows 11 24H2"), ("MAC-CEO-01", "macos", "CEO MacBook Pro", "macOS 15.3")]:
    call("POST", "/devices", {"device_identifier": ident, "platform": plat, "device_name": name, "os_version": osv, "app_version": "1.4.2"}, quiet=True)
call("POST", "/web-tabs", {"tab_name": "GST Portal", "url": "https://www.gst.gov.in", "allowed_roles": ["owner", "admin", "finance"]}, quiet=True)
call("POST", "/ai/queries", {"prompt": "Which customers have overdue invoices above 50,000?"}, quiet=True)

print("\nDone.")
if warnings:
    print(f"{len(warnings)} non-fatal warnings:")
    for w in warnings[:25]:
        print("  -", w)
