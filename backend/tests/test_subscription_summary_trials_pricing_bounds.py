"""QA regressions: Trial Center trial creation (B2), subscription summary KPIs (B3) and
pricing quantity bounds (B4)."""
from datetime import date, timedelta
from decimal import Decimal

from backend.app.models import Subscription, SubscriptionStatus


def _create(client, headers, customer_id, plan_id, **extra):
    res = client.post(
        "/api/v1/subscriptions",
        headers=headers,
        json={"customer_id": customer_id, "plan_id": plan_id, "quantity": 1, **extra},
    )
    assert res.status_code == 201, res.text
    return res.json()


# --- B2: Trial Center "New Trial" -----------------------------------------------------------------------------------


def test_explicit_trial_days_on_no_trial_plan_creates_trialing_and_lists_in_trial_center(client, tenant, auth_headers):
    customer = tenant.customer()
    _product, plan = tenant.product_with_plan(unit_amount="1200.00", trial_days=0)

    # What the Trial Center form sends: trial mode forces status=trialing + trial_days > 0.
    data = _create(
        client,
        auth_headers,
        customer.id,
        plan.id,
        status="trialing",
        trial_days=14,
        start_date=str(date.today()),
        generate_first_invoice=False,
    )
    assert data["status"] == "trialing"
    assert data["trial_start"] == str(date.today())
    assert data["trial_end"] == str(date.today() + timedelta(days=14))

    # The Trial Center lists subscriptions with status=trialing ...
    listed = client.get("/api/v1/subscriptions", headers=auth_headers, params={"status": "trialing"}).json()
    assert data["id"] in [s["id"] for s in listed["items"]]
    # ... and the trial service's own list carries a TrialPeriod row for it.
    trials = client.get("/api/v1/trials", headers=auth_headers).json()
    assert any(t["subscription_id"] == data["id"] for t in trials["items"])
    # ... and the summary's trial KPI counts it.
    summary = client.get("/api/v1/subscriptions/summary", headers=auth_headers).json()
    assert summary["trialing_count"] == 1


def test_trialing_status_without_trial_days_is_rejected(client, tenant, auth_headers):
    customer = tenant.customer()
    _product, plan = tenant.product_with_plan(trial_days=0)
    res = client.post(
        "/api/v1/subscriptions",
        headers=auth_headers,
        json={"customer_id": customer.id, "plan_id": plan.id, "status": "trialing", "trial_days": 0},
    )
    assert res.status_code == 422


# --- B3: subscription summary KPIs ----------------------------------------------------------------------------------


def test_subscription_summary_exposes_every_kpi_the_ui_reads(client, tenant, auth_headers, db):
    _product, plan = tenant.product_with_plan(unit_amount="1000.00", interval="monthly", trial_days=0)
    today = date.today()

    def make(**extra):
        # One customer per subscription: a customer may hold only one live sub per plan.
        customer = tenant.customer()
        return _create(client, auth_headers, customer.id, plan.id, start_date=str(today), **extra)["id"]

    renewing = make(trial_days=0)  # active, auto-renews
    not_renewing = make(trial_days=0, auto_renewal=False)  # active, ends in 3 days, no renewal
    cancelling = make(trial_days=0)  # active, cancel at period end (far out)
    trial_soon = make(trial_days=5)
    trial_later = make(trial_days=30)
    past_due = make(trial_days=0)
    draft = make(status="draft")
    pending = make(status="draft")

    def sub(sid):
        return db.get(Subscription, sid)

    sub(not_renewing).current_period_end = today + timedelta(days=3)
    sub(cancelling).cancel_at_period_end = True
    sub(cancelling).current_period_end = today + timedelta(days=30)
    sub(past_due).status = SubscriptionStatus.PAST_DUE
    sub(pending).status = SubscriptionStatus.PENDING_ACTIVATION
    db.commit()

    res = client.get("/api/v1/subscriptions/summary", headers=auth_headers)
    assert res.status_code == 200, res.text
    summary = res.json()

    assert summary["total_subscriptions"] == 8
    assert summary["active_count"] == 3
    assert summary["trialing_count"] == 2
    assert summary["past_due_count"] == 1
    assert summary["paused_count"] == 0
    assert summary["cancelled_count"] == 0
    # draft + pending_activation, matching what the list renders as drafts.
    assert summary["draft_count"] == 2
    assert summary["auto_renew_enabled_count"] == 1
    assert summary["expiring_soon_count"] == 1
    assert summary["trial_expiring_soon_count"] == 1

    mrr = Decimal(summary["total_mrr"])
    assert mrr > 0
    assert Decimal(summary["total_arr"]) == (mrr * 12).quantize(Decimal("0.01"))

    # The Draft tab lists both statuses so the tab count and the rows agree.
    drafts = client.get(
        "/api/v1/subscriptions", headers=auth_headers, params={"status": "draft,pending_activation"}
    ).json()
    assert {s["id"] for s in drafts["items"]} == {draft, pending}
    assert drafts["total"] == summary["draft_count"]
    # Unknown statuses in the list are still rejected.
    bad = client.get("/api/v1/subscriptions", headers=auth_headers, params={"status": "draft,bogus"})
    assert bad.status_code == 422
    assert renewing and trial_soon and trial_later


def test_subscription_summary_empty_org_has_zeroed_kpis(client, tenant, auth_headers):
    summary = client.get("/api/v1/subscriptions/summary", headers=auth_headers).json()
    assert summary["total_arr"] == "0.00"
    for key in (
        "past_due_count",
        "expiring_soon_count",
        "trial_expiring_soon_count",
        "auto_renew_enabled_count",
        "draft_count",
    ):
        assert summary[key] == 0


# --- B4: pricing quantity bounds ------------------------------------------------------------------------------------


def test_pricing_simulate_rejects_quantity_over_one_million(client, tenant):
    _product, plan = tenant.product_with_plan(unit_amount="1.00")
    res = client.post(
        "/api/v1/pricing/simulate",
        json={"plan_id": plan.id, "quantity": "187654446786545"},
        headers=tenant.headers(),
    )
    assert res.status_code == 422, res.text


def test_pricing_calculate_rejects_item_quantity_over_one_million(client, tenant):
    _product, plan = tenant.product_with_plan(unit_amount="1.00")
    res = client.post(
        "/api/v1/pricing/calculate",
        json={"items": [{"plan_id": plan.id, "quantity": "1000001"}]},
        headers=tenant.headers(),
    )
    assert res.status_code == 422, res.text
    assert "quantity" in res.text


def test_pricing_simulate_accepts_quantity_at_the_limit(client, tenant):
    _product, plan = tenant.product_with_plan(unit_amount="1.00")
    res = client.post(
        "/api/v1/pricing/simulate",
        json={"plan_id": plan.id, "quantity": "1000000"},
        headers=tenant.headers(),
    )
    assert res.status_code == 200, res.text
