"""Production QA 2026-10-09 subscription lifecycle fixes.

BUG-45: the record says whether a manual renewal is due (the Renew button follows it).
BUG-55: an ended subscription reports mrr 0 and auto_renewal false.
BUG-56: early trial conversion moves trial_end to the conversion date; the
        auto-renew counter counts active subscriptions that will renew.
"""
from datetime import date

from backend.app.models import Subscription, TrialPeriod
from backend.app.services.subscription_service import renew_subscription

SUBS = "/api/v1/subscriptions"


def _create(client, headers, customer, plan, **extra):
    res = client.post(SUBS, headers=headers, json={"customer_id": customer.id, "plan_id": plan.id, "quantity": 1, **extra})
    assert res.status_code == 201, res.text
    return res.json()


def test_renewal_due_flag_matches_the_renew_endpoint(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="500.00")
    body = _create(client, auth_headers, customer, plan)
    assert body["renewal_due"] is False
    assert client.post(f"{SUBS}/{body['id']}/renew", headers=auth_headers).status_code == 409

    sub = db.get(Subscription, body["id"])
    sub.next_billing_date = date.today()
    db.commit()
    detail = client.get(f"{SUBS}/{body['id']}", headers=auth_headers).json()
    assert detail["renewal_due"] is True
    renewed = client.post(f"{SUBS}/{body['id']}/renew", headers=auth_headers)
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["renewal_due"] is False


def test_immediate_cancellation_zeroes_mrr_and_auto_renewal(client, tenant, auth_headers):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="500.00")
    body = _create(client, auth_headers, customer, plan)
    assert body["mrr"] != "0.00" and body["auto_renewal"] is True

    res = client.post(f"{SUBS}/{body['id']}/cancel", headers=auth_headers, json={"at_period_end": False})
    assert res.status_code == 200, res.text
    cancelled = client.get(f"{SUBS}/{body['id']}", headers=auth_headers).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["mrr"] == "0.00"
    assert cancelled["auto_renewal"] is False


def test_period_end_cancellation_keeps_mrr_until_the_period_ends(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="500.00")
    body = _create(client, auth_headers, customer, plan)
    res = client.post(f"{SUBS}/{body['id']}/cancel", headers=auth_headers, json={"at_period_end": True})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "active"
    assert res.json()["mrr"] == body["mrr"]  # still billed for the current period

    sub = db.get(Subscription, body["id"])
    sub.next_billing_date = date.today()
    db.commit()
    assert renew_subscription(db, sub, only_if_due=True) == "ended"
    db.commit()
    ended = client.get(f"{SUBS}/{body['id']}", headers=auth_headers).json()
    assert ended["status"] == "cancelled"
    assert ended["mrr"] == "0.00"
    assert ended["auto_renewal"] is False


def test_early_trial_conversion_ends_the_trial_today(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1000.00", trial_days=7)
    body = _create(client, auth_headers, customer, plan, start_date=str(date.today()))
    assert body["status"] == "trialing"
    assert date.fromisoformat(body["trial_end"]) > date.today()

    conv = client.post(f"/api/v1/trials/{body['id']}/convert", headers=auth_headers, json={"generate_first_invoice": True})
    assert conv.status_code == 200, conv.text
    detail = client.get(f"{SUBS}/{body['id']}", headers=auth_headers).json()
    assert detail["status"] == "active"
    today = date.fromisoformat(detail["current_period_start"])  # organization-local conversion date
    assert date.fromisoformat(detail["trial_end"]) == today
    db.expire_all()
    tp = db.query(TrialPeriod).filter(TrialPeriod.subscription_id == body["id"]).one()
    assert tp.trial_end_date == today


def test_auto_renew_counter_counts_active_subscriptions_that_will_renew(client, tenant, auth_headers):
    """The production observation (0 with auto_renewal true) was one trialing subscription and
    one active subscription set to cancel at period end: neither will auto-renew."""
    _, plan = tenant.product_with_plan(unit_amount="500.00")
    _, trial_plan = tenant.product_with_plan(unit_amount="500.00", trial_days=7)
    renewing = _create(client, auth_headers, tenant.customer(), plan)
    cancelling = _create(client, auth_headers, tenant.customer(), plan)
    client.post(f"{SUBS}/{cancelling['id']}/cancel", headers=auth_headers, json={"at_period_end": True})
    trial = _create(client, auth_headers, tenant.customer(), trial_plan, start_date=str(date.today()))
    assert trial["status"] == "trialing" and trial["auto_renewal"] is True

    summary = client.get(f"{SUBS}/summary", headers=auth_headers).json()
    assert summary["active_count"] == 2
    assert summary["auto_renew_enabled_count"] == 1
    assert renewing["auto_renewal"] is True

    client.post(f"/api/v1/trials/{trial['id']}/convert", headers=auth_headers, json={"generate_first_invoice": False})
    assert client.get(f"{SUBS}/summary", headers=auth_headers).json()["auto_renew_enabled_count"] == 2
