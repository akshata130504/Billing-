"""The invoice summary cards and tab counts agree with the invoices actually listed.

QA (new-bugs PDF, "Invoices - Invoice Dashboard"): with one sent, one void and one partially paid
invoice in the table, every card and tab count showed 0.
"""
from datetime import date, timedelta
from decimal import Decimal

BASE = "/api/v1/invoices"


def _sent_invoice(client, headers, customer, amount="1000.00"):
    res = client.post(BASE, json={
        "customer_id": customer.id,
        "issue_date": date.today().isoformat(),
        "due_date": (date.today() + timedelta(days=30)).isoformat(),
        "items": [{"description": "Education", "quantity": "1", "unit_price": amount, "tax_rate_pct": "18"}],
    }, headers=headers)
    assert res.status_code == 201, res.text
    inv = res.json()
    assert client.post(f"{BASE}/{inv['id']}/send", headers=headers).status_code == 200
    return inv


def test_summary_counts_and_totals_match_the_listed_invoices(client, tenant, auth_headers):
    customer = tenant.customer()
    sent = _sent_invoice(client, auth_headers, customer)                 # 1180.00 outstanding
    voided = _sent_invoice(client, auth_headers, customer)
    partly = _sent_invoice(client, auth_headers, customer)
    res = client.post(f"{BASE}/{voided['id']}/void", json={"reason": "Issued twice"}, headers=auth_headers)
    assert res.status_code == 200, res.text
    res = client.post(f"{BASE}/{partly['id']}/record-payment",
                      json={"amount": "1100.00", "method": "cash"}, headers=auth_headers)
    assert res.status_code == 201, res.text

    listed = client.get(BASE, headers=auth_headers).json()["items"]
    by_status = {}
    for inv in listed:
        by_status[inv["status"]] = by_status.get(inv["status"], 0) + 1
    assert by_status == {"sent": 1, "void": 1, "partially_paid": 1}

    summary = client.get(f"{BASE}/summary", headers=auth_headers).json()
    assert summary["total_invoices"] == 3
    assert summary["sent_count"] == 1
    assert summary["void_count"] == 1
    assert summary["partially_paid_count"] == 1
    assert summary["draft_count"] == summary["paid_count"] == summary["overdue_count"] == 0
    # Outstanding = the sent invoice in full + the unpaid part of the partly paid one; void excluded.
    expected_outstanding = Decimal(sent["total"]) + Decimal(partly["total"]) - Decimal("1100.00")
    assert Decimal(str(summary["total_outstanding"])) == expected_outstanding
    assert Decimal(str(summary["total_revenue"])) == Decimal("1100.00")
