"""Regression tests: money is never summed across currencies (BUG-01, BUG-02, BUG-11, BUG-12, BUG-14).

The app has no exchange-rate feature, so every monetary aggregate must be reported per
currency. One organization (base currency INR) gets INR, AED and USD invoices, payments
and an INR credit note - the QA scenario (INR 7,210.71 + AED 433.36 was shown as
"₹7,644.07") - and every affected endpoint is checked against independently computed
per-currency sums.
"""
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import pytest

from backend.app.core.security import hash_password
from backend.app.core.tenant_context import tenant_context
from backend.app.models import (
    CreditApplication,
    CreditNote,
    CreditNoteStatus,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentAllocation,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    ReconciliationStatus,
)
from backend.app.models.portal import CustomerPortalUser
from backend.app.services import timezones


def _q(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rate(collected: str, invoiced: str) -> str:
    return str(_q(Decimal(collected) / Decimal(invoiced) * 100))


@pytest.fixture
def mixed(db, tenant):
    """INR, AED and USD activity in one INR-based organization, all dated today."""
    org = tenant.organization
    assert (org.default_currency or "INR") == "INR"
    today = timezones.org_today(org)
    now = datetime.now(timezone.utc)
    c_inr = tenant.customer(currency="INR")
    c_usd = tenant.customer(currency="USD")

    def invoice(customer, currency, total, paid, status, due_in_days=30, paid_at=None):
        inv = Invoice(
            organization_id=org.id,
            invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
            customer_id=customer.id,
            status=status,
            issue_date=today,
            due_date=today + timedelta(days=due_in_days),
            currency=currency,
            subtotal=Decimal(total),
            total=Decimal(total),
            amount_paid=Decimal(paid),
            amount_due=Decimal(total) - Decimal(paid),
            public_token=uuid.uuid4().hex,
            sent_at=now,
            paid_at=paid_at,
        )
        db.add(inv)
        db.flush()
        return inv

    def payment(customer, currency, amount, inv):
        p = Payment(
            organization_id=org.id,
            payment_number=f"PAY-{uuid.uuid4().hex[:8]}",
            customer_id=customer.id,
            amount=Decimal(amount),
            currency=currency,
            method=PaymentMethod.BANK_TRANSFER,
            gateway=PaymentGateway.MANUAL,
            status=PaymentStatus.SUCCEEDED,
            reconciliation_status=ReconciliationStatus.MATCHED,
            paid_at=now,
            amount_refunded=Decimal("0"),
        )
        db.add(p)
        db.flush()
        db.add(PaymentAllocation(organization_id=org.id, payment_id=p.id, invoice_id=inv.id, amount=Decimal(amount)))
        return p

    with tenant_context(org.id):
        # INR: 7,210.71 paid 2,111.51 in cash + 590.00 by credit note -> 4,509.20 due.
        inr1 = invoice(c_inr, "INR", "7210.71", "2701.51", InvoiceStatus.PARTIALLY_PAID)
        invoice(c_inr, "INR", "1000.00", "0.00", InvoiceStatus.OVERDUE, due_in_days=-1)
        # The same INR customer billed in AED (the BUG-12 subscription invoice).
        aed1 = invoice(c_inr, "AED", "433.36", "100.00", InvoiceStatus.PARTIALLY_PAID)
        usd1 = invoice(c_usd, "USD", "50.00", "50.00", InvoiceStatus.PAID, paid_at=now)
        payment(c_inr, "INR", "2111.51", inr1)
        payment(c_inr, "AED", "100.00", aed1)
        payment(c_usd, "USD", "50.00", usd1)
        cn = CreditNote(
            organization_id=org.id,
            credit_note_number=f"CN-{uuid.uuid4().hex[:8]}",
            customer_id=c_inr.id,
            invoice_id=inr1.id,
            status=CreditNoteStatus.APPLIED,
            issue_date=today,
            currency="INR",
            subtotal=Decimal("590.00"),
            total=Decimal("590.00"),
            balance_remaining=Decimal("0.00"),
        )
        db.add(cn)
        db.flush()
        db.add(CreditApplication(organization_id=org.id, credit_note_id=cn.id, invoice_id=inr1.id, amount=Decimal("590.00")))
        db.commit()

    # Independently computed expectations, per currency.
    expected = {
        "INR": {"invoiced": "8210.71", "collected": "2111.51", "outstanding": "5509.20", "overdue": "1000.00"},
        "AED": {"invoiced": "433.36", "collected": "100.00", "outstanding": "333.36", "overdue": "0.00"},
        "USD": {"invoiced": "50.00", "collected": "50.00", "outstanding": "0.00", "overdue": "0.00"},
    }
    for cur, e in expected.items():
        e["rate"] = _rate(e["collected"], e["invoiced"])
    return {
        "org": org,
        "today": today,
        "c_inr": c_inr,
        "c_usd": c_usd,
        "expected": expected,
        "range": {"range": "custom", "start": str(today - timedelta(days=35)), "end": str(today)},
    }


def _by(rows, key="currency"):
    return {row[key]: row for row in rows}


# --- BUG-01: reports ------------------------------------------------------------------------------------------


def test_reports_kpis_are_per_currency(client, auth_headers, mixed):
    exp = mixed["expected"]
    res = client.get("/api/v1/reports/dashboard", params=mixed["range"], headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    # Scalars: base currency only, and labelled.
    assert body["total_invoiced"] == exp["INR"]["invoiced"]  # not 8,694.07 (INR + AED + USD)
    assert body["outstanding_receivables"] == exp["INR"]["outstanding"]  # not 5,842.56
    assert body["currency"] == "INR"
    assert body["collection_rate"] == exp["INR"]["rate"]
    assert body["average_invoice_value"] == "4105.36"
    assert body["currencies"] == ["INR", "AED", "USD"]
    by = _by(body["by_currency"])
    for cur, e in exp.items():
        assert by[cur]["total_invoiced"] == e["invoiced"]
        assert by[cur]["total_collected"] == e["collected"]
        assert by[cur]["outstanding_receivables"] == e["outstanding"]
        assert by[cur]["overdue_receivables"] == e["overdue"]
        assert by[cur]["collection_rate"] == e["rate"]

    aed = client.get("/api/v1/reports/dashboard", params={**mixed["range"], "currency": "aed"}, headers=auth_headers).json()
    assert aed["currency"] == "AED"
    assert aed["total_invoiced"] == exp["AED"]["invoiced"]
    assert aed["outstanding_receivables"] == exp["AED"]["outstanding"]


def test_reports_analytics_filter_and_label_currency(client, auth_headers, mixed):
    exp, rng, h = mixed["expected"], mixed["range"], auth_headers
    for cur, e in exp.items():
        params = {**rng, "currency": cur}
        revenue = client.get("/api/v1/reports/revenue", params=params, headers=h).json()
        assert revenue["currency"] == cur
        assert sum(Decimal(p["amount"]) for p in revenue["revenue_over_time"]) == Decimal(e["collected"])
        assert sum(Decimal(p["invoiced"]) for p in revenue["invoiced_vs_collected"]) == Decimal(e["invoiced"])
        assert all(row["currency"] == cur for row in revenue["revenue_by_customer"])
        assert sum(Decimal(r["amount"]) for r in revenue["revenue_by_customer"]) == Decimal(e["collected"])

        receivables = client.get("/api/v1/reports/receivables", params=params, headers=h).json()
        assert sum(Decimal(b["amount"]) for b in receivables["outstanding_by_aging"]) == Decimal(e["outstanding"])
        assert all(row["currency"] == cur for row in receivables["top_customers_by_outstanding"])

        invoices = client.get("/api/v1/reports/invoices", params=params, headers=h).json()
        assert sum(Decimal(v["amount"]) for v in invoices["by_status"].values()) == Decimal(e["invoiced"])

        payments = client.get("/api/v1/reports/payments", params=params, headers=h).json()
        assert payments["total_payments"] == e["collected"]
        assert all(row["currency"] == cur for row in payments["method_breakdown"])

        customers = client.get("/api/v1/reports/customers", params=params, headers=h).json()
        assert sum(Decimal(r["amount"]) for r in customers["top_customers_by_revenue"]) == Decimal(e["collected"])
        assert sum(Decimal(r["amount"]) for r in customers["top_customers_by_outstanding"]) == Decimal(e["outstanding"])

    # Default = base currency, never the mixed sum.
    receivables = client.get("/api/v1/reports/receivables", params=rng, headers=h).json()
    aging = {b["bucket"]: b["amount"] for b in receivables["outstanding_by_aging"]}
    assert aging["current"] == "4509.20" and aging["1_30"] == "1000.00"  # was 4,942.56 current (INR + AED)


@pytest.mark.parametrize(
    "section",
    [
        "revenue_over_time",
        "invoiced_vs_collected",
        "revenue_by_customer",
        "outstanding_by_aging",
        "top_customers_by_outstanding",
        "method_breakdown",
    ],
)
def test_csv_export_rows_carry_currency(client, auth_headers, mixed, section):
    res = client.get("/api/v1/reports/export", params={**mixed["range"], "section": section}, headers=auth_headers)
    assert res.status_code == 200
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert rows and all(row["currency"] in {"INR", "AED", "USD"} for row in rows)
    amount_col = {"invoiced_vs_collected": "invoiced"}.get(section, "amount")
    totals = {}
    for row in rows:
        totals[row["currency"]] = totals.get(row["currency"], Decimal("0")) + Decimal(row[amount_col])
    exp = mixed["expected"]
    want_key = {
        "revenue_over_time": "collected",
        "invoiced_vs_collected": "invoiced",
        "revenue_by_customer": "collected",
        "outstanding_by_aging": "outstanding",
        "top_customers_by_outstanding": "outstanding",
        "method_breakdown": "collected",
    }[section]
    for cur, e in exp.items():
        assert totals.get(cur, Decimal("0")) == Decimal(e[want_key]), (cur, totals)


# --- BUG-01: collections, invoices, payments, dashboard, customer --------------------------------------------


def test_collections_dashboard_is_per_currency(client, auth_headers, mixed):
    exp = mixed["expected"]
    body = client.get("/api/v1/collections/dashboard", headers=auth_headers).json()
    assert body["kpis"]["total_outstanding"] == exp["INR"]["outstanding"]  # was 5,842.56
    assert body["currency"] == "INR"
    assert body["kpis"]["overdue_amount"] == exp["INR"]["overdue"]
    assert sum(Decimal(b["amount"]) for b in body["aging_summary"]) == Decimal(exp["INR"]["outstanding"])
    by = _by(body["kpis_by_currency"])
    assert by["AED"]["total_outstanding"] == exp["AED"]["outstanding"]
    assert all(row["currency"] in exp for row in body["upcoming_due_invoices"])

    aed = client.get("/api/v1/collections/dashboard", params={"currency": "AED"}, headers=auth_headers).json()
    assert aed["kpis"]["total_outstanding"] == exp["AED"]["outstanding"]
    assert sum(Decimal(b["amount"]) for b in aed["aging_summary"]) == Decimal(exp["AED"]["outstanding"])


def test_collection_rate_is_identical_on_collections_and_reports(client, auth_headers, mixed):
    """BUG-14: one formula (net cash / invoiced; credit notes are not cash), per currency."""
    exp = mixed["expected"]
    window = {"range": "custom", "start": str(mixed["today"] - timedelta(days=30)), "end": str(mixed["today"])}
    old_style = client.get("/api/v1/collections/dashboard", headers=auth_headers).json()["kpis"]["collection_rate"]
    assert old_style == exp["INR"]["rate"]  # credit notes are not cash
    reports = _by(client.get("/api/v1/reports/dashboard", params=window, headers=auth_headers).json()["by_currency"])
    collections = _by(client.get("/api/v1/collections/dashboard", headers=auth_headers).json()["kpis_by_currency"])
    for cur, e in exp.items():
        assert collections[cur]["collection_rate"] == reports[cur]["collection_rate"] == e["rate"]
    # The 590.00 INR credit note is not counted as collected (would be 32.90%).
    assert collections["INR"]["collection_rate"] == "25.72"


def test_invoice_summary_is_per_currency(client, auth_headers, mixed):
    body = client.get("/api/v1/invoices/summary", headers=auth_headers).json()
    assert body["total_outstanding"] == "5509.20"
    assert body["currency"] == "INR"
    by = _by(body["by_currency"])
    assert by["AED"]["total_outstanding"] == "333.36"
    assert by["USD"]["total_revenue"] == "50.00"
    assert body["total_invoices"] == 4


def test_payments_summary_is_per_currency(client, auth_headers, mixed):
    body = client.get("/api/v1/payments/summary", headers=auth_headers).json()
    assert body["total_collected"] == "2111.51"
    assert body["currency"] == "INR"
    assert body["count"] == 3
    by = _by(body["by_currency"])
    assert {cur: row["total_collected"] for cur, row in by.items()} == {"INR": "2111.51", "AED": "100.00", "USD": "50.00"}

    recon = client.get("/api/v1/payments/reconciliation/summary", headers=auth_headers).json()
    assert recon["currency"] == "INR" and recon["unallocated_amount"] == "0.00"


def test_dashboard_summary_trend_and_metrics_are_per_currency(client, auth_headers, mixed):
    body = client.get("/api/v1/dashboard/summary", params={"range": "30_days"}, headers=auth_headers).json()
    assert body["revenue"]["trend"][-1]["invoiced"] == "8210.71"  # was 8,694.07
    assert body["metrics"]["total_revenue"] == "2111.51"
    assert body["metrics"]["outstanding_amount"] == "5509.20"
    assert body["currency"] == "INR"
    metrics = _by(body["metrics"]["by_currency"])
    assert metrics["AED"]["outstanding_amount"] == "333.36"
    point = body["revenue"]["trend"][-1]
    assert point["invoiced"] == "8210.71"  # was 8,694.07
    assert point["revenue"] == "2111.51"
    trend = _by(point["by_currency"])
    assert trend["AED"]["invoiced"] == "433.36" and trend["USD"]["revenue"] == "50.00"
    partial = body["pipeline"]["partially_paid"]
    assert partial["count"] == 2 and partial["amount"] == "4509.20"
    assert _by(partial["by_currency"])["AED"]["amount"] == "333.36"


def test_customer_stats_are_per_currency(client, auth_headers, mixed):
    body = client.get(f"/api/v1/customers/{mixed['c_inr'].id}", headers=auth_headers).json()
    stats = body["stats"]
    assert stats["outstanding_amount"] == "5509.20"
    assert stats["currency"] == "INR"
    assert _by(stats["by_currency"])["AED"]["outstanding_amount"] == "333.36"


def test_lifecycle_totals_are_per_currency(client, auth_headers, mixed):
    rows = {r["customer_id"]: r for r in client.get("/api/v1/lifecycle", headers=auth_headers).json()}
    row = rows[mixed["c_inr"].id]
    assert Decimal(str(row["amount_due"])) == Decimal("5509.20")
    assert row["currency"] == "INR"
    assert Decimal(str(_by(row["totals_by_currency"])["AED"]["amount_due"])) == Decimal("333.36")


# --- BUG-02: customer portal ----------------------------------------------------------------------------------


def test_portal_outstanding_is_per_currency(client, db, mixed):
    org, customer = mixed["org"], mixed["c_inr"]
    email = f"portal-{uuid.uuid4().hex[:6]}@example.com"
    db.add(
        CustomerPortalUser(
            organization_id=org.id,
            customer_id=customer.id,
            email=email,
            password_hash=hash_password("SecurePassword123!"),
            display_name="Portal User",
            is_active=True,
        )
    )
    db.commit()
    login = client.post(
        "/api/v1/portal/auth/login",
        json={"organization_id": org.id, "email": email, "password": "SecurePassword123!"},
    )
    assert login.status_code == 200, login.text
    headers = {"X-Portal-Token": login.json()["token"]}
    dash = client.get("/api/v1/portal/dashboard", headers=headers).json()
    assert Decimal(str(dash["total_outstanding_amount"])) == Decimal("5509.20")  # was 5,842.56
    assert dash["currency"] == "INR"
    by = _by(dash["outstanding_by_currency"])
    assert Decimal(by["INR"]["amount_due"]) == Decimal("5509.20") and by["INR"]["open_count"] == 2
    assert Decimal(by["AED"]["amount_due"]) == Decimal("333.36") and by["AED"]["open_count"] == 1
    assert {inv["currency"] for inv in dash["recent_invoices"]} == {"INR", "AED"}
    listed = client.get("/api/v1/portal/invoices", headers=headers).json()
    assert all(inv["currency"] in {"INR", "AED"} for inv in listed)


# --- BUG-11: expenses -----------------------------------------------------------------------------------------


def _expense(client, headers, **overrides):
    body = {"name": "Taxi", "date": str(datetime.now(timezone.utc).date()), "category": "Travel", "amount": "100.00"}
    body.update(overrides)
    return client.post("/api/v1/expenses", headers=headers, json=body)


def test_expense_currency_must_be_supported(client, auth_headers):
    assert _expense(client, auth_headers, currency="XYZ").status_code == 422
    assert _expense(client, auth_headers, currency="usd").json()["currency"] == "USD"
    created = _expense(client, auth_headers).json()
    patch = client.patch(f"/api/v1/expenses/{created['id']}", headers=auth_headers, json={"currency": "ABC"})
    assert patch.status_code == 422


def test_expense_summary_is_per_currency(client, auth_headers):
    _expense(client, auth_headers, amount="100.00", currency="INR", billable=True)
    _expense(client, auth_headers, amount="40.00", currency="AED")
    body = client.get("/api/v1/expenses/summary", headers=auth_headers).json()
    assert Decimal(str(body["total"])) == Decimal("100.00")  # was 140 (INR + AED)
    assert body["currency"] == "INR"
    by = _by(body["by_currency"])
    assert Decimal(str(by["AED"]["total"])) == Decimal("40.00")
    assert Decimal(str(by["INR"]["billable"])) == Decimal("100.00")


# --- BUG-12: subscription currency mismatch -------------------------------------------------------------------


def test_subscription_rejects_plan_in_other_currency(client, db, tenant, auth_headers):
    customer = tenant.customer(currency="INR")
    _, plan = tenant.product_with_plan(unit_amount="367.25")
    with tenant_context(tenant.organization.id):
        plan.currency = "AED"
        db.commit()
    body = {"customer_id": customer.id, "plan_id": plan.id}
    res = client.post("/api/v1/subscriptions", headers=auth_headers, json=body)
    assert res.status_code == 422, res.text
    assert "AED" in res.text and "INR" in res.text

    ok = client.post("/api/v1/subscriptions", headers=auth_headers, json={**body, "allow_currency_mismatch": True})
    assert ok.status_code == 201, ok.text
    assert ok.json()["currency"] == "AED"
