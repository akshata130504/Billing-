"""Adding an allocation keeps the payment's existing allocations (L-5), and a replace may keep an
allocation to an invoice the payment itself settled (L-2).

Before the fix, Reconciliation sent PUT /payments/{id}/allocations with only the new invoice: the
replace deleted the existing allocation and re-opened the invoice it had paid, while the UI said
"Payment allocated". Sending the full list instead was refused, because the settled invoice was
"paid, not open".
"""
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.app.core.database import engine
from backend.app.core.tenant_context import tenant_context
from backend.app.models import Invoice, PaymentAllocation
from backend.app.services import payment_service
from backend.tests.test_payment_allocation_guards import _allocation_audits, _customer, _put, _sent_invoice

API = "/api/v1"


def _add(client, tenant, payment_id, invoice_id, amount, headers=None):
    return client.post(f"{API}/payments/{payment_id}/allocations/add", headers=headers or tenant.headers(),
                       json={"invoice_id": invoice_id, "amount": amount})


def _payment(client, tenant, customer_id, amount, allocations=None):
    body = {"customer_id": customer_id, "amount": amount, "method": "bank_transfer"}
    if allocations:
        body["allocations"] = allocations
    res = client.post(f"{API}/payments", headers=tenant.headers(), json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _invoice(db, tenant, invoice_id):
    with tenant_context(tenant.organization.id):
        db.expire_all()
        inv = db.get(Invoice, invoice_id)
        return inv.status.value, inv.amount_paid, inv.amount_due


def _allocations(db, tenant, payment_id):
    with tenant_context(tenant.organization.id):
        db.expire_all()
        rows = db.execute(select(PaymentAllocation.invoice_id, PaymentAllocation.amount)
                          .where(PaymentAllocation.payment_id == payment_id)).all()
        return sorted((r.invoice_id, r.amount) for r in rows)


def _state(db, tenant, payment_id, *invoice_ids):
    return _allocations(db, tenant, payment_id), [_invoice(db, tenant, i) for i in invoice_ids]


def _partly_allocated(client, tenant, name):
    """The L-5 scenario: payment 120 with 100 on invoice A (now paid), invoice B 50 open."""
    cust = _customer(client, tenant, name)
    a = _sent_invoice(client, tenant, cust, amount="100.00")
    b = _sent_invoice(client, tenant, cust, amount="50.00")
    pay = _payment(client, tenant, cust, "120.00", [{"invoice_id": a, "amount": "100.00"}])
    assert pay["reconciliation_status"] == "exception"
    return cust, a, b, pay["id"]


def test_add_keeps_existing_allocation_original_scenario(client, db, tenant):
    _cust, a, b, pay = _partly_allocated(client, tenant, "L5 Original")
    audits_before = _allocation_audits(db, tenant, pay)

    res = _add(client, tenant, pay, b, "20.00")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["amount_allocated"] == "120.00"
    assert body["amount_unallocated"] == "0.00"
    assert body["reconciliation_status"] == "matched"
    assert sorted((x["invoice_id"], x["amount"]) for x in body["allocations"]) == sorted([(a, "100.00"), (b, "20.00")])
    assert _invoice(db, tenant, a) == ("paid", Decimal("100.00"), Decimal("0.00"))
    assert _invoice(db, tenant, b) == ("partially_paid", Decimal("20.00"), Decimal("30.00"))
    assert _allocations(db, tenant, pay) == sorted([(a, Decimal("100.00")), (b, Decimal("20.00"))])
    assert _allocation_audits(db, tenant, pay) == audits_before + 1


def test_repeating_the_add_is_refused_and_creates_no_duplicate(client, db, tenant):
    _cust, a, b, pay = _partly_allocated(client, tenant, "L5 Repeat")
    assert _add(client, tenant, pay, b, "20.00").status_code == 200
    before = _state(db, tenant, pay, a, b)

    res = _add(client, tenant, pay, b, "20.00")

    assert res.status_code == 422, res.text
    assert "unallocated" in res.json()["error"]["details"]["fields"]["amount"]
    assert _state(db, tenant, pay, a, b) == before


def test_add_to_an_invoice_already_allocated_merges_into_one_row(client, db, tenant):
    cust = _customer(client, tenant, "L5 Merge")
    a = _sent_invoice(client, tenant, cust, amount="100.00")
    pay = _payment(client, tenant, cust, "100.00", [{"invoice_id": a, "amount": "60.00"}])["id"]

    res = _add(client, tenant, pay, a, "40.00")

    assert res.status_code == 200, res.text
    assert _allocations(db, tenant, pay) == [(a, Decimal("100.00"))]
    assert _invoice(db, tenant, a) == ("paid", Decimal("100.00"), Decimal("0.00"))


@pytest.mark.parametrize("amount", ["20.01", "21.00"])
def test_over_allocating_the_payment_is_refused_without_changes(client, db, tenant, amount):
    _cust, a, b, pay = _partly_allocated(client, tenant, f"L5 Over {amount}")
    before = _state(db, tenant, pay, a, b)

    res = _add(client, tenant, pay, b, amount)

    assert res.status_code == 422, res.text
    assert _state(db, tenant, pay, a, b) == before


def test_amount_above_the_invoice_balance_is_refused(client, db, tenant):
    cust = _customer(client, tenant, "L5 Balance")
    small = _sent_invoice(client, tenant, cust, amount="10.00")
    pay = _payment(client, tenant, cust, "50.00")["id"]

    res = _add(client, tenant, pay, small, "11.00")

    assert res.status_code == 422, res.text
    assert "exceeds amount due" in res.json()["error"]["details"]["fields"]["allocations.0.amount"]
    assert _allocations(db, tenant, pay) == []


def test_other_customer_and_other_currency_are_refused(client, db, tenant):
    _cust, a, b, pay = _partly_allocated(client, tenant, "L5 Guards")
    other = _sent_invoice(client, tenant, _customer(client, tenant, "L5 Someone Else"), amount="50.00")
    usd = _sent_invoice(client, tenant, _cust, amount="50.00", currency="USD")
    before = _state(db, tenant, pay, a, b)

    r1 = _add(client, tenant, pay, other, "10.00")
    r2 = _add(client, tenant, pay, usd, "10.00")

    assert r1.status_code == 422 and "different customer" in r1.text
    assert r2.status_code == 422 and "USD" in r2.text
    assert _state(db, tenant, pay, a, b) == before


def test_draft_and_void_invoices_are_refused(client, db, tenant):
    _cust, a, b, pay = _partly_allocated(client, tenant, "L5 States")
    draft = client.post(f"{API}/invoices", headers=tenant.headers(), json={
        "customer_id": _cust, "items": [{"description": "Draft", "quantity": "1", "unit_price": "10.00"}]}).json()["id"]
    void = _sent_invoice(client, tenant, _cust, amount="10.00")
    assert client.post(f"{API}/invoices/{void}/void", headers=tenant.headers(), json={"reason": "test"}).status_code == 200
    before = _state(db, tenant, pay, a, b)

    for inv in (draft, void):
        res = _add(client, tenant, pay, inv, "5.00")
        assert res.status_code == 422 and "not open" in res.text, res.text
    assert _state(db, tenant, pay, a, b) == before


def test_other_tenants_payment_and_invoice_are_not_found(client, db, tenant):
    import uuid

    from backend.tests.conftest import Tenant

    _cust, a, b, pay = _partly_allocated(client, tenant, "L5 Tenant A")
    # Plain hex suffix: other tests search organizations for literal "%" and "_".
    other = Tenant(db, uuid.uuid4().hex[:8])
    res = _add(client, tenant, pay, b, "5.00", headers=other.headers())
    assert res.status_code == 404, res.text
    assert _invoice(db, tenant, b) == ("sent", Decimal("0.00"), Decimal("50.00"))


def test_viewer_cannot_add(client, db, tenant):
    from backend.app.models import MemberRole

    _cust, a, b, pay = _partly_allocated(client, tenant, "L5 Viewer")
    res = _add(client, tenant, pay, b, "5.00", headers=tenant.headers_for_role(MemberRole.VIEWER))
    assert res.status_code == 403, res.text


def test_partly_refunded_payment_limits_the_add_to_the_effective_amount(client, db, tenant):
    cust = _customer(client, tenant, "L5 Refund")
    a = _sent_invoice(client, tenant, cust, amount="100.00")
    b = _sent_invoice(client, tenant, cust, amount="50.00")
    pay = _payment(client, tenant, cust, "120.00", [{"invoice_id": a, "amount": "100.00"}])["id"]
    refund = client.post(f"{API}/payments/{pay}/refund", headers=tenant.headers(), json={"amount": "15.00", "reason": "partial"})
    assert refund.status_code == 200, refund.text
    # The refund may reduce allocations proportionally; whatever remains unallocated is the limit.
    left = Decimal(client.get(f"{API}/payments/{pay}", headers=tenant.headers()).json()["amount_unallocated"])

    over = _add(client, tenant, pay, b, str(left + Decimal("0.01")))
    ok = _add(client, tenant, pay, b, str(left)) if left > 0 else None

    assert over.status_code == 422, over.text
    if ok is not None:
        assert ok.status_code == 200, ok.text
        assert ok.json()["amount_unallocated"] == "0.00"


def test_failure_midway_rolls_back_everything(client, db, tenant, monkeypatch):
    _cust, a, b, pay = _partly_allocated(client, tenant, "L5 Rollback")
    before = _state(db, tenant, pay, a, b)
    audits_before = _allocation_audits(db, tenant, pay)

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated failure after the allocation row was written")

    monkeypatch.setattr(payment_service, "recompute_invoice", boom)
    with pytest.raises(RuntimeError):
        _add(client, tenant, pay, b, "20.00")

    assert _state(db, tenant, pay, a, b) == before
    assert _allocation_audits(db, tenant, pay) == audits_before


def test_replace_may_keep_an_allocation_to_an_invoice_the_payment_settled(client, db, tenant):
    """L-2: the full set (settled allocation kept, leftover added) is accepted by the replace."""
    _cust, a, b, pay = _partly_allocated(client, tenant, "L2 Keep")

    res = _put(client, tenant, pay, [{"invoice_id": a, "amount": "100.00"}, {"invoice_id": b, "amount": "20.00"}])

    assert res.status_code == 200, res.text
    assert _invoice(db, tenant, a) == ("paid", Decimal("100.00"), Decimal("0.00"))
    assert _invoice(db, tenant, b) == ("partially_paid", Decimal("20.00"), Decimal("30.00"))


def test_replace_may_reduce_but_not_increase_a_settled_allocation(client, db, tenant):
    _cust, a, b, pay = _partly_allocated(client, tenant, "L2 Reduce")

    up = _put(client, tenant, pay, [{"invoice_id": a, "amount": "100.01"}])
    assert up.status_code == 422, up.text
    down = _put(client, tenant, pay, [{"invoice_id": a, "amount": "90.00"}])
    assert down.status_code == 200, down.text
    assert _invoice(db, tenant, a) == ("partially_paid", Decimal("90.00"), Decimal("10.00"))


def test_replace_still_replaces(client, db, tenant):
    """The PUT keeps its documented replace semantics: an omitted allocation is removed."""
    _cust, a, b, pay = _partly_allocated(client, tenant, "L2 Replace")

    res = _put(client, tenant, pay, [{"invoice_id": b, "amount": "20.00"}])

    assert res.status_code == 200, res.text
    assert _allocations(db, tenant, pay) == [(b, Decimal("20.00"))]
    assert _invoice(db, tenant, a)[0] == "sent"


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="real row-lock concurrency needs PostgreSQL (set TEST_DATABASE_URL)")
def test_concurrent_adds_cannot_over_allocate(client, db, tenant):
    from backend.tests.test_postgres_concurrency import run_concurrently, thread_client

    _cust, a, b, pay = _partly_allocated(client, tenant, "L5 Concurrent")
    headers = tenant.headers()
    codes, errors = run_concurrently(
        lambda _i: thread_client().post(f"{API}/payments/{pay}/allocations/add", headers=headers,
                                        json={"invoice_id": b, "amount": "20.00"}).status_code, n=4)
    assert errors == [None] * 4, errors
    assert codes.count(200) == 1, codes
    assert all(c in (200, 422) for c in codes), codes
    with tenant_context(tenant.organization.id):
        db.expire_all()
        total = db.scalar(select(func.sum(PaymentAllocation.amount)).where(PaymentAllocation.payment_id == pay))
    assert total == Decimal("120.00")
    assert _invoice(db, tenant, a) == ("paid", Decimal("100.00"), Decimal("0.00"))
