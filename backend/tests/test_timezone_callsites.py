"""Business-day call sites follow the organization's timezone (storage stays UTC).

The clock is frozen at 2026-03-31 20:00 UTC == 2026-04-01 01:30 IST == 2026-03-31 16:00 EDT,
so an Asia/Kolkata organization is already on 1 April while a New York one is still on
31 March. Every scenario asserts both sides of that split.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.app.models import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    Quote,
    QuoteStatus,
    ReconciliationStatus,
    Subscription,
    SubscriptionStatus,
)
from backend.app.services import invoice_service, quote_service, reports_service, scheduler, timezones

UTC = timezone.utc
FROZEN = datetime(2026, 3, 31, 20, 0, tzinfo=UTC)
KOLKATA = "Asia/Kolkata"
NEW_YORK = "America/New_York"


@pytest.fixture()
def frozen(monkeypatch):
    def _freeze(at: datetime = FROZEN):
        monkeypatch.setattr(timezones, "utc_now", lambda: at)
        return at

    _freeze()
    return _freeze


def _tenant(db, tz_name):
    from backend.tests.conftest import Tenant

    t = Tenant(db, uuid.uuid4().hex[:8])
    t.organization.timezone = tz_name
    db.commit()
    return t


def _open_invoice(db, tenant, due):
    inv = Invoice(
        organization_id=tenant.organization.id,
        customer_id=tenant.customer().id,
        invoice_number=f"INV-TZC-{uuid.uuid4().hex[:6]}",
        status=InvoiceStatus.SENT,
        issue_date=due - timedelta(days=30),
        due_date=due,
        subtotal=Decimal("100.00"),
        total=Decimal("100.00"),
        amount_paid=Decimal("0.00"),
        amount_due=Decimal("100.00"),
        public_token=uuid.uuid4().hex,
    )
    db.add(inv)
    db.commit()
    return inv


def _subscription(db, tenant, **overrides):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="500.00")
    data = dict(
        organization_id=tenant.organization.id,
        customer_id=customer.id,
        plan_id=plan.id,
        quantity=1,
        status=SubscriptionStatus.ACTIVE,
        start_date=date(2026, 3, 1),
        current_period_start=date(2026, 3, 1),
        current_period_end=date(2026, 4, 1),
        next_billing_date=date(2026, 4, 1),
        subscription_number=f"SUB-TZC-{uuid.uuid4().hex[:6]}",
    )
    data.update(overrides)
    sub = Subscription(**data)
    db.add(sub)
    db.commit()
    return sub


# --- overdue marking: mark_overdue and the scheduler agree -------------------------------------


def test_mark_overdue_agrees_with_scheduler_for_kolkata_at_2000_utc(client, db, frozen):
    kolkata = _tenant(db, KOLKATA)
    new_york = _tenant(db, NEW_YORK)
    inv_in = _open_invoice(db, kolkata, date(2026, 3, 31))
    inv_ny = _open_invoice(db, new_york, date(2026, 3, 31))

    # The scheduler's per-org business day...
    days = scheduler._org_todays(db, None)
    assert days[kolkata.organization.id] == date(2026, 4, 1)
    assert days[new_york.organization.id] == date(2026, 3, 31)

    # ...is exactly what mark_overdue uses when called on its own (no `today`), so the
    # scheduler's pre-check and the function itself can never disagree.
    assert invoice_service.mark_overdue(db, inv_in) is True
    assert invoice_service.mark_overdue(db, inv_ny) is False
    db.commit()
    assert inv_in.status == InvoiceStatus.OVERDUE
    assert inv_ny.status == InvoiceStatus.SENT
    assert invoice_service.days_overdue(inv_ny) == 0

    # And the scheduler run leaves the New York invoice alone until its own midnight.
    scheduler.run_billing_jobs(db)
    db.refresh(inv_ny)
    assert inv_ny.status == InvoiceStatus.SENT
    frozen(datetime(2026, 4, 1, 4, 0, tzinfo=UTC))  # 00:00 EDT on 1 April
    scheduler.run_billing_jobs(db)
    db.refresh(inv_ny)
    assert inv_ny.status == InvoiceStatus.OVERDUE


def test_recompute_invoice_status_uses_org_local_date(client, db, frozen):
    inv_in = _open_invoice(db, _tenant(db, KOLKATA), date(2026, 3, 31))
    inv_ny = _open_invoice(db, _tenant(db, NEW_YORK), date(2026, 3, 31))
    invoice_service.recompute_invoice(db, inv_in)
    invoice_service.recompute_invoice(db, inv_ny)
    db.commit()
    assert inv_in.status == InvoiceStatus.OVERDUE
    assert inv_ny.status == InvoiceStatus.SENT


# --- renewal due check ---------------------------------------------------------------------------


def test_renewal_due_check_defaults_to_org_local_date(client, db, frozen):
    from backend.app.services.subscription_service import renew_subscription

    sub_in = _subscription(db, _tenant(db, KOLKATA))
    sub_ny = _subscription(db, _tenant(db, NEW_YORK))

    assert renew_subscription(db, sub_ny, only_if_due=True) == "skipped"
    db.commit()
    db.refresh(sub_ny)
    assert sub_ny.next_billing_date == date(2026, 4, 1)

    assert renew_subscription(db, sub_in, only_if_due=True) != "skipped"
    db.commit()
    db.refresh(sub_in)
    assert sub_in.next_billing_date > date(2026, 4, 1)
    assert sub_in.current_period_start == date(2026, 4, 1)


# --- trial end -----------------------------------------------------------------------------------


def test_trial_end_evaluation_uses_org_local_date(client, db, frozen):
    from backend.app.services.trial_service import evaluate_expiring_trials

    trial = dict(
        status=SubscriptionStatus.TRIALING,
        trial_start=date(2026, 3, 18),
        trial_end=date(2026, 4, 1),
        start_date=date(2026, 3, 18),
        current_period_start=date(2026, 3, 18),
        current_period_end=date(2026, 4, 1),
        next_billing_date=date(2026, 4, 1),
    )
    kolkata = _tenant(db, KOLKATA)
    new_york = _tenant(db, NEW_YORK)
    _subscription(db, kolkata, **trial)
    sub_ny = _subscription(db, new_york, **trial)

    # 1 April has begun in Kolkata: its trial has ended and is evaluated.
    assert evaluate_expiring_trials(db, org_id=kolkata.organization.id, commit=True)["evaluated"] == 1
    # Still 31 March in New York: the trial runs until its own local midnight.
    assert evaluate_expiring_trials(db, org_id=new_york.organization.id, commit=True)["evaluated"] == 0
    db.refresh(sub_ny)
    assert sub_ny.status == SubscriptionStatus.TRIALING


# --- quote expiry --------------------------------------------------------------------------------


def _sent_quote(db, tenant, expiry):
    quote = Quote(
        organization_id=tenant.organization.id,
        quote_number=f"QT-TZC-{uuid.uuid4().hex[:6]}",
        customer_id=tenant.customer().id,
        status=QuoteStatus.SENT,
        issue_date=expiry - timedelta(days=14),
        expiry_date=expiry,
        currency="INR",
        public_token=uuid.uuid4().hex,
    )
    db.add(quote)
    db.commit()
    return quote


def test_quote_expiry_uses_org_local_date(client, db, frozen):
    kolkata = _tenant(db, KOLKATA)
    new_york = _tenant(db, NEW_YORK)
    q_in = _sent_quote(db, kolkata, date(2026, 3, 31))
    q_ny = _sent_quote(db, new_york, date(2026, 3, 31))

    # A quote is valid through its expiry date in the organization's timezone.
    assert quote_service._is_past_expiry(q_in) is True
    assert quote_service._is_past_expiry(q_ny) is False
    assert quote_service.expire_stale_quotes(db, kolkata.organization.id) == 1
    assert quote_service.expire_stale_quotes(db, new_york.organization.id) == 0
    db.commit()
    db.refresh(q_in)
    db.refresh(q_ny)
    assert q_in.status == QuoteStatus.EXPIRED
    assert q_ny.status == QuoteStatus.SENT


def test_quote_issue_date_default_and_past_check_use_org_local_date(client, db, frozen):
    kolkata = _tenant(db, KOLKATA)
    customer = kolkata.customer()
    line = {"description": "Consulting", "quantity": "1", "unit_price": "100.00", "tax_rate_pct": "0"}

    created = client.post(
        "/api/v1/quotes", json={"customer_id": customer.id, "items": [line]}, headers=kolkata.headers()
    )
    assert created.status_code == 201, created.text
    assert created.json()["issue_date"] == "2026-04-01"

    # 31 March is still "today" somewhere (so the schema lets it through) but it is already
    # in the past for a Kolkata organization: the service rejects it.
    past = client.post(
        "/api/v1/quotes",
        json={"customer_id": customer.id, "issue_date": "2026-03-31", "items": [line]},
        headers=kolkata.headers(),
    )
    assert past.status_code == 422, past.text
    assert "past" in past.text

    new_york = _tenant(db, NEW_YORK)
    ok = client.post(
        "/api/v1/quotes",
        json={"customer_id": new_york.customer().id, "issue_date": "2026-03-31", "items": [line]},
        headers=new_york.headers(),
    )
    assert ok.status_code == 201, ok.text


# --- credit note issue date ------------------------------------------------------------------------


def test_credit_note_issue_date_defaults_to_org_local_date(client, db, frozen):
    from backend.app.services import credit_service

    notes = {}
    for tz_name in (KOLKATA, NEW_YORK):
        t = _tenant(db, tz_name)
        notes[tz_name] = credit_service.create_credit_note(
            db,
            organization_id=t.organization.id,
            customer_id=t.customer().id,
            lines=[{"description": "Goodwill", "amount": "50.00", "tax_rate_pct": "0"}],
        )
    db.commit()
    assert notes[KOLKATA].issue_date == date(2026, 4, 1)
    assert notes[NEW_YORK].issue_date == date(2026, 3, 31)


# --- invoice issue date --------------------------------------------------------------------------


def test_invoice_record_issue_date_defaults_to_org_local_date(client, db, frozen):
    from backend.app.services.money import LineInput

    dates = {}
    for tz_name in (KOLKATA, NEW_YORK):
        t = _tenant(db, tz_name)
        inv = invoice_service.create_invoice_record(
            db,
            organization_id=t.organization.id,
            customer=t.customer(),
            lines=[LineInput(description="Work", quantity=Decimal("1"), unit_price=Decimal("10"), tax_rate_pct=Decimal("0"))],
        )
        dates[tz_name] = inv.issue_date
    db.commit()
    assert dates == {KOLKATA: date(2026, 4, 1), NEW_YORK: date(2026, 3, 31)}


# --- report ranges ------------------------------------------------------------------------------


def _payment(db, tenant, customer, amount, paid_at):
    p = Payment(
        organization_id=tenant.organization.id,
        payment_number=f"PAY-TZC-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        amount=Decimal(amount),
        currency="INR",
        method=PaymentMethod.BANK_TRANSFER,
        gateway=PaymentGateway.MANUAL,
        status=PaymentStatus.SUCCEEDED,
        reconciliation_status=ReconciliationStatus.UNMATCHED,
        paid_at=paid_at,
        amount_refunded=Decimal("0.00"),
    )
    db.add(p)
    db.commit()
    return p


def test_report_this_month_range_kolkata_vs_new_york_at_month_boundary(client, db, frozen):
    from backend.app.api.v1.endpoints.reports import report_range

    results = {}
    for tz_name in (KOLKATA, NEW_YORK):
        t = _tenant(db, tz_name)
        customer = t.customer()
        # 17:00 UTC = 22:30 IST / 13:00 EDT on 31 March; 19:00 UTC = 00:30 IST on 1 April.
        _payment(db, t, customer, "100.00", datetime(2026, 3, 31, 17, 0, tzinfo=UTC))
        _payment(db, t, customer, "10.00", datetime(2026, 3, 31, 19, 0, tzinfo=UTC))
        r = report_range(range="this_month", start=None, end=None, ctx=SimpleNamespace(organization=t.organization))
        results[tz_name] = (r, reports_service.kpis(db, t.organization.id, r), t.organization.id)

    r_in, kpis_in, _ = results[KOLKATA]
    assert (r_in.start, r_in.end) == (date(2026, 4, 1), date(2026, 4, 1))
    assert reports_service._dt_bounds(r_in) == (
        datetime(2026, 3, 31, 18, 30, tzinfo=UTC),
        datetime(2026, 4, 1, 18, 30, tzinfo=UTC),
    )
    assert kpis_in["total_revenue"] == "10.00"  # only the payment made on local 1 April

    r_ny, kpis_ny, ny_org_id = results[NEW_YORK]
    assert (r_ny.start, r_ny.end) == (date(2026, 3, 1), date(2026, 3, 31))
    assert kpis_ny["total_revenue"] == "110.00"  # both are 31 March in New York

    # The revenue-over-time buckets use the local date of each payment too.
    trend = reports_service.revenue_analytics(db, ny_org_id, r_ny)
    assert {row["period"]: row["amount"] for row in trend["revenue_over_time"]}["2026-03-31"] == "110.00"


def test_resolve_report_range_takes_org_today():
    r = reports_service.resolve_report_range("last_month", today=date(2026, 4, 1), tz=KOLKATA)
    assert (r.start, r.end) == (date(2026, 3, 1), date(2026, 3, 31))
