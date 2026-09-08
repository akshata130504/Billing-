"""Backend tests for the Automation module (a minimal WHEN/IF/THEN rule engine).

Covers pure condition evaluation (`_resolve_field`/`_compare`/`evaluate_conditions`,
no DB needed), the five real action side effects, `dispatch()`'s defensive
never-raises contract plus its trigger/org/active filtering, rule CRUD
validation, RBAC over HTTP, tenant isolation, and dashboard aggregation.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import EntityNotFoundError, ValidationAppError
from backend.app.models import (
    ApprovalRequest,
    AutomationExecution,
    AutomationExecutionStatus,
    AutomationTrigger,
    CollectionActivity,
    CollectionActivityType,
    CollectionStatus,
    Customer,
    CustomerStatus,
    Invoice,
    InvoiceStatus,
    MemberRole,
    Membership,
    Organization,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Quote,
    QuoteStatus,
    User,
)
from backend.app.schemas.automation import AutomationRuleIn
from backend.app.schemas.common_refs import LineItemIn
from backend.app.schemas.invoices import InvoiceCreate
from backend.app.services import automation_service, collection_service, invoice_service
from backend.app.services.pagination import PageParams

BASE = "/api/v1/automation"


# --- fixtures --------------------------------------------------------------------------------


@pytest.fixture
def org_ctx(db: Session):
    uid = uuid.uuid4().hex[:8]
    org = Organization(name=f"Automation Test Org {uid}", slug=f"automation-org-{uid}", default_currency="INR")
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(email=f"automator_{uid}@example.com", full_name="Automation Tester", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    membership = Membership(organization_id=org.id, user_id=user.id, role="owner", status="active")
    db.add(membership)
    db.commit()

    customer = Customer(
        organization_id=org.id,
        customer_number=f"CUST-{uid}",
        display_name="Automation Customer",
        email=f"ar_{uid}@example.com",
        currency="INR",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    ctx = CurrentContext(user=user, organization=org, membership=membership, ip_address=None, user_agent=None)
    return org, user, customer, ctx


def _make_invoice(db, ctx, customer, *, due_in_days, amount="1000.00", send=True):
    invoice = invoice_service.create_invoice(
        db,
        ctx,
        InvoiceCreate(
            customer_id=customer.id,
            issue_date=date.today() - timedelta(days=60),
            due_date=date.today() + timedelta(days=due_in_days),
            currency="INR",
            items=[LineItemIn(description="Automation test service", quantity=Decimal("1"), unit_price=Decimal(amount), tax_rate_pct=Decimal("0"))],
        ),
    )
    if send:
        invoice = invoice_service.send_invoice(db, ctx, invoice)
    db.refresh(invoice)
    return invoice


def _make_rule(db, ctx, trigger, actions, conditions=None, name="Test rule"):
    return automation_service.create_rule(
        db, ctx, AutomationRuleIn(name=name, trigger=trigger, conditions=conditions or [], actions=actions)
    )


def _default_page() -> PageParams:
    return PageParams(page=1, page_size=50, sort=None)


# --- 1. condition evaluation (pure, no DB) ----------------------------------------------------


def test_resolve_field_amount_from_invoice_payment_or_quote():
    invoice = Invoice(total=Decimal("1500.00"))
    assert automation_service._resolve_field("amount", {"invoice": invoice}) == Decimal("1500.00")

    payment = Payment(amount=Decimal("750.50"))
    assert automation_service._resolve_field("amount", {"payment": payment}) == Decimal("750.50")

    quote = Quote(total=Decimal("2500.00"))
    assert automation_service._resolve_field("amount", {"quote": quote}) == Decimal("2500.00")

    # invoice takes precedence when several are present
    assert automation_service._resolve_field("amount", {"invoice": invoice, "payment": payment}) == Decimal("1500.00")
    assert automation_service._resolve_field("amount", {}) is None


def test_resolve_field_days_overdue():
    assert automation_service._resolve_field("days_overdue", {}) == 0

    overdue_invoice = Invoice(status=InvoiceStatus.OVERDUE, due_date=date.today() - timedelta(days=12))
    assert automation_service._resolve_field("days_overdue", {"invoice": overdue_invoice}) == 12

    # a non-open invoice (e.g. draft) is never "overdue" per invoice_service.days_overdue
    draft_invoice = Invoice(status=InvoiceStatus.DRAFT, due_date=date.today() - timedelta(days=12))
    assert automation_service._resolve_field("days_overdue", {"invoice": draft_invoice}) == 0


def test_resolve_field_status_from_invoice_payment_or_quote():
    assert automation_service._resolve_field("status", {"invoice": Invoice(status=InvoiceStatus.SENT)}) == "sent"
    assert automation_service._resolve_field("status", {"payment": Payment(status=PaymentStatus.FAILED)}) == "failed"
    assert automation_service._resolve_field("status", {"quote": Quote(status=QuoteStatus.ACCEPTED)}) == "accepted"
    assert automation_service._resolve_field("status", {}) is None


def test_resolve_field_payment_method():
    assert automation_service._resolve_field("payment_method", {"payment": Payment(method=PaymentMethod.UPI)}) == "upi"
    assert automation_service._resolve_field("payment_method", {}) is None


def test_resolve_field_customer_segment_proxies_customer_status():
    assert automation_service._resolve_field("customer_segment", {"customer": Customer(status=CustomerStatus.INACTIVE)}) == "inactive"
    assert automation_service._resolve_field("customer_segment", {"customer": Customer(status=CustomerStatus.ACTIVE)}) == "active"
    assert automation_service._resolve_field("customer_segment", {}) is None


def test_resolve_field_falls_back_to_raw_context_key():
    assert automation_service._resolve_field("some_custom_key", {"some_custom_key": "hello"}) == "hello"
    assert automation_service._resolve_field("missing_key", {}) is None


@pytest.mark.parametrize(
    "op,actual,expected,matches",
    [
        ("eq", "100.00", "100.00", True),
        ("eq", "100", "200", False),
        ("ne", "100", "200", True),
        ("ne", "100", "100", False),
        ("gt", 10, 5, True),
        ("gt", 5, 10, False),
        ("gte", 10, 10, True),
        ("gte", 9, 10, False),
        ("lt", 5, 10, True),
        ("lt", 10, 5, False),
        ("lte", 10, 10, True),
        ("lte", 11, 10, False),
        ("contains", "Overdue Invoice", "overdue", True),
        ("contains", "Overdue Invoice", "paid", False),
    ],
)
def test_compare_every_op(op, actual, expected, matches):
    assert automation_service._compare(actual, op, expected) is matches


def test_compare_none_actual_never_matches_any_op():
    """A field that resolves to None (context missing that value) never matches, whatever the op."""
    for op in automation_service.CONDITION_OPS:
        assert automation_service._compare(None, op, "whatever") is False


def test_compare_non_numeric_value_for_numeric_op_does_not_match():
    assert automation_service._compare("not-a-number", "gt", 5) is False


def test_evaluate_conditions_empty_list_always_matches():
    assert automation_service.evaluate_conditions([], {}) is True
    assert automation_service.evaluate_conditions(None, {}) is True


def test_evaluate_conditions_missing_field_in_context_never_matches():
    # payment_method resolves to None when there's no payment in context, for every op
    for op in automation_service.CONDITION_OPS:
        assert automation_service.evaluate_conditions([{"field": "payment_method", "op": op, "value": "upi"}], {}) is False


def test_evaluate_conditions_all_must_match_and():
    payment = Payment(amount=Decimal("500.00"), method=PaymentMethod.UPI)
    context = {"payment": payment}
    both_match = [
        {"field": "amount", "op": "eq", "value": "500.00"},
        {"field": "payment_method", "op": "eq", "value": "upi"},
    ]
    assert automation_service.evaluate_conditions(both_match, context) is True

    one_fails = [
        {"field": "amount", "op": "eq", "value": "500.00"},
        {"field": "payment_method", "op": "eq", "value": "card"},
    ]
    assert automation_service.evaluate_conditions(one_fails, context) is False


# --- 2. actions: real side effects ------------------------------------------------------------


def test_action_create_activity_creates_row_and_bumps_last_contact(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-5)
    rule = _make_rule(
        db, ctx, AutomationTrigger.INVOICE_OVERDUE,
        actions=[{"action": "create_activity", "params": {"activity_type": "phone_call", "note": "Automated call log"}}],
    )

    collection_before = collection_service.get_or_create_collection(db, org.id, invoice.id)
    assert collection_before.last_contact_at is None

    results = automation_service.execute_actions(db, rule, {"invoice": invoice, "customer": customer})
    db.commit()

    assert results == [{"action": "create_activity", "activity_id": results[0]["activity_id"]}]

    activity = db.scalars(select(CollectionActivity).where(CollectionActivity.invoice_id == invoice.id)).first()
    assert activity is not None
    assert activity.activity_type == CollectionActivityType.PHONE_CALL
    assert activity.note == "Automated call log"
    assert activity.customer_id == customer.id

    db.refresh(collection_before)
    assert collection_before.last_contact_at is not None


def test_action_create_activity_defaults_note_and_type_and_skips_without_invoice(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    rule = _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "create_activity", "params": {}}])

    results = automation_service.execute_actions(db, rule, {"customer": customer})
    db.commit()
    assert results == [{"action": "create_activity", "skipped": "no invoice in context"}]

    invoice = _make_invoice(db, ctx, customer, due_in_days=-5)
    results = automation_service.execute_actions(db, rule, {"invoice": invoice, "customer": customer})
    db.commit()
    activity = db.scalars(select(CollectionActivity).where(CollectionActivity.invoice_id == invoice.id)).first()
    assert activity.activity_type == CollectionActivityType.INTERNAL_NOTE
    assert rule.name in activity.note


def test_action_create_reminder_bumps_reminder_count(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-3)
    assert invoice.reminder_count == 0
    assert invoice.last_reminder_at is None

    rule = _make_rule(db, ctx, AutomationTrigger.INVOICE_OVERDUE, actions=[{"action": "create_reminder", "params": {}}])
    results = automation_service.execute_actions(db, rule, {"invoice": invoice, "customer": customer})
    db.commit()
    db.refresh(invoice)

    assert invoice.reminder_count == 1
    assert invoice.last_reminder_at is not None
    assert results[0]["action"] == "create_reminder"
    assert results[0]["reminder_count"] == 1


def test_action_create_reminder_skips_without_invoice(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    rule = _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "create_reminder", "params": {}}])
    results = automation_service.execute_actions(db, rule, {"customer": customer})
    db.commit()
    assert results == [{"action": "create_reminder", "skipped": "no open invoice in context"}]


def test_action_create_reminder_skips_when_invoice_not_open(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    draft_invoice = _make_invoice(db, ctx, customer, due_in_days=10, send=False)
    assert draft_invoice.status == InvoiceStatus.DRAFT

    rule = _make_rule(db, ctx, AutomationTrigger.INVOICE_CREATED, actions=[{"action": "create_reminder", "params": {}}])
    results = automation_service.execute_actions(db, rule, {"invoice": draft_invoice, "customer": customer})
    db.commit()
    assert results == [{"action": "create_reminder", "skipped": "no open invoice in context"}]
    db.refresh(draft_invoice)
    assert draft_invoice.reminder_count == 0


def test_action_send_email_does_not_raise_when_smtp_disabled(db: Session, org_ctx):
    """Test env has SMTP_HOST="" (email disabled); send_email must return False, never raise."""
    org, user, customer, ctx = org_ctx
    rule = _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "send_email", "params": {}}])

    results = automation_service.execute_actions(db, rule, {"customer": customer})
    db.commit()
    assert results == [{"action": "send_email", "sent": False, "to": customer.email}]


def test_action_send_email_skips_without_customer_or_email(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    rule = _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "send_email", "params": {}}])

    # no customer at all
    results = automation_service.execute_actions(db, rule, {})
    assert results == [{"action": "send_email", "skipped": "no customer email in context"}]

    # customer present but no email
    no_email_customer = Customer(organization_id=org.id, customer_number="CUST-NOEMAIL", display_name="No Email Co", email=None, currency="INR")
    results = automation_service.execute_actions(db, rule, {"customer": no_email_customer})
    assert results == [{"action": "send_email", "skipped": "no customer email in context"}]


def test_action_update_collection_status_sets_manual_status(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-5)
    rule = _make_rule(
        db, ctx, AutomationTrigger.INVOICE_OVERDUE, actions=[{"action": "update_collection_status", "params": {"status": "escalated"}}]
    )

    results = automation_service.execute_actions(db, rule, {"invoice": invoice})
    db.commit()

    collection = collection_service.get_or_create_collection(db, org.id, invoice.id)
    assert collection.manual_status == CollectionStatus.ESCALATED
    assert results == [{"action": "update_collection_status", "invoice_id": invoice.id, "status": "escalated"}]


def test_action_update_collection_status_rejects_collected(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-5)
    rule = _make_rule(
        db, ctx, AutomationTrigger.INVOICE_OVERDUE, actions=[{"action": "update_collection_status", "params": {"status": "collected"}}]
    )

    results = automation_service.execute_actions(db, rule, {"invoice": invoice})
    db.commit()

    assert results == [{"action": "update_collection_status", "skipped": "collected is set automatically, not by automation"}]
    collection = collection_service.get_or_create_collection(db, org.id, invoice.id)
    assert collection.manual_status is None


def test_action_update_collection_status_skips_without_invoice_or_bad_status(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    rule = _make_rule(
        db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "update_collection_status", "params": {"status": "escalated"}}]
    )
    results = automation_service.execute_actions(db, rule, {"customer": customer})
    assert results == [{"action": "update_collection_status", "skipped": "no invoice in context"}]

    invoice = _make_invoice(db, ctx, customer, due_in_days=-5)
    bad_rule = _make_rule(
        db, ctx, AutomationTrigger.INVOICE_OVERDUE, actions=[{"action": "update_collection_status", "params": {"status": "not_a_status"}}]
    )
    results = automation_service.execute_actions(db, bad_rule, {"invoice": invoice})
    assert results == [{"action": "update_collection_status", "skipped": "invalid status param"}]


def test_action_create_approval_task_creates_row(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-5)
    rule = _make_rule(db, ctx, AutomationTrigger.INVOICE_OVERDUE, actions=[{"action": "create_approval_task", "params": {"note": "please review"}}])

    results = automation_service.execute_actions(db, rule, {"invoice": invoice})
    db.commit()

    approval = db.scalars(select(ApprovalRequest).where(ApprovalRequest.organization_id == org.id)).first()
    assert approval is not None
    assert approval.entity_type == "invoice"
    assert approval.entity_id == invoice.id
    assert approval.requested_by_id is None
    assert approval.payload == {"automation_rule_id": rule.id}
    assert approval.justification == "please review"
    assert results == [{"action": "create_approval_task", "approval_id": approval.id}]


def test_action_create_approval_task_skips_without_entity(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    rule = _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "create_approval_task", "params": {}}])
    results = automation_service.execute_actions(db, rule, {"customer": customer})
    assert results == [{"action": "create_approval_task", "skipped": "no entity to attach the approval to"}]


def test_execute_actions_reports_unknown_action_without_raising(db: Session, org_ctx):
    """execute_actions() itself just records an error entry for an unknown action; it doesn't raise
    (that guard lives in _validate_actions at rule-creation time, not here)."""
    org, user, customer, ctx = org_ctx
    rule = _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "send_email", "params": {}}])
    rule.actions = [{"action": "totally_bogus_action"}]  # bypass _validate_actions directly on the model
    db.flush()

    results = automation_service.execute_actions(db, rule, {"customer": customer})
    assert results == [{"action": "totally_bogus_action", "error": "unknown action"}]


# --- 3. dispatch(): defensive, filters correctly ------------------------------------------------


def test_dispatch_writes_success_execution_with_result_per_action(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-2)
    _make_rule(
        db, ctx, AutomationTrigger.INVOICE_OVERDUE,
        actions=[{"action": "create_activity", "params": {}}, {"action": "send_email", "params": {}}],
    )

    automation_service.dispatch(db, AutomationTrigger.INVOICE_OVERDUE, org.id, {"invoice": invoice, "customer": customer})

    executions = db.scalars(select(AutomationExecution).where(AutomationExecution.organization_id == org.id)).all()
    assert len(executions) == 1
    execution = executions[0]
    assert execution.status == AutomationExecutionStatus.SUCCESS
    assert execution.error is None
    assert len(execution.result) == 2
    assert {r["action"] for r in execution.result} == {"create_activity", "send_email"}


def test_dispatch_catches_action_errors_logs_failed_execution_and_never_raises(db: Session, org_ctx, monkeypatch):
    org, user, customer, ctx = org_ctx
    rule = _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "create_activity", "params": {}}])

    def _boom(db, rule, context, params):
        raise RuntimeError("kaboom from a broken rule")

    monkeypatch.setitem(automation_service._ACTION_DISPATCH, "create_activity", _boom)

    # must not raise, even though the action handler blows up
    automation_service.dispatch(db, AutomationTrigger.CUSTOMER_CREATED, org.id, {"customer": customer})

    executions = db.scalars(select(AutomationExecution).where(AutomationExecution.organization_id == org.id)).all()
    assert len(executions) == 1
    execution = executions[0]
    assert execution.status == AutomationExecutionStatus.FAILED
    assert execution.rule_id == rule.id
    assert execution.error and "kaboom" in execution.error
    assert execution.result is None

    # the session is left usable (rollback was clean) — a follow-up write succeeds
    db.add(Customer(organization_id=org.id, customer_number="CUST-AFTER-BOOM", display_name="Still works", currency="INR"))
    db.commit()


def test_dispatch_only_fires_for_matching_trigger_and_organization(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    other_org = Organization(name="Other Org", slug=f"other-org-{uuid.uuid4().hex[:8]}", default_currency="INR")
    db.add(other_org)
    db.commit()
    db.refresh(other_org)

    _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "send_email", "params": {}}])

    # wrong trigger -> nothing fires
    automation_service.dispatch(db, AutomationTrigger.PAYMENT_RECEIVED, org.id, {"customer": customer})
    assert db.scalars(select(AutomationExecution).where(AutomationExecution.organization_id == org.id)).all() == []

    # right trigger, wrong org -> nothing fires (rule belongs to `org`, not `other_org`)
    automation_service.dispatch(db, AutomationTrigger.CUSTOMER_CREATED, other_org.id, {"customer": customer})
    assert db.scalars(select(AutomationExecution).where(AutomationExecution.organization_id == other_org.id)).all() == []

    # right trigger, right org -> fires exactly once
    automation_service.dispatch(db, AutomationTrigger.CUSTOMER_CREATED, org.id, {"customer": customer})
    rows = db.scalars(select(AutomationExecution).where(AutomationExecution.organization_id == org.id)).all()
    assert len(rows) == 1


def test_dispatch_skips_inactive_rules_with_no_execution_row_at_all(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    rule = _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "send_email", "params": {}}])
    automation_service.set_rule_active(db, ctx, rule, False)

    automation_service.dispatch(db, AutomationTrigger.CUSTOMER_CREATED, org.id, {"customer": customer})

    rows = db.scalars(select(AutomationExecution).where(AutomationExecution.organization_id == org.id)).all()
    assert rows == []  # not even a "skipped" row — inactive rules are filtered out of the query entirely


def test_dispatch_writes_no_execution_when_conditions_dont_match(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-2, amount="100.00")
    _make_rule(
        db, ctx, AutomationTrigger.INVOICE_OVERDUE,
        conditions=[{"field": "amount", "op": "gt", "value": 10000}],
        actions=[{"action": "send_email", "params": {}}],
    )

    automation_service.dispatch(db, AutomationTrigger.INVOICE_OVERDUE, org.id, {"invoice": invoice, "customer": customer})

    rows = db.scalars(select(AutomationExecution).where(AutomationExecution.organization_id == org.id)).all()
    assert rows == []


# --- 4. rule CRUD validation --------------------------------------------------------------------


def test_validate_actions_rejects_empty_list_and_unknown_action():
    with pytest.raises(ValidationAppError):
        automation_service._validate_actions([])
    with pytest.raises(ValidationAppError):
        automation_service._validate_actions([{"action": "delete_the_database"}])
    with pytest.raises(ValidationAppError):
        automation_service._validate_actions([{"params": {}}])  # missing 'action' key
    automation_service._validate_actions([{"action": "send_email"}])  # does not raise


def test_validate_conditions_rejects_malformed_condition_and_unknown_op():
    with pytest.raises(ValidationAppError):
        automation_service._validate_conditions([{"field": "amount", "op": "eq"}])  # missing value
    with pytest.raises(ValidationAppError):
        automation_service._validate_conditions([{"op": "eq", "value": 5}])  # missing field
    with pytest.raises(ValidationAppError):
        automation_service._validate_conditions([{"field": "amount", "value": 5}])  # missing op
    with pytest.raises(ValidationAppError):
        automation_service._validate_conditions([{"field": "amount", "op": "regex", "value": "x"}])  # unknown op
    automation_service._validate_conditions([{"field": "amount", "op": "gt", "value": 100}])  # does not raise


def test_create_rule_rejects_unknown_action_over_service(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    with pytest.raises(ValidationAppError):
        automation_service.create_rule(
            db, ctx, AutomationRuleIn(name="Bad", trigger=AutomationTrigger.CUSTOMER_CREATED, conditions=[], actions=[{"action": "hack_the_planet"}])
        )


# --- 5. RBAC over HTTP ---------------------------------------------------------------------------


def test_viewer_can_read_but_not_mutate(client, tenant, auth_headers):
    viewer_headers = tenant.headers_for_role(MemberRole.VIEWER)

    assert client.get(f"{BASE}/dashboard", headers=viewer_headers).status_code == 200
    assert client.get(f"{BASE}/rules", headers=viewer_headers).status_code == 200
    assert client.get(f"{BASE}/executions", headers=viewer_headers).status_code == 200

    body = {"name": "Viewer rule", "trigger": "customer_created", "conditions": [], "actions": [{"action": "send_email"}]}
    assert client.post(f"{BASE}/rules", json=body, headers=viewer_headers).status_code == 403

    create_resp = client.post(f"{BASE}/rules", json=body, headers=auth_headers)
    assert create_resp.status_code == 201, create_resp.text
    rule_id = create_resp.json()["id"]

    assert client.patch(f"{BASE}/rules/{rule_id}", json={"is_active": False}, headers=viewer_headers).status_code == 403
    assert client.delete(f"{BASE}/rules/{rule_id}", headers=viewer_headers).status_code == 403


def test_admin_can_create_toggle_and_delete_rules(client, tenant, auth_headers):
    admin_headers = tenant.headers_for_role(MemberRole.ADMIN)
    body = {"name": "Admin rule", "trigger": "invoice_overdue", "conditions": [], "actions": [{"action": "send_email"}]}

    create_resp = client.post(f"{BASE}/rules", json=body, headers=admin_headers)
    assert create_resp.status_code == 201, create_resp.text
    rule_id = create_resp.json()["id"]
    assert create_resp.json()["is_active"] is True

    toggle_resp = client.patch(f"{BASE}/rules/{rule_id}", json={"is_active": False}, headers=admin_headers)
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_active"] is False

    delete_resp = client.delete(f"{BASE}/rules/{rule_id}", headers=admin_headers)
    assert delete_resp.status_code == 204

    listing = client.get(f"{BASE}/rules", headers=admin_headers).json()
    assert all(item["id"] != rule_id for item in listing["items"])


def test_create_rule_validation_over_http(client, auth_headers):
    # empty actions -> pydantic min_length=1 rejects before hitting the service
    empty_actions = client.post(
        f"{BASE}/rules", json={"name": "No actions", "trigger": "customer_created", "conditions": [], "actions": []}, headers=auth_headers
    )
    assert empty_actions.status_code == 422

    # unknown action -> service-level ValidationAppError -> 422
    unknown_action = client.post(
        f"{BASE}/rules",
        json={"name": "Bad action", "trigger": "customer_created", "conditions": [], "actions": [{"action": "not_real"}]},
        headers=auth_headers,
    )
    assert unknown_action.status_code == 422
    assert unknown_action.json()["error"]["code"] == "VALIDATION_ERROR"

    # malformed condition -> service-level ValidationAppError -> 422
    bad_condition = client.post(
        f"{BASE}/rules",
        json={
            "name": "Bad condition",
            "trigger": "customer_created",
            "conditions": [{"field": "amount", "op": "gt"}],
            "actions": [{"action": "send_email"}],
        },
        headers=auth_headers,
    )
    assert bad_condition.status_code == 422


# --- 6. tenant isolation --------------------------------------------------------------------------


def test_tenant_isolation_over_http(client, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    body = {"name": "Org A rule", "trigger": "customer_created", "conditions": [], "actions": [{"action": "send_email"}]}
    create_resp = client.post(f"{BASE}/rules", json=body, headers=auth_headers)
    assert create_resp.status_code == 201
    rule_id = create_resp.json()["id"]

    other = Tenant(db, uuid.uuid4().hex[:8])
    other_headers = other.headers()

    assert client.patch(f"{BASE}/rules/{rule_id}", json={"is_active": False}, headers=other_headers).status_code == 404
    assert client.delete(f"{BASE}/rules/{rule_id}", headers=other_headers).status_code == 404

    other_listing = client.get(f"{BASE}/rules", headers=other_headers).json()
    assert all(item["id"] != rule_id for item in other_listing["items"])

    other_dashboard = client.get(f"{BASE}/dashboard", headers=other_headers).json()
    assert other_dashboard["active_rules"] == 0 and other_dashboard["paused_rules"] == 0 and other_dashboard["total_executions"] == 0

    # org A's own token still works
    own_listing = client.get(f"{BASE}/rules", headers=auth_headers).json()
    assert any(item["id"] == rule_id for item in own_listing["items"])


def test_tenant_isolation_direct_service(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    other_org = Organization(name="Other Org", slug=f"other-org-{uuid.uuid4().hex[:8]}", default_currency="INR")
    db.add(other_org)
    db.commit()
    db.refresh(other_org)

    rule = _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "send_email", "params": {}}])
    automation_service.dispatch(db, AutomationTrigger.CUSTOMER_CREATED, org.id, {"customer": customer})

    with pytest.raises(EntityNotFoundError):
        automation_service.get_rule(db, other_org.id, rule.id)

    page = automation_service.list_rules(db, other_org.id, _default_page())
    assert page.items == []

    exec_page = automation_service.list_executions(db, other_org.id, _default_page())
    assert exec_page.items == []

    dash = automation_service.dashboard(db, other_org.id)
    assert dash == {"active_rules": 0, "paused_rules": 0, "failed_executions": 0, "total_executions": 0, "success_rate": None}

    # org A's own data is untouched
    assert automation_service.get_rule(db, org.id, rule.id).id == rule.id
    assert len(automation_service.list_executions(db, org.id, _default_page()).items) == 1


# --- 7. dashboard aggregation -----------------------------------------------------------------------


def test_dashboard_active_and_paused_counts(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    assert automation_service.dashboard(db, org.id) == {
        "active_rules": 0, "paused_rules": 0, "failed_executions": 0, "total_executions": 0, "success_rate": None,
    }

    active_rule = _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "send_email", "params": {}}], name="Active")
    paused_rule = _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "send_email", "params": {}}], name="Paused")
    automation_service.set_rule_active(db, ctx, paused_rule, False)

    dash = automation_service.dashboard(db, org.id)
    assert dash["active_rules"] == 1
    assert dash["paused_rules"] == 1


def test_dashboard_success_rate_none_then_computed(db: Session, org_ctx, monkeypatch):
    org, user, customer, ctx = org_ctx
    _make_rule(db, ctx, AutomationTrigger.CUSTOMER_CREATED, actions=[{"action": "send_email", "params": {}}])
    assert automation_service.dashboard(db, org.id)["success_rate"] is None

    # one successful dispatch
    automation_service.dispatch(db, AutomationTrigger.CUSTOMER_CREATED, org.id, {"customer": customer})
    dash = automation_service.dashboard(db, org.id)
    assert dash["total_executions"] == 1
    assert dash["failed_executions"] == 0
    assert dash["success_rate"] == 100.0

    # force one failed dispatch
    def _boom(db, rule, context, params):
        raise RuntimeError("boom")

    monkeypatch.setitem(automation_service._ACTION_DISPATCH, "send_email", _boom)
    automation_service.dispatch(db, AutomationTrigger.CUSTOMER_CREATED, org.id, {"customer": customer})

    dash = automation_service.dashboard(db, org.id)
    assert dash["total_executions"] == 2
    assert dash["failed_executions"] == 1
    assert dash["success_rate"] == 50.0
