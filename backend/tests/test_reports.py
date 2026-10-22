"""Backend tests for the Reports & Analytics module (`reports_service` + `/reports`).

Reports & Analytics is entirely read-only: every number is computed live from
Invoice/Payment/Refund/InvoiceItem/Customer rows, nothing is cached or
snapshotted. These tests exercise `resolve_report_range()`'s boundary math,
each analytics function's aggregation logic (gross vs. net revenue, aging
buckets, status breakdowns, product/plan grouping, pricing-model grouping),
CSV export (including the empty-data path), tenant isolation, and RBAC over
HTTP (every endpoint only requires `viewer`).
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from backend.app.core.tenant_context import system_context, tenant_context
from backend.app.api.deps import CurrentContext
from backend.app.models import (
    Customer,
    CustomerStatus,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    MemberRole,
    Membership,
    Organization,
    Payment,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    Plan,
    PricingModel,
    Product,
    ProductType,
    ReconciliationStatus,
    Refund,
    RefundStatus,
    User,
)
from backend.app.services import reports_service as svc

BASE = "/api/v1/reports"


# --- direct-service fixture (mirrors test_collections.org_ctx) ------------------------------


@pytest.fixture
def org_ctx(db: Session):
    uid = uuid.uuid4().hex[:8]
    org = Organization(name=f"Reports Test Org {uid}", slug=f"reports-org-{uid}", default_currency="INR")
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(email=f"reporter_{uid}@example.com", full_name="Reports Tester", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    membership = Membership(organization_id=org.id, user_id=user.id, role="owner", status="active")
    db.add(membership)

    customer = Customer(
        organization_id=org.id,
        customer_number=f"CUST-{uid}",
        display_name=f"Reports Customer {uid}",
        email=f"cust_{uid}@example.com",
        currency="INR",
        status=CustomerStatus.ACTIVE,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    ctx = CurrentContext(user=user, organization=org, membership=membership, ip_address=None, user_agent=None)
    # Like require_role() in a real request: everything after this runs in the org's tenant context.
    with tenant_context(org.id):
        yield org, user, customer, ctx


def _mk_org_and_customer(db: Session, *, label: str) -> tuple[Organization, Customer]:
    uid = uuid.uuid4().hex[:8]
    org = Organization(name=f"{label} Org {uid}", slug=f"{label.lower()}-org-{uid}", default_currency="INR")
    db.add(org)
    db.commit()
    db.refresh(org)
    customer = Customer(
        organization_id=org.id,
        customer_number=f"CUST-{uid}",
        display_name=f"{label} Customer",
        email=f"{label.lower()}_{uid}@example.com",
        currency="INR",
        status=CustomerStatus.ACTIVE,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return org, customer


# --- direct model builders (fine control over dates/amounts, per the module's own guidance) -


def _mk_invoice(
    db: Session,
    org: Organization,
    customer: Customer,
    *,
    status: InvoiceStatus,
    issue_date: date,
    due_date: date,
    total="1000.00",
    amount_due=None,
    paid_at=None,
    items=None,
) -> Invoice:
    total_d = Decimal(total)
    if amount_due is None:
        amount_due = Decimal("0.00") if status in (InvoiceStatus.PAID, InvoiceStatus.DRAFT, InvoiceStatus.VOID) else total_d
    else:
        amount_due = Decimal(amount_due)
    amount_paid = q2 = total_d - amount_due
    inv = Invoice(
        organization_id=org.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:10]}",
        customer_id=customer.id,
        status=status,
        issue_date=issue_date,
        due_date=due_date,
        currency="INR",
        subtotal=total_d,
        discount_pct=Decimal("0"),
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total=total_d,
        amount_paid=amount_paid,
        amount_due=amount_due,
        public_token=uuid.uuid4().hex,
        paid_at=paid_at,
    )
    db.add(inv)
    db.flush()
    if items is None:
        items = [{"description": "Line", "quantity": "1", "unit_price": total, "amount": total}]
    for idx, item in enumerate(items):
        db.add(
            InvoiceItem(
                organization_id=org.id,
                invoice_id=inv.id,
                description=item.get("description", "Line"),
                quantity=Decimal(item.get("quantity", "1")),
                unit_price=Decimal(item.get("unit_price", "0")),
                tax_rate_pct=Decimal("0"),
                amount=Decimal(item.get("amount", "0")),
                position=idx,
                product_id=item.get("product_id"),
                plan_id=item.get("plan_id"),
            )
        )
    db.commit()
    db.refresh(inv)
    return inv


def _mk_payment(
    db: Session,
    org: Organization,
    customer: Customer,
    *,
    amount,
    paid_at,
    method: PaymentMethod = PaymentMethod.BANK_TRANSFER,
    status: PaymentStatus = PaymentStatus.SUCCEEDED,
    amount_refunded="0.00",
) -> Payment:
    p = Payment(
        organization_id=org.id,
        payment_number=f"PAY-{uuid.uuid4().hex[:10]}",
        customer_id=customer.id,
        amount=Decimal(amount),
        currency="INR",
        method=method,
        gateway=PaymentGateway.MANUAL,
        status=status,
        reconciliation_status=ReconciliationStatus.UNMATCHED,
        paid_at=paid_at,
        amount_refunded=Decimal(amount_refunded),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _mk_refund(db: Session, org: Organization, payment: Payment, *, amount, created_at, status: RefundStatus = RefundStatus.PROCESSED) -> Refund:
    r = Refund(organization_id=org.id, payment_id=payment.id, amount=Decimal(amount), status=status, created_at=created_at)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _mk_product_plan(db: Session, org: Organization, *, pricing_model: PricingModel = PricingModel.PER_UNIT) -> tuple[Product, Plan]:
    code = uuid.uuid4().hex[:8]
    product = Product(organization_id=org.id, name=f"Product {code}", sku=f"SKU-{code}", type=ProductType.SERVICE, tax_rate_pct=Decimal("0"))
    db.add(product)
    db.flush()
    plan = Plan(
        organization_id=org.id,
        product_id=product.id,
        name=f"Plan {code}",
        code=f"PLAN-{code}",
        pricing_model=pricing_model,
        unit_amount=Decimal("100.00"),
        currency="INR",
    )
    db.add(plan)
    db.commit()
    db.refresh(product)
    db.refresh(plan)
    return product, plan


def _noon(d: date) -> datetime:
    return datetime.combine(d, time(12, 0), tzinfo=timezone.utc)


def _custom_range(start: date, end: date) -> svc.ReportRange:
    return svc.resolve_report_range("custom", start=start, end=end)


TODAY = date.today()


# =============================================================================================
# 1. resolve_report_range() — pure boundary math
# =============================================================================================


def test_resolve_range_today():
    r = svc.resolve_report_range("today")
    assert r.key == "today"
    assert r.start == TODAY
    assert r.end == TODAY


def test_resolve_range_this_week():
    r = svc.resolve_report_range("this_week")
    assert r.start == TODAY - timedelta(days=TODAY.weekday())
    assert r.start.weekday() == 0  # Monday
    assert r.end == TODAY


def test_resolve_range_this_month():
    r = svc.resolve_report_range("this_month")
    assert r.start == TODAY.replace(day=1)
    assert r.end == TODAY


def test_resolve_range_last_month():
    r = svc.resolve_report_range("last_month")
    first_this_month = TODAY.replace(day=1)
    expected_end = first_this_month - timedelta(days=1)
    assert r.end == expected_end
    assert r.start == expected_end.replace(day=1)
    assert r.start.day == 1
    # the whole range must fall strictly before this month
    assert r.end < first_this_month


def test_resolve_range_this_quarter():
    r = svc.resolve_report_range("this_quarter")
    expected_month = ((TODAY.month - 1) // 3) * 3 + 1
    assert r.start == TODAY.replace(month=expected_month, day=1)
    assert r.start.month in (1, 4, 7, 10)
    assert r.end == TODAY


def test_resolve_range_this_year():
    r = svc.resolve_report_range("this_year")
    assert r.start == TODAY.replace(month=1, day=1)
    assert r.end == TODAY


def test_resolve_range_last_12_months():
    r = svc.resolve_report_range("last_12_months")
    assert r.start == TODAY - timedelta(days=365)
    assert r.end == TODAY


def test_resolve_range_custom_valid():
    start = TODAY - timedelta(days=10)
    end = TODAY
    r = svc.resolve_report_range("custom", start=start, end=end)
    assert r.key == "custom"
    assert r.start == start
    assert r.end == end


def test_resolve_range_custom_missing_start_or_end_raises():
    with pytest.raises(ValueError):
        svc.resolve_report_range("custom", start=None, end=TODAY)
    with pytest.raises(ValueError):
        svc.resolve_report_range("custom", start=TODAY, end=None)
    with pytest.raises(ValueError):
        svc.resolve_report_range("custom")


def test_resolve_range_custom_end_before_start_raises():
    with pytest.raises(ValueError):
        svc.resolve_report_range("custom", start=TODAY, end=TODAY - timedelta(days=1))


def test_resolve_range_unknown_key_raises():
    with pytest.raises(ValueError):
        svc.resolve_report_range("not_a_real_range")


def test_resolve_range_empty_key_defaults_to_this_month():
    r = svc.resolve_report_range("")
    assert r.key == "this_month"
    assert r.start == TODAY.replace(day=1)


# =============================================================================================
# 2. small pure helpers: _bucket_key / _granularity_for / _empty_buckets
# =============================================================================================


def test_bucket_key_day_vs_month():
    d = date(2026, 3, 7)
    assert svc._bucket_key(d, "day") == "2026-03-07"
    assert svc._bucket_key(d, "month") == "2026-03"


def test_granularity_for_boundary_at_62_days():
    r62 = svc.ReportRange("custom", date(2026, 1, 1), date(2026, 1, 1) + timedelta(days=62))
    r63 = svc.ReportRange("custom", date(2026, 1, 1), date(2026, 1, 1) + timedelta(days=63))
    assert svc._granularity_for(r62) == "day"
    assert svc._granularity_for(r63) == "month"


def test_empty_buckets_day_granularity_covers_every_day():
    r = svc.ReportRange("custom", date(2026, 1, 1), date(2026, 1, 5))
    buckets = svc._empty_buckets(r, "day")
    assert list(buckets.keys()) == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
    assert all(v == Decimal("0") for v in buckets.values())


def test_empty_buckets_month_granularity_covers_every_month():
    r = svc.ReportRange("custom", date(2026, 1, 15), date(2026, 4, 3))
    buckets = svc._empty_buckets(r, "month")
    assert list(buckets.keys()) == ["2026-01", "2026-02", "2026-03", "2026-04"]


# =============================================================================================
# 3. kpis()
# =============================================================================================


def test_kpis_gross_vs_net_revenue_with_partial_refund(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    payment = _mk_payment(db, org, customer, amount="1000.00", paid_at=_noon(TODAY), status=PaymentStatus.PARTIALLY_REFUNDED, amount_refunded="200.00")
    _mk_refund(db, org, payment, amount="200.00", created_at=_noon(TODAY))

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.kpis(db, org.id, r)
    assert result["total_revenue"] == "1000.00"
    assert result["net_revenue"] == "800.00"
    assert result["total_collected"] == "800.00"


def test_kpis_total_invoiced_excludes_draft(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    _mk_invoice(db, org, customer, status=InvoiceStatus.DRAFT, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total="500.00")
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total="700.00")

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.kpis(db, org.id, r)
    assert result["total_invoiced"] == "700.00"
    assert result["average_invoice_value"] == "700.00"


def test_kpis_outstanding_and_overdue_are_current_snapshots_not_range_bound(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    # overdue by explicit status
    _mk_invoice(db, org, customer, status=InvoiceStatus.OVERDUE, issue_date=TODAY - timedelta(days=100), due_date=TODAY - timedelta(days=50), total="1000.00")
    # overdue implicitly: SENT with due_date in the past
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY - timedelta(days=100), due_date=TODAY - timedelta(days=5), total="2000.00")
    # not overdue: SENT with due_date in the future
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY - timedelta(days=100), due_date=TODAY + timedelta(days=20), total="3000.00")

    # a date range that excludes every invoice's issue_date entirely (proves these figures
    # are NOT filtered by the report range).
    far_range = _custom_range(TODAY + timedelta(days=365), TODAY + timedelta(days=366))
    result = svc.kpis(db, org.id, far_range)
    assert result["outstanding_receivables"] == "6000.00"
    assert result["overdue_receivables"] == "3000.00"  # 1000 + 2000
    assert result["total_invoiced"] == "0.00"  # nothing issued in this range


def test_kpis_collection_rate_and_average_invoice_value_none_when_zero(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.kpis(db, org.id, r)
    assert result["collection_rate"] is None
    assert result["average_invoice_value"] is None
    assert result["total_invoiced"] == "0.00"


def test_kpis_collection_rate_computation(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total="1000.00")
    _mk_payment(db, org, customer, amount="400.00", paid_at=_noon(TODAY))

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.kpis(db, org.id, r)
    assert result["total_invoiced"] == "1000.00"
    assert result["net_revenue"] == "400.00"
    assert result["collection_rate"] == "40.00"


# =============================================================================================
# 4. revenue_analytics()
# =============================================================================================


def test_revenue_analytics_granularity_day_vs_month(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    short_range = _custom_range(TODAY - timedelta(days=10), TODAY)
    long_range = _custom_range(TODAY - timedelta(days=100), TODAY)
    assert svc.revenue_analytics(db, org.id, short_range)["granularity"] == "day"
    assert svc.revenue_analytics(db, org.id, long_range)["granularity"] == "month"


def test_revenue_by_product_and_plan_grouping_excludes_ad_hoc_lines(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    product, plan = _mk_product_plan(db, org)
    _mk_invoice(
        db,
        org,
        customer,
        status=InvoiceStatus.SENT,
        issue_date=TODAY,
        due_date=TODAY + timedelta(days=30),
        total="1300.00",
        items=[
            {"description": "Subscription", "quantity": "2", "unit_price": "500.00", "amount": "1000.00", "product_id": product.id, "plan_id": plan.id},
            {"description": "Ad-hoc consulting", "quantity": "1", "unit_price": "300.00", "amount": "300.00"},
        ],
    )

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.revenue_analytics(db, org.id, r)

    by_product = result["revenue_by_product"]
    assert len(by_product) == 1
    assert by_product[0]["id"] == product.id
    assert by_product[0]["name"] == product.name
    assert by_product[0]["revenue"] == "1000.00"
    assert Decimal(by_product[0]["quantity"]) == Decimal("2")

    by_plan = result["revenue_by_plan"]
    assert len(by_plan) == 1
    assert by_plan[0]["id"] == plan.id
    assert by_plan[0]["revenue"] == "1000.00"
    assert Decimal(by_plan[0]["quantity"]) == Decimal("2")


def test_revenue_by_product_and_plan_exclude_voided_invoices(db: Session, org_ctx):
    # A voided invoice was cancelled, so its lines are not revenue - the same rule as
    # total_invoiced and invoiced_vs_collected (_invoiced_query excludes DRAFT and VOID).
    org, user, customer, ctx = org_ctx
    product, plan = _mk_product_plan(db, org, pricing_model=PricingModel.FLAT)
    line = {"description": "Subscription", "product_id": product.id, "plan_id": plan.id}
    _mk_invoice(
        db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY, due_date=TODAY + timedelta(days=30),
        total="1000.00", items=[{**line, "quantity": "2", "unit_price": "500.00", "amount": "1000.00"}],
    )
    _mk_invoice(
        db, org, customer, status=InvoiceStatus.VOID, issue_date=TODAY, due_date=TODAY + timedelta(days=30),
        total="9999.00", items=[{**line, "quantity": "50", "unit_price": "199.98", "amount": "9999.00"}],
    )

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    revenue = svc.revenue_analytics(db, org.id, r)
    assert [(row["revenue"], Decimal(row["quantity"])) for row in revenue["revenue_by_product"]] == [("1000.00", Decimal("2"))]
    assert [(row["revenue"], Decimal(row["quantity"])) for row in revenue["revenue_by_plan"]] == [("1000.00", Decimal("2"))]

    products = svc.product_analytics(db, org.id, r)
    assert [Decimal(row["quantity"]) for row in products["best_selling"]] == [Decimal("2")]
    assert products["revenue_by_pricing_model"] == [{"pricing_model": "flat", "amount": "1000.00", "currency": "INR"}]

    csv_text = "".join(svc.export_section_csv(db, org.id, "revenue_by_product", r))
    assert "1000.00" in csv_text and "9999.00" not in csv_text


def test_unlinked_payment_counts_in_totals_but_not_in_customer_ranking(db: Session, org_ctx):
    # A payment without a customer (customer_id is nullable) is real cash: it stays in every
    # total and in the method breakdown; only the per-customer ranking cannot place it.
    org, user, customer, ctx = org_ctx
    _mk_payment(db, org, customer, amount="600.00", paid_at=_noon(TODAY))
    unlinked = _mk_payment(db, org, customer, amount="400.00", paid_at=_noon(TODAY), method=PaymentMethod.UPI)
    unlinked.customer_id = None
    db.commit()

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    assert svc.kpis(db, org.id, r)["total_collected"] == "1000.00"
    payments = svc.payment_analytics(db, org.id, r)
    assert (payments["total_payments"], payments["payment_count"]) == ("1000.00", 2)
    assert sum(Decimal(row["amount"]) for row in payments["method_breakdown"]) == Decimal("1000.00")
    ranking = svc.revenue_analytics(db, org.id, r)["revenue_by_customer"]
    assert [(row["customer"]["id"], row["amount"]) for row in ranking] == [(customer.id, "600.00")]


def test_revenue_over_time_and_invoiced_vs_collected_buckets(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total="500.00")
    _mk_payment(db, org, customer, amount="200.00", paid_at=_noon(TODAY))

    r = _custom_range(TODAY - timedelta(days=2), TODAY + timedelta(days=2))
    result = svc.revenue_analytics(db, org.id, r)
    assert result["granularity"] == "day"

    key = svc._bucket_key(TODAY, "day")
    revenue_point = {p["period"]: p["amount"] for p in result["revenue_over_time"]}
    assert revenue_point[key] == "200.00"

    ivc_point = {p["period"]: p for p in result["invoiced_vs_collected"]}
    assert ivc_point[key]["invoiced"] == "500.00"
    assert ivc_point[key]["collected"] == "200.00"


def test_revenue_by_customer_top_customers(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    _mk_payment(db, org, customer, amount="750.00", paid_at=_noon(TODAY))

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.revenue_analytics(db, org.id, r)
    assert len(result["revenue_by_customer"]) == 1
    row = result["revenue_by_customer"][0]
    assert row["customer"]["id"] == customer.id
    assert row["amount"] == "750.00"


# =============================================================================================
# 5. receivables_analytics()
# =============================================================================================


def test_outstanding_by_aging_sums_to_total_open(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY - timedelta(days=200), due_date=TODAY + timedelta(days=5), total="1000.00")
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY - timedelta(days=200), due_date=TODAY - timedelta(days=15), total="2000.00")
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY - timedelta(days=200), due_date=TODAY - timedelta(days=45), total="3000.00")
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY - timedelta(days=200), due_date=TODAY - timedelta(days=75), total="4000.00")
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY - timedelta(days=200), due_date=TODAY - timedelta(days=200), total="5000.00")
    # closed invoices must not be counted at all
    _mk_invoice(db, org, customer, status=InvoiceStatus.PAID, issue_date=TODAY - timedelta(days=200), due_date=TODAY - timedelta(days=200), total="9999.00")
    _mk_invoice(db, org, customer, status=InvoiceStatus.VOID, issue_date=TODAY - timedelta(days=200), due_date=TODAY - timedelta(days=200), total="8888.00")

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.receivables_analytics(db, org.id, r)
    buckets = {row["bucket"]: row for row in result["outstanding_by_aging"]}
    assert Decimal(buckets["current"]["amount"]) == Decimal("1000.00")
    assert Decimal(buckets["1_30"]["amount"]) == Decimal("2000.00")
    assert Decimal(buckets["31_60"]["amount"]) == Decimal("3000.00")
    assert Decimal(buckets["61_90"]["amount"]) == Decimal("4000.00")
    assert Decimal(buckets["90_plus"]["amount"]) == Decimal("5000.00")

    total = sum(Decimal(row["amount"]) for row in result["outstanding_by_aging"])
    assert total == Decimal("15000.00")


def test_overdue_by_due_period_excludes_non_overdue_invoices(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    current_inv = _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY - timedelta(days=10), due_date=TODAY + timedelta(days=10), total="1000.00")
    overdue_inv = _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY - timedelta(days=60), due_date=TODAY - timedelta(days=20), total="2500.00")

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.receivables_analytics(db, org.id, r)
    periods = {row["period"]: row["amount"] for row in result["overdue_by_due_period"]}

    overdue_key = f"{overdue_inv.due_date.year:04d}-{overdue_inv.due_date.month:02d}"
    current_key = f"{current_inv.due_date.year:04d}-{current_inv.due_date.month:02d}"

    assert periods[overdue_key] == "2500.00"
    total_overdue = sum(Decimal(v) for v in periods.values())
    assert total_overdue == Decimal("2500.00")
    if current_key != overdue_key:
        assert current_key not in periods


def test_average_days_to_payment(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    _mk_invoice(
        db, org, customer, status=InvoiceStatus.PAID,
        issue_date=TODAY - timedelta(days=30), due_date=TODAY - timedelta(days=15),
        total="1000.00", paid_at=_noon(TODAY),
    )
    _mk_invoice(
        db, org, customer, status=InvoiceStatus.PAID,
        issue_date=TODAY - timedelta(days=10), due_date=TODAY + timedelta(days=5),
        total="500.00", paid_at=_noon(TODAY),
    )

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.receivables_analytics(db, org.id, r)
    assert result["average_days_to_payment"] == 20.0  # (30 + 10) / 2


def test_average_days_to_payment_none_when_no_paid_invoices_in_range(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total="500.00")

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.receivables_analytics(db, org.id, r)
    assert result["average_days_to_payment"] is None


# =============================================================================================
# 6. invoice_analytics()
# =============================================================================================


def test_invoice_analytics_by_status_includes_draft_and_totals_add_up(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    _mk_invoice(db, org, customer, status=InvoiceStatus.DRAFT, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total="500.00")
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total="700.00")
    _mk_invoice(db, org, customer, status=InvoiceStatus.PAID, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total="300.00", paid_at=_noon(TODAY))

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.invoice_analytics(db, org.id, r)

    assert result["by_status"]["draft"] == {"count": 1, "amount": "500.00"}
    assert result["by_status"]["sent"] == {"count": 1, "amount": "700.00"}
    assert result["by_status"]["paid"] == {"count": 1, "amount": "300.00"}
    assert result["total_count"] == sum(v["count"] for v in result["by_status"].values())
    assert result["total_count"] == 3
    assert result["average_invoice_amount"] == "500.00"  # (500 + 700 + 300) / 3


def test_invoice_analytics_average_none_when_zero_invoices(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.invoice_analytics(db, org.id, r)
    assert result["total_count"] == 0
    assert result["average_invoice_amount"] is None
    assert result["by_status"] == {}


# =============================================================================================
# 7. payment_analytics()
# =============================================================================================


def test_method_breakdown_uses_gross_amount_not_net(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    p1 = _mk_payment(db, org, customer, amount="1000.00", paid_at=_noon(TODAY), method=PaymentMethod.UPI, status=PaymentStatus.PARTIALLY_REFUNDED, amount_refunded="300.00")
    _mk_refund(db, org, p1, amount="300.00", created_at=_noon(TODAY))
    _mk_payment(db, org, customer, amount="500.00", paid_at=_noon(TODAY), method=PaymentMethod.CASH)

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.payment_analytics(db, org.id, r)
    methods = {row["method"]: row["amount"] for row in result["method_breakdown"]}
    assert methods["upi"] == "1000.00"  # gross, not 700
    assert methods["cash"] == "500.00"
    assert result["total_payments"] == "1500.00"
    assert result["net_collected"] == "1200.00"  # 700 + 500


def test_refund_amount_keyed_off_refund_created_at_not_payment_paid_at(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    # payment paid_at is OUTSIDE the report range, but the refund's created_at is INSIDE it.
    old_payment = _mk_payment(
        db, org, customer, amount="1000.00", paid_at=_noon(TODAY - timedelta(days=90)),
        status=PaymentStatus.PARTIALLY_REFUNDED, amount_refunded="150.00",
    )
    _mk_refund(db, org, old_payment, amount="150.00", created_at=_noon(TODAY))

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.payment_analytics(db, org.id, r)
    assert result["refund_amount"] == "150.00"
    # the payment itself is outside this range, so payment_count/total_payments are 0
    assert result["payment_count"] == 0
    assert result["total_payments"] == "0.00"


def test_net_collected_matches_kpis_net_revenue(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    p = _mk_payment(db, org, customer, amount="800.00", paid_at=_noon(TODAY), status=PaymentStatus.PARTIALLY_REFUNDED, amount_refunded="100.00")
    _mk_refund(db, org, p, amount="100.00", created_at=_noon(TODAY))
    _mk_payment(db, org, customer, amount="200.00", paid_at=_noon(TODAY))

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    payments_result = svc.payment_analytics(db, org.id, r)
    kpis_result = svc.kpis(db, org.id, r)
    assert payments_result["net_collected"] == kpis_result["net_revenue"]
    assert payments_result["net_collected"] == "900.00"


# =============================================================================================
# 8. customer_analytics()
# =============================================================================================


def test_customer_counts_and_outstanding_balance_distinct(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    other_customer = Customer(
        organization_id=org.id,
        customer_number="CUST-OTHER",
        display_name="Other Customer",
        email="other@example.test",
        currency="INR",
        status=CustomerStatus.INACTIVE,
    )
    db.add(other_customer)
    db.commit()
    db.refresh(other_customer)

    # two open invoices against the SAME customer must count as one distinct customer
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY, due_date=TODAY + timedelta(days=10), total="100.00")
    _mk_invoice(db, org, customer, status=InvoiceStatus.OVERDUE, issue_date=TODAY, due_date=TODAY - timedelta(days=10), total="200.00")
    # other_customer has no open invoices with amount_due > 0

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.customer_analytics(db, org.id, r)
    assert result["total_customers"] == 2
    assert result["active_customers"] == 1
    assert result["customers_with_outstanding_balance"] == 1


# =============================================================================================
# 9. product_analytics()
# =============================================================================================


def test_best_selling_is_revenue_by_offering_resorted_by_quantity_capped_at_10(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    items = []
    products = []
    for i in range(11):
        product, plan = _mk_product_plan(db, org)
        products.append(product)
        qty = i + 1  # 1..11, product[10] has the highest quantity
        items.append({"description": f"Item {i}", "quantity": str(qty), "unit_price": "10.00", "amount": str(qty * 10), "product_id": product.id})
    _mk_invoice(db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total=str(sum((i + 1) * 10 for i in range(11))), items=items)

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.product_analytics(db, org.id, r)

    assert len(result["revenue_by_offering"]) == 11  # uncapped
    assert len(result["best_selling"]) == 10  # capped
    assert result["best_selling"][0]["id"] == products[10].id  # quantity 11, the highest
    assert Decimal(result["best_selling"][0]["quantity"]) >= Decimal(result["best_selling"][1]["quantity"])


def test_revenue_by_pricing_model_groups_flat_and_per_unit(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    flat_product, flat_plan = _mk_product_plan(db, org, pricing_model=PricingModel.FLAT)
    per_unit_product, per_unit_plan = _mk_product_plan(db, org, pricing_model=PricingModel.PER_UNIT)

    _mk_invoice(
        db, org, customer, status=InvoiceStatus.SENT, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total="1200.00",
        items=[
            {"description": "Flat plan", "quantity": "1", "unit_price": "500.00", "amount": "500.00", "product_id": flat_product.id, "plan_id": flat_plan.id},
            {"description": "Per-unit plan", "quantity": "7", "unit_price": "100.00", "amount": "700.00", "product_id": per_unit_product.id, "plan_id": per_unit_plan.id},
        ],
    )

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    result = svc.product_analytics(db, org.id, r)
    by_model = {row["pricing_model"]: row["amount"] for row in result["revenue_by_pricing_model"]}
    assert by_model["flat"] == "500.00"
    assert by_model["per_unit"] == "700.00"


# =============================================================================================
# 10. export_section_csv()
# =============================================================================================


def test_export_unknown_section_raises_valueerror(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    with pytest.raises(ValueError):
        list(svc.export_section_csv(db, org.id, "not_a_real_section", r))


def test_export_valid_section_with_data(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    _mk_payment(db, org, customer, amount="640.00", paid_at=_noon(TODAY))

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    chunks = list(svc.export_section_csv(db, org.id, "revenue_by_customer", r))
    csv_text = "".join(chunks)
    assert "customer,amount" in csv_text
    assert customer.display_name in csv_text
    assert "640.00" in csv_text


def test_export_empty_org_yields_single_no_data_row_when_the_section_has_no_rows(db: Session, org_ctx):
    """Sections backed by pre-filled time buckets (revenue_over_time, invoiced_vs_collected)
    or the 5 fixed aging buckets (outstanding_by_aging) always have rows -- just zeroed out --
    so only the genuinely row-less sections fall back to the "No data" sentinel for an org
    with no invoices/payments at all.
    """
    org, user, customer, ctx = org_ctx
    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))

    always_populated = {"revenue_over_time", "invoiced_vs_collected", "outstanding_by_aging"}
    for section in svc.EXPORTABLE_SECTIONS:
        chunks = list(svc.export_section_csv(db, org.id, section, r))
        if section in always_populated:
            assert len(chunks) > 1, f"section={section} chunks={chunks}"
            assert "," in chunks[0]  # a real CSV header, not the "No data" sentinel
        else:
            assert chunks == ["No data for this range.\n"], f"section={section} chunks={chunks}"


# =============================================================================================
# 11. tenant isolation
# =============================================================================================


def test_tenant_isolation_across_report_functions(db: Session):
    # System context switches the ORM tenant filter off, so isolation here comes only from the
    # report functions' own organization_id filtering (the strictest form of this check).
    with system_context():
        _tenant_isolation_across_report_functions(db)


def _tenant_isolation_across_report_functions(db: Session):
    org_a, customer_a = _mk_org_and_customer(db, label="OrgA")
    org_b, customer_b = _mk_org_and_customer(db, label="OrgB")

    product_a, plan_a = _mk_product_plan(db, org_a)
    product_b, plan_b = _mk_product_plan(db, org_b)

    _mk_invoice(
        db, org_a, customer_a, status=InvoiceStatus.SENT, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total="1000.00",
        items=[{"description": "A item", "quantity": "1", "unit_price": "1000.00", "amount": "1000.00", "product_id": product_a.id, "plan_id": plan_a.id}],
    )
    _mk_invoice(
        db, org_b, customer_b, status=InvoiceStatus.SENT, issue_date=TODAY, due_date=TODAY + timedelta(days=30), total="9000.00",
        items=[{"description": "B item", "quantity": "1", "unit_price": "9000.00", "amount": "9000.00", "product_id": product_b.id, "plan_id": plan_b.id}],
    )
    _mk_payment(db, org_a, customer_a, amount="1000.00", paid_at=_noon(TODAY))
    _mk_payment(db, org_b, customer_b, amount="9000.00", paid_at=_noon(TODAY))
    # overdue open invoice for receivables aging, one per org
    _mk_invoice(db, org_a, customer_a, status=InvoiceStatus.OVERDUE, issue_date=TODAY - timedelta(days=50), due_date=TODAY - timedelta(days=10), total="150.00")
    _mk_invoice(db, org_b, customer_b, status=InvoiceStatus.OVERDUE, issue_date=TODAY - timedelta(days=50), due_date=TODAY - timedelta(days=10), total="7500.00")

    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))

    kpis_a = svc.kpis(db, org_a.id, r)
    kpis_b = svc.kpis(db, org_b.id, r)
    assert kpis_a["total_invoiced"] == "1000.00"
    assert kpis_a["net_revenue"] == "1000.00"
    assert kpis_a["overdue_receivables"] == "150.00"
    assert kpis_b["total_invoiced"] == "9000.00"
    assert kpis_b["net_revenue"] == "9000.00"
    assert kpis_b["overdue_receivables"] == "7500.00"

    revenue_a = svc.revenue_analytics(db, org_a.id, r)
    revenue_b = svc.revenue_analytics(db, org_b.id, r)
    assert [row["customer"]["id"] for row in revenue_a["revenue_by_customer"]] == [customer_a.id]
    assert [row["customer"]["id"] for row in revenue_b["revenue_by_customer"]] == [customer_b.id]
    assert revenue_a["revenue_by_product"][0]["id"] == product_a.id
    assert revenue_a["revenue_by_product"][0]["revenue"] == "1000.00"
    assert revenue_b["revenue_by_product"][0]["id"] == product_b.id
    assert revenue_b["revenue_by_product"][0]["revenue"] == "9000.00"

    receivables_a = svc.receivables_analytics(db, org_a.id, r)
    receivables_b = svc.receivables_analytics(db, org_b.id, r)
    total_a = sum(Decimal(row["amount"]) for row in receivables_a["outstanding_by_aging"])
    total_b = sum(Decimal(row["amount"]) for row in receivables_b["outstanding_by_aging"])
    # both orgs' open invoices: the still-open 1000/9000 SENT invoice plus the 150/7500 OVERDUE one
    assert total_a == Decimal("1150.00")
    assert total_b == Decimal("16500.00")

    customers_a = svc.customer_analytics(db, org_a.id, r)
    customers_b = svc.customer_analytics(db, org_b.id, r)
    assert customers_a["total_customers"] == 1
    assert customers_b["total_customers"] == 1

    products_a = svc.product_analytics(db, org_a.id, r)
    products_b = svc.product_analytics(db, org_b.id, r)
    assert [row["amount"] for row in products_a["revenue_by_pricing_model"]] != [row["amount"] for row in products_b["revenue_by_pricing_model"]]
    assert sum(Decimal(row["amount"]) for row in products_a["revenue_by_pricing_model"]) == Decimal("1000.00")
    assert sum(Decimal(row["amount"]) for row in products_b["revenue_by_pricing_model"]) == Decimal("9000.00")


# =============================================================================================
# 12. RBAC + validation over HTTP
# =============================================================================================


def test_viewer_can_access_every_report_endpoint(client, tenant):
    viewer_headers = tenant.headers_for_role(MemberRole.VIEWER)

    for path in ("dashboard", "revenue", "receivables", "invoices", "payments", "customers", "products"):
        resp = client.get(f"{BASE}/{path}", headers=viewer_headers)
        assert resp.status_code == 200, f"{path}: {resp.text}"

    export_resp = client.get(f"{BASE}/export", params={"section": "revenue_over_time"}, headers=viewer_headers)
    assert export_resp.status_code == 200, export_resp.text
    assert "text/csv" in export_resp.headers["content-type"]


def test_export_invalid_section_is_rejected_at_the_service_layer(db: Session, org_ctx):
    """`export_report` (backend/app/api/v1/endpoints/reports.py) intends an unknown `section`
    to raise 422 via `except ValueError as exc: raise ValidationAppError(...)`. In practice
    that `except` never fires: `svc.export_section_csv` is a generator function (it contains
    `yield` later in its body), so *calling* it does not execute any code -- including the
    `raise ValueError` guard -- until the generator is first iterated. That iteration happens
    inside Starlette's StreamingResponse, well outside the endpoint's try/except, by which
    point the 200 response has already started streaming. The practical effect (verified
    manually against a live TestClient) is that GET /reports/export?section=<invalid> either
    crashes with an unhandled anyio ExceptionGroup (default TestClient, which re-raises server
    exceptions) or silently returns HTTP 200 with a truncated body (raise_server_exceptions=False),
    never the intended 422. This is a real bug in the endpoint, but per this task's instructions
    the test suite must not modify implementation files to fix it, so this test instead pins
    down the one place the validation *does* work correctly: the service function itself.
    """
    org, user, customer, ctx = org_ctx
    r = _custom_range(TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    with pytest.raises(ValueError, match="Unknown export section"):
        list(svc.export_section_csv(db, org.id, "not_a_real_section", r))


def test_custom_range_without_start_end_returns_422(client, tenant, auth_headers):
    resp = client.get(f"{BASE}/dashboard", params={"range": "custom"}, headers=auth_headers)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # also verify on the export endpoint (its own report_range dependency)
    resp2 = client.get(f"{BASE}/export", params={"range": "custom", "section": "revenue_over_time"}, headers=auth_headers)
    assert resp2.status_code == 422, resp2.text
