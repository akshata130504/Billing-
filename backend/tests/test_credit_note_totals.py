"""GET /credit-notes real total count and GET /credit-notes/summary."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from backend.app.models import MemberRole
from backend.app.models.credits import CreditNote, CreditNoteStatus
from backend.app.services import credit_service

from backend.tests.conftest import Tenant

URL = "/api/v1/credit-notes"


def _note(tenant, customer, amount, *, currency="INR", issue=None, status=CreditNoteStatus.ISSUED):
    cn = credit_service.create_credit_note(
        tenant.db,
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        lines=[{"description": "Adj", "amount": str(amount), "tax_rate_pct": "0"}],
        currency=currency,
        issue_date=issue,
        status=status,
    )
    return cn


def test_list_total_is_real_count_not_page_size(client, tenant):
    customer = tenant.customer()
    for i in range(7):
        _note(tenant, customer, 10 + i)
    res = client.get(f"{URL}?limit=3&offset=0", headers=tenant.headers())
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 3
    assert body["total"] == 7
    assert body["limit"] == 3 and body["offset"] == 0
    last_page = client.get(f"{URL}?limit=3&offset=6", headers=tenant.headers()).json()
    assert len(last_page["items"]) == 1 and last_page["total"] == 7
    # pages do not overlap
    ids = set()
    for off in (0, 3, 6):
        ids |= {n["id"] for n in client.get(f"{URL}?limit=3&offset={off}", headers=tenant.headers()).json()["items"]}
    assert len(ids) == 7


def test_list_total_respects_filters(client, tenant):
    a, b = tenant.customer(), tenant.customer()
    _note(tenant, a, 10)
    _note(tenant, a, 20)
    _note(tenant, b, 30)
    old = _note(tenant, b, 40, issue=date.today() - timedelta(days=40))
    res = client.get(f"{URL}?customer_id={a.id}&limit=1", headers=tenant.headers()).json()
    assert res["total"] == 2 and len(res["items"]) == 1
    recent = client.get(f"{URL}?date_from={(date.today() - timedelta(days=5)).isoformat()}", headers=tenant.headers()).json()
    assert recent["total"] == 3 and old.id not in {n["id"] for n in recent["items"]}
    assert client.get(f"{URL}?status=void", headers=tenant.headers()).json()["total"] == 0
    bad = client.get(f"{URL}?date_from=2026-02-01&date_to=2026-01-01", headers=tenant.headers())
    assert bad.status_code == 422


def test_summary_business_rules_per_currency(client, tenant, db):
    customer = tenant.customer()
    inv = tenant.invoice(customer, amount="500.00")
    applied_note = _note(tenant, customer, 300)  # 200 applied -> partially applied, 100 remaining
    credit_service.apply_credit_note_to_invoice(
        db, organization_id=tenant.organization.id, credit_note_id=applied_note.id, invoice_id=inv.id, amount=Decimal("200.00")
    )
    _note(tenant, customer, 150)  # issued, untouched
    voided = _note(tenant, customer, 80)
    credit_service.void_credit_note(db, _ctx(tenant), voided.id, reason="mistake")
    _note(tenant, customer, 45, status=CreditNoteStatus.DRAFT)
    _note(tenant, customer, 99.99, currency="USD")

    res = client.get(f"{URL}/summary", headers=tenant.headers())
    assert res.status_code == 200, res.text
    s = res.json()
    assert s["total_count"] == 5
    assert s["count_by_status"]["partially_applied"] == 1
    assert s["count_by_status"]["issued"] == 2
    assert s["count_by_status"]["void"] == 1
    assert s["count_by_status"]["draft"] == 1
    by = {c["currency"]: c for c in s["currencies"]}
    assert set(by) == {"INR", "USD"}  # never summed across currencies
    inr = by["INR"]
    assert inr["issued_total"] == "450.00"  # 300 + 150 (void and draft excluded)
    assert inr["applied_total"] == "200.00"
    assert inr["remaining_balance"] == "250.00"  # 100 + 150
    assert inr["voided_total"] == "80.00"
    assert inr["draft_total"] == "45.00"
    assert Decimal(inr["issued_total"]) == Decimal(inr["applied_total"]) + Decimal(inr["remaining_balance"])
    assert by["USD"]["issued_total"] == "99.99" and by["USD"]["count"] == 1


def test_summary_filters_and_empty_org(client, tenant, db):
    empty = client.get(f"{URL}/summary", headers=tenant.headers()).json()
    assert empty["total_count"] == 0 and empty["currencies"] == []
    assert all(v == 0 for v in empty["count_by_status"].values())

    a, b = tenant.customer(), tenant.customer()
    _note(tenant, a, 100, issue=date.today() - timedelta(days=60))
    _note(tenant, a, 10)
    _note(tenant, b, 1)
    since = (date.today() - timedelta(days=30)).isoformat()
    ranged = client.get(f"{URL}/summary?from={since}", headers=tenant.headers()).json()
    assert ranged["currencies"][0]["issued_total"] == "11.00"
    assert ranged["filters"]["date_from"] == since
    only_a = client.get(f"{URL}/summary?customer_id={a.id}", headers=tenant.headers()).json()
    assert only_a["currencies"][0]["issued_total"] == "110.00"
    until = (date.today() - timedelta(days=30)).isoformat()
    old = client.get(f"{URL}/summary?to={until}", headers=tenant.headers()).json()
    assert old["currencies"][0]["issued_total"] == "100.00"


def test_summary_and_list_are_tenant_isolated_and_viewer_readable(client, tenant, db):
    other = Tenant(db, uuid.uuid4().hex[:8])
    _note(other, other.customer(), 999)
    mine = tenant.customer()
    _note(tenant, mine, 5)
    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    s = client.get(f"{URL}/summary", headers=viewer)
    assert s.status_code == 200
    assert s.json()["currencies"][0]["issued_total"] == "5.00"
    lst = client.get(URL, headers=viewer).json()
    assert lst["total"] == 1
    # filtering by another tenant's customer id yields nothing
    foreign = client.get(f"{URL}/summary?customer_id={other.customer().id}", headers=tenant.headers()).json()
    assert foreign["total_count"] == 0
    assert client.get(f"{URL}/summary").status_code == 401


def _ctx(tenant):
    from backend.app.api.deps import CurrentContext
    from backend.app.models import Membership

    membership = tenant.db.query(Membership).filter_by(organization_id=tenant.organization.id, user_id=tenant.owner.id).first()
    return CurrentContext(user=tenant.owner, organization=tenant.organization, membership=membership, ip_address=None, user_agent=None)
