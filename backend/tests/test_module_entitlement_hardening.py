"""Stage 0: optional product modules (core/modules.json) are enforced on every way in, not only on the
module's own API prefix.

An organization whose access is 'entitled' may use the base modules plus its
organization_entitlements rows. These tests cover the alternate routes that used to expose a module
it is not entitled to (device registry, customer sub-resources, dashboard KPIs, search, the Roomi chat
and AI queries, the customer portal), and the unattended work (scheduler, outbox, inbound webhook)
that used to run for such modules. 'Unrestricted' organizations (every organization that predates
entitlements, and self-service trials) keep every module.
"""
import hashlib
import hmac
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.app.core.config import settings
from backend.app.core.entitlements import module_for_path
from backend.app.core.tenant_context import system_context, tenant_context
from backend.app.models import (
    MemberRole,
    OrganizationStatus,
    Payment,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
)
from backend.app.models.customization import AutomationLog
from backend.app.models.expenses import Expense
from backend.app.models.projects import Project
from backend.app.models.subscription_access import OrganizationEntitlement
from backend.app.services import dashboard_service, org_access, org_lifecycle, outbox_processor
from backend.app.services.scheduler import run_billing_jobs
from backend.tests.test_org_suspension_policy import _portal_token
from backend.tests.test_scheduler_org_lifecycle import (  # noqa: F401 - pytest fixtures
    _assert_processed,
    _seed_due_work,
    _set_org,
    _state,
    gateway,
    outbox_seen,
)

API = "/api/v1"


def _entitle(db, tenant, modules):
    """Switch the tenant's organization to 'entitled' access with exactly these optional modules."""
    org = tenant.organization
    with tenant_context(org.id):
        for key in modules:
            db.add(OrganizationEntitlement(organization_id=org.id, module_key=key, source="platform"))
        org.module_access = "entitled"
        db.commit()


def _code(resp):
    return resp.json()["error"]["code"]


def _schedule_runs(db, org_id):
    with system_context():
        return db.scalar(select(func.count()).select_from(AutomationLog).where(
            AutomationLog.organization_id == org_id, AutomationLog.action_type == "schedule"))


# --- registry -------------------------------------------------------------------------------------


def test_alternate_routes_map_to_their_module():
    assert module_for_path("/customers/{customer_id}/subscriptions") == "subscriptions"
    for sub in ("portal-access", "portal-invite", "portal-reactivate", "portal-revoke"):
        assert module_for_path(f"/customers/{{customer_id}}/{sub}") == "customer_portal"
    assert module_for_path("/dashboard/quotes-summary") == "quotes"
    assert module_for_path("/dashboard/deals-summary") == "quotes"
    # Base and core routes are unchanged.
    assert module_for_path("/customers/{customer_id}") == "customers"
    assert module_for_path("/customers/{customer_id}/payments") == "customers"
    assert module_for_path("/dashboard/summary") is None
    assert module_for_path("/dashboard/catalog-summary") is None


def test_module_entitled_reads_current_database_state(db, tenant):
    org_id = tenant.organization.id
    assert org_access.module_entitled(db, org_id, "dunning") is True  # unrestricted
    assert org_access.module_entitled(db, org_id, "customers") is True  # base
    _entitle(db, tenant, ["quotes"])
    assert org_access.module_entitled(db, org_id, "quotes") is True
    assert org_access.module_entitled(db, org_id, "dunning") is False
    assert org_access.module_entitled(db, org_id, "customers") is True
    assert org_access.module_entitled(db, None, "dunning") is False
    assert org_access.module_entitled(db, str(uuid.uuid4()), "dunning") is False


# --- device registry ("platforms") ----------------------------------------------------------------


def test_devices_require_the_platforms_module(client, db, tenant):
    _entitle(db, tenant, [])
    for method, path in (("get", "/devices"), ("get", "/mobile/bootstrap")):
        r = getattr(client, method)(f"{API}{path}", headers=tenant.headers())
        assert r.status_code == 403 and _code(r) == "FEATURE_NOT_ENTITLED", (path, r.text)
    r = client.post(f"{API}/devices", headers=tenant.headers(), json={"platform": "android", "device_name": "Phone"})
    assert r.status_code in (403, 422)


def test_devices_work_when_entitled_and_for_unrestricted_orgs(client, db, tenant):
    assert client.get(f"{API}/devices", headers=tenant.headers()).status_code == 200  # unrestricted
    _entitle(db, tenant, ["platforms"])
    assert client.get(f"{API}/devices", headers=tenant.headers()).status_code == 200
    assert client.get(f"{API}/mobile/bootstrap", headers=tenant.headers()).status_code == 200


@pytest.mark.parametrize("status, code", [
    (OrganizationStatus.SUSPENDED, "ORGANIZATION_SUSPENDED"),
    (OrganizationStatus.DELETED, "ORGANIZATION_DELETED"),
])
def test_devices_follow_the_organization_lifecycle(client, db, tenant, status, code):
    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    _set_org(tenant.organization.id, status=status)
    r = client.get(f"{API}/devices", headers=viewer)
    assert r.status_code == 403 and _code(r) == code


# --- customer sub-resources -----------------------------------------------------------------------


def test_customer_subscriptions_and_portal_routes_need_their_modules(client, db, tenant):
    customer = tenant.customer()
    _entitle(db, tenant, [])
    base = f"{API}/customers/{customer.id}"
    assert client.get(base, headers=tenant.headers()).status_code == 200
    assert client.get(f"{base}/payments", headers=tenant.headers()).status_code == 200
    assert client.get(f"{base}/invoices", headers=tenant.headers()).status_code == 200
    for path in ("subscriptions", "portal-access"):
        r = client.get(f"{base}/{path}", headers=tenant.headers())
        assert r.status_code == 403 and _code(r) == "FEATURE_NOT_ENTITLED", (path, r.text)
    r = client.post(f"{base}/portal-invite", headers=tenant.headers(), json={})
    assert r.status_code == 403 and _code(r) == "FEATURE_NOT_ENTITLED"


def test_customer_sub_resources_open_when_entitled(client, db, tenant):
    customer = tenant.customer()
    _entitle(db, tenant, ["subscriptions", "customer_portal"])
    base = f"{API}/customers/{customer.id}"
    assert client.get(f"{base}/subscriptions", headers=tenant.headers()).status_code == 200
    assert client.get(f"{base}/portal-access", headers=tenant.headers()).status_code == 200


def test_viewer_role_still_cannot_invite_to_the_portal(client, db, tenant):
    customer = tenant.customer()
    _entitle(db, tenant, ["customer_portal"])
    r = client.post(f"{API}/customers/{customer.id}/portal-invite", headers=tenant.headers_for_role(MemberRole.VIEWER),
                    json={})
    assert r.status_code == 403 and _code(r) != "FEATURE_NOT_ENTITLED"


# --- dashboard ------------------------------------------------------------------------------------


def test_quote_and_deal_kpis_need_the_quotes_module(client, db, tenant):
    for path in ("/dashboard/quotes-summary", "/dashboard/deals-summary"):
        assert client.get(f"{API}{path}", headers=tenant.headers()).status_code == 200  # unrestricted
    _entitle(db, tenant, [])
    for path in ("/dashboard/quotes-summary", "/dashboard/deals-summary"):
        r = client.get(f"{API}{path}", headers=tenant.headers())
        assert r.status_code == 403 and _code(r) == "FEATURE_NOT_ENTITLED"
    assert client.get(f"{API}/dashboard/catalog-summary", headers=tenant.headers()).status_code == 200  # base


def _fake_summary(real):
    def fake(db, organization, range_key="30_days"):
        data = real(db, organization, range_key)
        data["revenue"].update(mrr="1234.00", arr="14808.00", mrr_other_currencies={"USD": "10.00"})
        data["customer_health"].update(active=7, trialing=2)
        return data
    return fake


def test_overview_hides_subscription_figures_without_the_module(client, db, tenant, monkeypatch):
    monkeypatch.setattr(dashboard_service, "dashboard_summary", _fake_summary(dashboard_service.dashboard_summary))
    full = client.get(f"{API}/dashboard/summary", headers=tenant.headers()).json()
    assert full["revenue"]["mrr"] == "1234.00" and full["customer_health"]["active"] == 7

    _entitle(db, tenant, [])
    hidden = client.get(f"{API}/dashboard/summary", headers=tenant.headers()).json()
    assert hidden["revenue"]["mrr"] == "0.00" and hidden["revenue"]["arr"] == "0.00"
    assert hidden["revenue"]["mrr_other_currencies"] == {}
    assert hidden["customer_health"]["active"] == 0 and hidden["customer_health"]["trialing"] == 0
    # Base-module figures are untouched.
    assert hidden["metrics"] == full["metrics"] and hidden["pipeline"] == full["pipeline"]


def test_financial_summary_hides_subscription_and_quote_blocks(client, db, tenant):
    _entitle(db, tenant, ["quotes"])
    body = client.get(f"{API}/dashboard/financial-summary", headers=tenant.headers())
    assert body.status_code == 200, body.text
    data = body.json()
    assert data["subscriptions"] == {"total_count": 0, "by_status": {}}
    assert data["mrr"]["mrr"] == "0.00" and data["mrr"]["subscription_count"] == 0
    assert "quotes" in data and "invoices" in data and "customers" in data


def _items(*categories):
    return [{"id": f"id-{c}", "category": c, "title": c, "description": c, "amount": None, "customer": None,
             "entity_type": "x", "entity_id": f"e-{c}", "due_info": "", "urgency": "high",
             "suggested_action": "send_reminder"} for c in categories]


def test_action_center_and_calendar_drop_items_of_unentitled_modules(client, db, tenant, monkeypatch):
    monkeypatch.setattr(dashboard_service, "action_center", lambda db, org_id: {
        "items": _items("overdue", "expiring_trial", "pending_quote", "pending_approval"),
        "counts": {"overdue": 1, "failed_payment": 0, "expiring_trial": 1, "pending_quote": 1, "pending_approval": 1},
    })
    events = [{"id": f"ev-{t}", "date": date.today().isoformat(), "type": t, "title": t, "customer": None,
               "amount": None, "entity_type": "x", "entity_id": f"e-{t}", "status": "open"}
              for t in ("invoice_due", "subscription_renewal", "trial_ending", "quote_expiry")]
    monkeypatch.setattr(dashboard_service, "calendar_events",
                        lambda db, org_id, month: {"month": date.today().strftime("%Y-%m"), "events": list(events)})

    full = client.get(f"{API}/action-center", headers=tenant.headers()).json()
    assert {i["category"] for i in full["items"]} == {"overdue", "expiring_trial", "pending_quote", "pending_approval"}

    _entitle(db, tenant, ["quotes"])
    ac = client.get(f"{API}/action-center", headers=tenant.headers()).json()
    assert {i["category"] for i in ac["items"]} == {"overdue", "pending_quote", "pending_approval"}
    assert ac["counts"]["expiring_trial"] == 0 and ac["counts"]["pending_quote"] == 1
    cal = client.get(f"{API}/calendar", headers=tenant.headers()).json()
    assert {e["type"] for e in cal["events"]} == {"invoice_due", "quote_expiry"}


# --- search ---------------------------------------------------------------------------------------


def test_search_leaves_out_results_of_unentitled_modules(client, db, tenant):
    token = f"zq{uuid.uuid4().hex[:6]}"
    customer = tenant.customer(display_name=f"Acme {token}")
    with tenant_context(tenant.organization.id):
        db.add(Project(organization_id=tenant.organization.id, name=f"Website {token}", customer_name=customer.display_name))
        db.add(Expense(organization_id=tenant.organization.id, name=f"Taxi {token}", date=date.today(),
                       category="Travel", amount=Decimal("10.00")))
        db.commit()

    def categories():
        r = client.get(f"{API}/search", params={"q": token}, headers=tenant.headers())
        assert r.status_code == 200, r.text
        return {i["category"] for i in r.json()["results"]}

    assert categories() == {"customers", "projects", "expenses"}  # unrestricted
    _entitle(db, tenant, ["projects"])
    assert categories() == {"customers", "projects"}


def test_search_never_returns_another_organizations_rows(client, db, tenant):
    from backend.tests.conftest import Tenant

    token = f"zx{uuid.uuid4().hex[:6]}"
    other = Tenant(db, uuid.uuid4().hex[:8])
    other.customer(display_name=f"Other {token}")
    r = client.get(f"{API}/search", params={"q": token}, headers=tenant.headers())
    assert r.status_code == 200 and r.json()["results"] == []


# --- Roomi chat and AI queries --------------------------------------------------------------------


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None, raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def _chat(client, tenant, message):
    r = client.post(f"{API}/chat/roomi", headers=tenant.headers(), json={"message": message})
    assert r.status_code == 200, r.text
    return r.json()


def test_roomi_reports_module_data_only_when_entitled(client, db, tenant, no_llm):
    assert "active_subscriptions" in (_chat(client, tenant, "how many subscriptions do I have")["data"] or {})
    assert "mrr" in _chat(client, tenant, "what is our revenue")["data"]

    _entitle(db, tenant, [])
    subs = _chat(client, tenant, "how many subscriptions do I have")
    assert "active_subscriptions" not in (subs["data"] or {})
    assert "active_subscription_count" not in (subs["data"] or {})
    revenue = _chat(client, tenant, "what is our revenue")
    assert "mrr" not in (revenue["data"] or {}) and "MRR" not in revenue["reply"]
    for message, key in (("show my expenses", "expense_total"), ("show my projects", "project_count")):
        assert key not in (_chat(client, tenant, message)["data"] or {})


def test_roomi_still_answers_base_module_questions(client, db, tenant, no_llm):
    _entitle(db, tenant, [])
    body = _chat(client, tenant, "what is our revenue")
    assert "total_collected" in body["data"]


def test_ai_query_mrr_needs_the_subscriptions_module(client, db, tenant):
    _entitle(db, tenant, ["ai_billing"])
    r = client.post(f"{API}/ai/queries", headers=tenant.headers(), json={"prompt": "What is our MRR?"})
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {} and "not included" in r.json()["answer"]
    # Base-module questions keep working.
    r = client.post(f"{API}/ai/queries", headers=tenant.headers(), json={"prompt": "What is our outstanding balance?"})
    assert r.status_code == 200 and r.json()["data"] != {}


def test_ai_query_mrr_answers_when_subscriptions_entitled(client, db, tenant):
    _entitle(db, tenant, ["ai_billing", "subscriptions"])
    r = client.post(f"{API}/ai/queries", headers=tenant.headers(), json={"prompt": "What is our MRR?"})
    assert r.status_code == 200 and "mrr" in r.json()["data"]


# --- customer portal ------------------------------------------------------------------------------


def test_portal_sessions_need_the_merchants_portal_module(client, db, tenant):
    token = _portal_token(client, db, tenant)
    headers = {"X-Portal-Token": token}
    assert client.get(f"{API}/portal/dashboard", headers=headers).status_code == 200  # unrestricted
    _entitle(db, tenant, [])
    r = client.get(f"{API}/portal/dashboard", headers=headers)
    assert r.status_code == 403 and _code(r) == "ORGANIZATION_UNAVAILABLE"


def test_portal_works_for_entitled_merchant(client, db, tenant):
    token = _portal_token(client, db, tenant)
    _entitle(db, tenant, ["customer_portal"])
    assert client.get(f"{API}/portal/dashboard", headers={"X-Portal-Token": token}).status_code == 200


# --- unattended work ------------------------------------------------------------------------------


def test_automation_guard_checks_the_module(db, tenant):
    org_id = tenant.organization.id
    assert org_lifecycle.AutomationGuard(db, org_id, module="dunning")() is True
    _entitle(db, tenant, ["expenses"])
    dunning = org_lifecycle.AutomationGuard(db, org_id, module="dunning")
    assert dunning() is False and dunning.refused == 1
    assert org_lifecycle.AutomationGuard(db, org_id, module="expenses")() is True
    assert org_lifecycle.AutomationGuard(db, org_id)() is True  # no module: lifecycle only, as before


def test_scheduler_skips_optional_module_work_but_keeps_base_work(db, tenant, gateway, outbox_seen):
    ids = _seed_due_work(db, tenant)
    _entitle(db, tenant, [])
    runs_before = _schedule_runs(db, tenant.organization.id)
    before = _state(db, ids)

    run_billing_jobs(db)

    after = _state(db, ids)
    assert after["trial_status"] == SubscriptionStatus.TRIALING  # subscriptions: no trial conversion
    assert after["renewal_invoices"] == 0 and after["renewal_next_billing"] == before["renewal_next_billing"]
    assert after["dunning_charged"] is False and after["dunning_attempts"] == before["dunning_attempts"]
    assert after["expenses"] == 0  # no recurring expense
    assert _schedule_runs(db, tenant.organization.id) == runs_before  # automation schedule not executed
    # Base work (invoices) and plain outbox delivery are unchanged.
    assert after["overdue_status"].value == "overdue"
    assert after["reminders"] == 1
    assert after["outbox_status"].value == "published"


def test_scheduler_runs_everything_for_an_entitled_org(db, tenant, gateway, outbox_seen):
    ids = _seed_due_work(db, tenant)
    _entitle(db, tenant, ["subscriptions", "dunning", "expenses", "automation"])
    run_billing_jobs(db)
    _assert_processed(_state(db, ids))


def test_outbox_runs_automation_and_webhooks_only_for_entitled_modules(db, tenant, monkeypatch):
    from backend.app.models.events import OutboxEvent
    from backend.app.services import customization_service

    calls = []
    monkeypatch.setattr(customization_service, "process_outbox_event_automation",
                        lambda *a, **k: calls.append("automation"))
    monkeypatch.setattr(customization_service, "enqueue_subscribed_webhooks", lambda *a, **k: calls.append("webhooks"))
    event = OutboxEvent(organization_id=tenant.organization.id, event_type="invoice.created", aggregate_type="invoice",
                        aggregate_id="inv-1", payload={})

    outbox_processor._handle_domain_event(db, event)
    assert calls == ["automation", "webhooks"]  # unrestricted

    calls.clear()
    _entitle(db, tenant, ["integrations"])
    outbox_processor._handle_domain_event(db, event)
    assert calls == ["webhooks"]

    calls.clear()
    with tenant_context(tenant.organization.id):
        db.query(OrganizationEntitlement).filter(OrganizationEntitlement.organization_id == tenant.organization.id).delete()
        db.commit()
    outbox_processor._handle_domain_event(db, event)
    assert calls == []


def _failed_payment_webhook(client, db, tenant, monkeypatch):
    """A payment.failed event for a subscription invoice. Returns (response, payment id, trigger calls)."""
    from backend.app.services import dunning_service

    secret = "hardening_webhook_secret"
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", secret)
    triggered = []
    monkeypatch.setattr(dunning_service, "trigger_dunning_for_failed_payment", lambda *a, **kw: triggered.append(kw))
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="900.00")
    today = date.today()
    with system_context():
        sub = Subscription(
            organization_id=tenant.organization.id, customer_id=customer.id, plan_id=plan.id, quantity=1,
            status=SubscriptionStatus.ACTIVE, start_date=today, current_period_start=today,
            current_period_end=today + timedelta(days=30), subscription_number=f"SUB-H-{uuid.uuid4().hex[:6]}",
        )
        db.add(sub)
        db.commit()
    inv = tenant.invoice(customer, amount="900.00")
    with system_context():
        inv.subscription_id = sub.id
        payment = Payment(
            organization_id=tenant.organization.id, payment_number=f"PAY-{uuid.uuid4().hex[:8].upper()}",
            customer_id=customer.id, amount=Decimal("900.00"), currency="INR", method=PaymentMethod.RAZORPAY,
            gateway=PaymentGateway.RAZORPAY, status=PaymentStatus.PENDING, gateway_order_id=f"order_{uuid.uuid4().hex[:14]}",
            gateway_payload={"notes": {"invoice_id": inv.id, "organization_id": tenant.organization.id}},
        )
        db.add(payment)
        db.commit()
    body = json.dumps({"event": "payment.failed", "payload": {"payment": {"entity": {
        "id": f"pay_{uuid.uuid4().hex[:12]}", "order_id": payment.gateway_order_id, "amount": 90000, "currency": "INR",
        "error_description": "Card declined", "method": "card"}}}}).encode()
    headers = {"Content-Type": "application/json", "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex}",
               "X-Razorpay-Signature": hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}
    return client.post(f"{API}/webhooks/razorpay", content=body, headers=headers), payment.id, triggered


def test_failed_payment_webhook_opens_no_dunning_case_without_the_module(client, db, tenant, monkeypatch):
    _entitle(db, tenant, ["subscriptions"])
    resp, payment_id, triggered = _failed_payment_webhook(client, db, tenant, monkeypatch)
    assert resp.status_code == 200, resp.text
    assert triggered == []
    db.expire_all()
    with system_context():
        assert db.get(Payment, payment_id).status == PaymentStatus.FAILED  # the failure itself is recorded


def test_failed_payment_webhook_opens_dunning_case_when_entitled(client, db, tenant, monkeypatch):
    _entitle(db, tenant, ["subscriptions", "dunning"])
    resp, _, triggered = _failed_payment_webhook(client, db, tenant, monkeypatch)
    assert resp.status_code == 200, resp.text
    assert len(triggered) == 1 and triggered[0]["organization_id"] == tenant.organization.id
