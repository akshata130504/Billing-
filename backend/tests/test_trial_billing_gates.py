"""No real money moves while an organization is in its free trial (running or ended).

A self-service organization is ACTIVE with organizations.module_access 'trial' until a Platform
Administrator approves its subscription request ('entitled'). During that time its users create
normal billing data (customers, products, quotes, invoices) and their customers can still accept or
decline quotes, but nothing collects money: no scheduler billing work (renewals, trial-conversion
charges, dunning, reminders, overdue marking, recurring expenses), no outbox / automation delivery,
no customer payment links or hosted-checkout orders, no portal conversion charge, no manual dunning
retry and no charge on a manual trial conversion. With an approved subscription everything works as
before; organizations that predate plans ('unrestricted') are unaffected (test_scheduler_org_lifecycle).
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from backend.app.core.tenant_context import system_context, tenant_context
from backend.app.models import Organization, Subscription, SubscriptionStatus, utcnow
from backend.app.models.subscription_access import OrganizationEntitlement
from backend.app.services import org_lifecycle, trial_service
from backend.app.services.scheduler import run_billing_jobs
from backend.tests.test_org_suspension_policy import _code, _portal_token, _sent_invoice_token
from backend.tests.test_scheduler_org_lifecycle import (  # noqa: F401 - pytest fixtures
    _assert_processed,
    _assert_untouched,
    _charged_customers,
    _seed_due_work,
    _state,
    gateway,
    outbox_seen,
)

API = "/api/v1"
TRIAL_PHASES = {"trial": timedelta(days=2), "trial_ended": timedelta(days=-1)}


def _set_access(db, org_id: str, module_access: str, *, ends_in: timedelta = timedelta(days=2), modules=()) -> None:
    with system_context():
        org = db.get(Organization, org_id)
        org.module_access = module_access
        org.trial_started_at = utcnow() - timedelta(days=3) + ends_in
        org.trial_ends_at = utcnow() + ends_in
        db.commit()
    if modules:
        with tenant_context(org_id):
            for key in modules:
                db.add(OrganizationEntitlement(organization_id=org_id, module_key=key, source="platform"))
            db.commit()


# --- gate --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("phase", TRIAL_PHASES)
def test_gates_refuse_trial_phases(db, tenant, phase):
    _set_access(db, tenant.organization.id, "trial", ends_in=TRIAL_PHASES[phase])
    org_id = tenant.organization.id
    assert org_lifecycle.automation_allowed(db, org_id) is False
    assert org_lifecycle.billing_collection_allowed(db, org_id) is False
    assert org_lifecycle.payment_collection_allowed(db, org_id) is False
    assert org_lifecycle.customer_actions_allowed(db, org_id) is True  # quote accept / decline still work
    ids = set(db.scalars(org_lifecycle.automation_allowed_org_ids()).all())
    assert org_id not in ids


def test_gates_allow_an_approved_subscription(db, tenant):
    _set_access(db, tenant.organization.id, "entitled", modules=("dunning",))
    org_id = tenant.organization.id
    assert org_lifecycle.automation_allowed(db, org_id) is True
    assert org_lifecycle.billing_collection_allowed(db, org_id) is True
    assert org_lifecycle.payment_collection_allowed(db, org_id) is True
    assert org_id in set(db.scalars(org_lifecycle.automation_allowed_org_ids()).all())


# --- scheduler / outbox / automation ---------------------------------------------------------------


@pytest.mark.parametrize("phase", TRIAL_PHASES)
def test_scheduler_starts_no_billing_work_in_trial(db, tenant, gateway, outbox_seen, phase):
    ids = _seed_due_work(db, tenant)
    _set_access(db, tenant.organization.id, "trial", ends_in=TRIAL_PHASES[phase])
    before = _state(db, ids)

    counts = run_billing_jobs(db, today=date.today())

    # Only this organization's work is asserted: the run's counters and the fake gateway are
    # run-wide, and other tests' organizations in the same database may have due work of their own.
    _assert_untouched(before, _state(db, ids), ids)  # no renewal, charge, dunning, reminder, outbox, schedule
    assert not ({ids["trial_customer"], ids["dunning_customer"]} & _charged_customers(gateway))
    assert ids["outbox_event"] not in outbox_seen
    assert counts["skipped_org_inactive"] >= 1


def test_scheduler_runs_everything_with_an_approved_subscription(db, tenant, gateway, outbox_seen):
    ids = _seed_due_work(db, tenant)
    _set_access(db, tenant.organization.id, "entitled")

    counts = run_billing_jobs(db, today=date.today())

    _assert_processed(_state(db, ids))
    assert {ids["trial_customer"], ids["dunning_customer"]} <= _charged_customers(gateway)
    assert ids["outbox_event"] in outbox_seen
    assert counts["errors"] == 0


def test_queued_work_runs_once_the_subscription_is_approved(db, tenant, gateway, outbox_seen):
    ids = _seed_due_work(db, tenant)
    _set_access(db, tenant.organization.id, "trial")
    run_billing_jobs(db, today=date.today())
    assert not ({ids["trial_customer"], ids["dunning_customer"]} & _charged_customers(gateway))
    assert ids["outbox_event"] not in outbox_seen
    _set_access(db, tenant.organization.id, "entitled")
    run_billing_jobs(db, today=date.today())
    _assert_processed(_state(db, ids))


# --- tenant-initiated money movement ---------------------------------------------------------------


def test_manual_dunning_retry_refused_in_trial_allowed_when_paid(client, db, tenant, gateway):
    ids = _seed_due_work(db, tenant)
    _set_access(db, tenant.organization.id, "trial")
    r = client.post(f"{API}/dunning/cases/{ids['dunning_case']}/retry-now", headers=tenant.headers())
    assert r.status_code == 403 and _code(r) == "BILLING_COLLECTION_NOT_ACTIVE"
    assert ids["dunning_customer"] not in _charged_customers(gateway)

    _set_access(db, tenant.organization.id, "entitled", modules=("dunning",))
    r = client.post(f"{API}/dunning/cases/{ids['dunning_case']}/retry-now", headers=tenant.headers())
    assert r.status_code == 200, r.text
    assert ids["dunning_customer"] in _charged_customers(gateway)


@pytest.mark.parametrize("access, charged", [("trial", False), ("entitled", True)])
def test_manual_trial_conversion_charges_only_with_a_paid_subscription(db, tenant, gateway, access, charged):
    ids = _seed_due_work(db, tenant)
    _set_access(db, tenant.organization.id, access)
    with tenant_context(tenant.organization.id):
        sub = db.get(Subscription, ids["trial_sub"])
        converted, invoice, _attempt, _ok, _msg = trial_service.convert_trial_to_live(db, sub)
        db.commit()
        assert converted.status == SubscriptionStatus.ACTIVE  # the conversion itself always works
        assert invoice is not None
    assert (ids["trial_customer"] in _charged_customers(gateway)) is charged
    if not charged:
        with tenant_context(tenant.organization.id):
            db.refresh(invoice)
            assert invoice.amount_due > 0  # stays unpaid


# --- customer-facing ---------------------------------------------------------------------------------


def test_payment_links_closed_in_trial_open_when_paid(client, db, tenant):
    _set_access(db, tenant.organization.id, "trial")
    token = _sent_invoice_token(client, tenant)  # creating and sending invoices works in the trial

    view = client.get(f"{API}/public/invoices/{token}")
    assert view.status_code == 200, view.text  # the customer can still see the invoice
    assert view.json()["razorpay"]["enabled"] is False
    assert view.json()["razorpay"]["unavailable_reason"]
    order = client.post(f"{API}/public/invoices/{token}/razorpay-order", json={})
    assert order.status_code == 403 and _code(order) == "ORGANIZATION_UNAVAILABLE"
    assert "not accepting online payments" in order.json()["error"]["message"]

    _set_access(db, tenant.organization.id, "entitled")
    assert client.get(f"{API}/public/invoices/{token}").json()["razorpay"].get("unavailable_reason") is None


def test_portal_trial_conversion_refused_in_trial(client, db, tenant):
    token = _portal_token(client, db, tenant)
    _set_access(db, tenant.organization.id, "trial")
    r = client.post(f"{API}/portal/subscriptions/any-subscription/trial/convert", headers={"X-Portal-Token": token}, json={})
    assert r.status_code == 403 and _code(r) == "ORGANIZATION_UNAVAILABLE"
    # Non-payment portal actions keep working during the trial.
    profile = client.patch(f"{API}/portal/profile", headers={"X-Portal-Token": token}, json={"display_name": "Trial Customer"})
    assert profile.status_code == 200, profile.text


def test_trial_users_create_billing_data_and_customers_accept_quotes(client, db, tenant):
    _set_access(db, tenant.organization.id, "trial")
    customer = tenant.customer()
    created = client.post(
        f"{API}/quotes", headers=tenant.headers(),
        json={"customer_id": customer.id, "title": "Trial rollout",
              "items": [{"description": "Impl", "quantity": "1", "unit_price": "1000.00", "tax_rate_pct": "18"}]},
    )
    assert created.status_code == 201, created.text
    sent = client.post(f"{API}/quotes/{created.json()['id']}/send", headers=tenant.headers())
    assert sent.status_code == 200, sent.text
    token = sent.json()["public_url"].rsplit("/", 1)[1]
    assert client.get(f"{API}/public/quotes/{token}").json()["actions_unavailable_reason"] is None
    accept = client.post(f"{API}/public/quotes/{token}/accept", json={"accepted_by_name": "Jane Buyer"})
    assert accept.status_code == 200, accept.text
    assert client.post(f"{API}/customers", headers=tenant.headers(),
                       json={"display_name": "Trial Customer Co", "email": "t@example.test"}).status_code == 201
    with system_context():
        assert db.scalar(select(Organization.status).where(Organization.id == tenant.organization.id)).value == "active"
