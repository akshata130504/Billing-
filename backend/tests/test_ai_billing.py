"""Tests for Phase 8: AI in Billing.

Verifies:
- Ask-Zia-equivalent queries answer from live data with cited sources (outstanding balance,
  overdue count, invoices beyond the organization's average late-payment cycle).
- CoCreate-equivalent drafting: structural validation of referenced entities at proposal time,
  and execution via the existing credit_service domain command (never a direct table write).
- Stale-draft rejection: an expired draft cannot be confirmed.
- Tool authorization: proposing/confirming a draft requires the finance role, not just viewer.
- Tenant isolation: one organization cannot see or confirm another organization's AI activity.
- Writing Assistant produces tone-adjusted, editable text.
- Audit completeness: every draft proposal/confirmation is recorded to the audit log.
"""
import uuid
from datetime import date, timedelta

from backend.app.models import AuditLog
from backend.app.models.ai import AIActionDraft, AIActionDraftStatus
from backend.app.models.invoices import Invoice, InvoiceStatus


def _make_overdue_invoice(tenant, customer, days_overdue: int, amount="1000.00"):
    from decimal import Decimal

    today = date.today()
    code = uuid.uuid4().hex[:6].upper()
    amt = Decimal(amount)
    inv = Invoice(
        organization_id=tenant.organization.id,
        invoice_number=f"INV-{code}",
        customer_id=customer.id,
        status=InvoiceStatus.OVERDUE,
        issue_date=today - timedelta(days=days_overdue + 30),
        due_date=today - timedelta(days=days_overdue),
        subtotal=amt,
        total=amt,
        amount_paid=Decimal("0.00"),
        amount_due=amt,
        public_token=uuid.uuid4().hex,
    )
    tenant.db.add(inv)
    tenant.db.commit()
    tenant.db.refresh(inv)
    return inv


def test_ai_query_outstanding_balance_and_overdue_count(client, tenant, auth_headers, db):
    customer = tenant.customer()
    tenant.invoice(customer, amount="500.00", status=InvoiceStatus.SENT)
    tenant.invoice(customer, amount="300.00", status=InvoiceStatus.OVERDUE)

    balance_res = client.post(
        "/api/v1/ai/queries",
        headers=auth_headers,
        json={"prompt": "What's our total outstanding balance right now?"},
    )
    assert balance_res.status_code == 200
    balance_body = balance_res.json()
    assert balance_body["data"]["total_outstanding_balance"] == "800.00"
    assert balance_body["data"]["open_invoice_count"] == 2
    assert len(balance_body["sources"]) == 1
    assert balance_body["sources"][0]["source_type"] == "receivable_summary"

    count_res = client.post(
        "/api/v1/ai/queries",
        headers=auth_headers,
        json={"prompt": "How many invoices are overdue?"},
    )
    assert count_res.status_code == 200
    assert count_res.json()["data"]["overdue_invoice_count"] == 1


def test_ai_query_overdue_beyond_average_cycle(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _make_overdue_invoice(tenant, customer, days_overdue=10)
    _make_overdue_invoice(tenant, customer, days_overdue=20)
    furthest = _make_overdue_invoice(tenant, customer, days_overdue=30)

    res = client.post(
        "/api/v1/ai/queries",
        headers=auth_headers,
        json={"prompt": "Which invoices are overdue longer than our average late-payment cycle?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["data"]["average_late_payment_days"] == 20.0
    assert body["data"]["overdue_invoice_count"] == 3
    assert body["data"]["beyond_average_count"] == 1
    assert body["sources"][0]["source_id"] == furthest.id


def test_ai_draft_propose_validates_referenced_entities(client, tenant, auth_headers, db):
    res = client.post(
        "/api/v1/ai/drafts",
        headers=auth_headers,
        json={
            "prompt": "Create a credit note for a customer that does not exist",
            "action_type": "credit_note",
            "customer_id": "cust_does_not_exist",
            "lines": [{"description": "Service credit", "quantity": 1, "unit_price": 100}],
        },
    )
    assert res.status_code == 422
    errors = res.json()["error"]["details"]["fields"]["draft"]
    assert any("customer" in e.lower() for e in errors)

    # The rejected draft is still persisted for audit/history purposes.
    rejected = db.query(AIActionDraft).filter(AIActionDraft.status == AIActionDraftStatus.REJECTED).first()
    assert rejected is not None


def test_ai_draft_propose_confirm_executes_credit_note_and_audits(client, tenant, auth_headers, db):
    customer = tenant.customer()

    propose_res = client.post(
        "/api/v1/ai/drafts",
        headers=auth_headers,
        json={
            "prompt": "Issue a goodwill credit note for this customer",
            "action_type": "credit_note",
            "customer_id": customer.id,
            "reason": "Goodwill adjustment",
            "lines": [{"description": "Service credit", "quantity": 1, "unit_price": 250, "tax_rate_pct": 0}],
        },
    )
    assert propose_res.status_code == 200
    draft = propose_res.json()["draft"]
    assert draft["status"] == "validated"

    confirm_res = client.post(f"/api/v1/ai/drafts/{draft['id']}/confirm", headers=auth_headers)
    assert confirm_res.status_code == 200
    confirmed = confirm_res.json()
    assert confirmed["draft"]["status"] == "executed"
    assert confirmed["draft"]["executed_entity_type"] == "credit_note"
    assert confirmed["executed_result"]["total"] == "250.00"

    # Confirming an already-executed draft is rejected.
    second_confirm = client.post(f"/api/v1/ai/drafts/{draft['id']}/confirm", headers=auth_headers)
    assert second_confirm.status_code == 422

    # Both the proposal and the confirmation are audited.
    actions = {
        row.action
        for row in db.query(AuditLog).filter(AuditLog.entity_id == draft["id"]).all()
    }
    assert "AI_DRAFT_PROPOSED" in actions
    assert "AI_DRAFT_CONFIRMED" in actions


def test_ai_draft_confirm_rejects_expired_draft(client, tenant, auth_headers, db):
    customer = tenant.customer()
    propose_res = client.post(
        "/api/v1/ai/drafts",
        headers=auth_headers,
        json={
            "prompt": "Issue a credit note",
            "action_type": "credit_note",
            "customer_id": customer.id,
            "lines": [{"description": "Adjustment", "quantity": 1, "unit_price": 50}],
        },
    )
    draft_id = propose_res.json()["draft"]["id"]

    # Force the draft into the past to simulate staleness.
    draft_row = db.query(AIActionDraft).filter(AIActionDraft.id == draft_id).first()
    draft_row.expires_at = draft_row.expires_at - timedelta(hours=1)
    db.commit()

    confirm_res = client.post(f"/api/v1/ai/drafts/{draft_id}/confirm", headers=auth_headers)
    assert confirm_res.status_code == 422

    db.refresh(draft_row)
    assert draft_row.status == AIActionDraftStatus.EXPIRED


def test_ai_draft_requires_finance_role(client, tenant, db):
    from backend.app.models import MemberRole

    viewer_headers = tenant.headers_for_role(MemberRole.VIEWER)
    customer = tenant.customer()

    res = client.post(
        "/api/v1/ai/drafts",
        headers=viewer_headers,
        json={
            "prompt": "Issue a credit note",
            "action_type": "credit_note",
            "customer_id": customer.id,
            "lines": [{"description": "Adjustment", "quantity": 1, "unit_price": 50}],
        },
    )
    assert res.status_code == 403


def test_ai_tenant_isolation_across_organizations(client, db):
    import uuid as _uuid
    from backend.tests.conftest import Tenant

    tenant_a = Tenant(db, _uuid.uuid4().hex[:8])
    tenant_b = Tenant(db, _uuid.uuid4().hex[:8])
    headers_a = tenant_a.headers()
    headers_b = tenant_b.headers()

    query_res = client.post(
        "/api/v1/ai/queries",
        headers=headers_a,
        json={"prompt": "What's our total outstanding balance right now?"},
    )
    assert query_res.status_code == 200

    history_b = client.get("/api/v1/ai/history", headers=headers_b)
    assert history_b.status_code == 200
    assert history_b.json() == []

    customer_a = tenant_a.customer()
    propose_res = client.post(
        "/api/v1/ai/drafts",
        headers=headers_a,
        json={
            "prompt": "Issue a credit note",
            "action_type": "credit_note",
            "customer_id": customer_a.id,
            "lines": [{"description": "Adjustment", "quantity": 1, "unit_price": 20}],
        },
    )
    draft_id = propose_res.json()["draft"]["id"]

    cross_org_confirm = client.post(f"/api/v1/ai/drafts/{draft_id}/confirm", headers=headers_b)
    assert cross_org_confirm.status_code == 404


def test_ai_writing_assistant_and_history(client, tenant, auth_headers, db):
    res = client.post(
        "/api/v1/ai/writing",
        headers=auth_headers,
        json={
            "purpose": "payment_reminder",
            "tone": "firm",
            "context": {
                "customer_name": "Acme Corp",
                "invoice_number": "INV-000123",
                "amount_due": "5000.00",
                "due_date": "2026-08-01",
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["subject"] == "Payment reminder: INV-000123"
    assert "Acme Corp" in body["body"]
    assert "INV-000123" in body["body"]

    history_res = client.get("/api/v1/ai/history?mode=writing", headers=auth_headers)
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) == 1
    assert history[0]["mode"] == "writing"
    assert history[0]["status"] == "completed"


def test_ai_draft_confirm_claim_is_released_when_execution_fails(client, tenant, auth_headers, db, monkeypatch):
    """The draft is claimed atomically; a failed credit note must not leave it 'executed'."""
    from backend.app.services import credit_service

    customer = tenant.customer()
    draft = client.post(
        "/api/v1/ai/drafts",
        headers=auth_headers,
        json={
            "prompt": "credit",
            "action_type": "credit_note",
            "customer_id": customer.id,
            "reason": "Goodwill",
            "lines": [{"description": "Credit", "quantity": 1, "unit_price": 10, "tax_rate_pct": 0}],
        },
    ).json()["draft"]

    def boom(*args, **kwargs):
        raise RuntimeError("credit service down")

    monkeypatch.setattr(credit_service, "create_credit_note", boom)
    try:
        client.post(f"/api/v1/ai/drafts/{draft['id']}/confirm", headers=auth_headers)
    except RuntimeError:
        pass
    stored = db.get(AIActionDraft, draft["id"])
    db.refresh(stored)
    assert stored.status == AIActionDraftStatus.VALIDATED

    monkeypatch.undo()
    ok = client.post(f"/api/v1/ai/drafts/{draft['id']}/confirm", headers=auth_headers)
    assert ok.status_code == 200, ok.text
    assert client.post(f"/api/v1/ai/drafts/{draft['id']}/confirm", headers=auth_headers).status_code == 422


def test_ai_mrr_uses_shared_definition(tenant, db):
    from decimal import Decimal

    from backend.app.models import Subscription, SubscriptionStatus
    from backend.app.services.ai_service import _tool_mrr_summary

    _, plan = tenant.product_with_plan(unit_amount="1000.00")
    customer = tenant.customer()
    today = date.today()
    db.add(
        Subscription(
            organization_id=tenant.organization.id,
            subscription_number=f"SUB-{uuid.uuid4().hex[:6]}",
            customer_id=customer.id,
            plan_id=plan.id,
            quantity=3,
            status=SubscriptionStatus.PAST_DUE,
            unit_price=Decimal("500"),
            discount_amount=Decimal("100"),
            start_date=today,
            current_period_start=today,
            current_period_end=today + timedelta(days=30),
        )
    )
    db.commit()
    _, data, _ = _tool_mrr_summary(db, tenant.organization.id)
    assert data["mrr"] == "1400.00"
    assert data["active_subscription_count"] == 1
