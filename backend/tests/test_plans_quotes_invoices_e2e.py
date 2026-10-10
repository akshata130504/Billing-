"""
Comprehensive End-to-End Tests for Plans & Pricing, Quotes, and Invoices.
Covers Tests 1 to 13 from the Master Implementation Prompt.
"""
from datetime import date, timedelta
from decimal import Decimal
import uuid
import pytest
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.models.identity import Organization, User, Membership
from backend.app.models.customers import Customer
from backend.app.models.catalog_cpq import Offering
from backend.app.models.quotes import Quote, QuoteStatus
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.payments import Payment, PaymentAllocation
from backend.app.schemas.quotes import QuoteCreate, QuoteConvertIn
from backend.app.schemas.invoices import InvoiceCreate, RecordPaymentIn
from backend.app.schemas.common_refs import LineItemIn
from backend.app.services import quote_service, invoice_service, payment_service, timezones
from backend.app.services.pricing_engine import calculate_line_item_pricing


@pytest.fixture
def org_and_user(db: Session):
    uid = uuid.uuid4().hex[:8]
    org = Organization(
        name=f"Billing Test Org {uid}",
        slug=f"billing-org-{uid}",
        default_currency="INR",
        country="IN",
        # GST-registered: without a GSTIN no GST is charged at all (BUG-07).
        gstin="29AAFCB9900V1Z8",
        state="Karnataka",
        discount_approval_threshold_pct=Decimal("5.00"),
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(
        email=f"tester_{uid}@example.com",
        full_name="Billing Tester",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    membership = Membership(
        organization_id=org.id,
        user_id=user.id,
        role="owner",
        status="active",
    )
    db.add(membership)

    customer = Customer(
        organization_id=org.id,
        customer_number=f"CUST-{uid}",
        display_name="Enterprise Corp",
        company_name="Enterprise Corp Pvt Ltd",
        email=f"finance_{uid}@enterprise.com",
        currency="INR",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    ctx = CurrentContext(
        user=user,
        organization=org,
        membership=membership,
        ip_address=None,
        user_agent=None,
    )

    from backend.app.core.tenant_context import tenant_context
    with tenant_context(org.id):
        yield org, user, customer, ctx


def test_1_to_5_plans_and_pricing_models(db: Session, org_and_user):
    """TEST 1 to 5: Test Flat, Per Unit, Volume, Tiered, and Package pricing models."""
    org, user, customer, ctx = org_and_user

    # TEST 1: Flat Pricing
    flat_plan = Offering(
        organization_id=org.id,
        name="Cloud Hosting Flat",
        sku="PLAN-FLAT-01",
        type="plan",
        pricing_model="flat",
        base_price=Decimal("5000.00"),
        tax_rate_pct=Decimal("18.00"),
        billing_frequency="monthly",
        is_active=True,
    )
    db.add(flat_plan)
    db.commit()
    db.refresh(flat_plan)

    res_flat = calculate_line_item_pricing(
        offering=flat_plan,
        quantity=Decimal("10"),
    )
    assert res_flat["subtotal"] == Decimal("5000.00")
    assert flat_plan.pricing_model == "flat"

    # TEST 2: Per Unit Pricing
    per_unit_plan = Offering(
        organization_id=org.id,
        name="User License Per Unit",
        sku="PLAN-UNIT-01",
        type="plan",
        pricing_model="per_unit",
        base_price=Decimal("500.00"),
        tax_rate_pct=Decimal("18.00"),
        billing_frequency="monthly",
        is_active=True,
    )
    db.add(per_unit_plan)
    db.commit()
    db.refresh(per_unit_plan)

    res_unit = calculate_line_item_pricing(
        offering=per_unit_plan,
        quantity=Decimal("5"),
    )
    assert res_unit["subtotal"] == Decimal("2500.00")
    assert res_unit["unit_price"] == Decimal("500.00")

    # TEST 3: Volume Pricing
    vol_plan = Offering(
        organization_id=org.id,
        name="Storage Volume",
        sku="PLAN-VOL-01",
        type="plan",
        pricing_model="volume",
        base_price=Decimal("100.00"),
        tax_rate_pct=Decimal("18.00"),
        billing_frequency="monthly",
        is_active=True,
        pricing_tiers=[
            {"min_qty": 1, "max_qty": 10, "unit_price": 100},
            {"min_qty": 11, "max_qty": 50, "unit_price": 80},
            {"min_qty": 51, "max_qty": None, "unit_price": 60},
        ],
    )
    db.add(vol_plan)
    db.commit()
    db.refresh(vol_plan)

    res_vol = calculate_line_item_pricing(
        offering=vol_plan,
        quantity=Decimal("20"),
    )
    # Rate for bracket 11-50 is 80 applied to all 20
    assert res_vol["unit_price"] == Decimal("80.00")
    assert res_vol["subtotal"] == Decimal("1600.00")

    # TEST 4: Tiered / Graduated Pricing
    tiered_plan = Offering(
        organization_id=org.id,
        name="API Calls Tiered",
        sku="PLAN-TIER-01",
        type="plan",
        pricing_model="tiered",
        base_price=Decimal("10.00"),
        tax_rate_pct=Decimal("18.00"),
        billing_frequency="monthly",
        is_active=True,
        pricing_tiers=[
            {"min_qty": 1, "max_qty": 10, "unit_price": 10},  # 10 * 10 = 100
            {"min_qty": 11, "max_qty": 20, "unit_price": 8},   # 10 * 8 = 80
            {"min_qty": 21, "max_qty": None, "unit_price": 5}, # 5 * 5 = 25
        ],
    )
    db.add(tiered_plan)
    db.commit()
    db.refresh(tiered_plan)

    res_tiered = calculate_line_item_pricing(
        offering=tiered_plan,
        quantity=Decimal("25"),
    )
    # (10 * 10) + (10 * 8) + (5 * 5) = 100 + 80 + 25 = 205
    assert res_tiered["subtotal"] == Decimal("205.00")

    # TEST 5: Package Pricing
    package_plan = Offering(
        organization_id=org.id,
        name="Support Package",
        sku="PLAN-PKG-01",
        type="plan",
        pricing_model="package",
        base_price=Decimal("1000.00"),
        tax_rate_pct=Decimal("18.00"),
        billing_frequency="monthly",
        is_active=True,
        pricing_tiers=[
            {"min_qty": 10, "max_qty": 10, "unit_price": 5000},
            {"min_qty": 25, "max_qty": 25, "unit_price": 10000},
            {"min_qty": 50, "max_qty": 50, "unit_price": 18000},
        ],
    )
    db.add(package_plan)
    db.commit()
    db.refresh(package_plan)

    res_pkg = calculate_line_item_pricing(
        offering=package_plan,
        quantity=Decimal("25"),
    )
    assert res_pkg["subtotal"] == Decimal("10000.00")


def test_6_to_8_quote_lifecycle_and_conversion_to_invoice(db: Session, org_and_user):
    """TEST 6 to 8: Create Quote, submit, approve, send, accept, and convert to invoice."""
    org, user, customer, ctx = org_and_user

    plan = Offering(
        organization_id=org.id,
        name="SaaS Pro Plan",
        sku="PLAN-SAAS-PRO",
        type="plan",
        pricing_model="per_unit",
        base_price=Decimal("1000.00"),
        tax_rate_pct=Decimal("18.00"),
        billing_frequency="monthly",
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    # TEST 6: Create Quote with 10% discount (which is > threshold 5% -> requires approval)
    quote_create = QuoteCreate(
        customer_id=customer.id,
        title="Enterprise SaaS Quote",
        issue_date=timezones.org_today(org),
        expiry_date=timezones.org_today(org) + timedelta(days=30),
        currency="INR",
        discount_pct=Decimal("10.00"),
        items=[
            LineItemIn(
                offering_id=plan.id,
                description="SaaS Pro Plan (10 seats)",
                quantity=Decimal("10"),
                unit_price=Decimal("1000.00"),
                tax_rate_pct=Decimal("18.00"),
                pricing_explanation="Per Unit 10 x ₹1,000",
            )
        ],
    )
    quote = quote_service.create_quote(db, ctx, quote_create)
    db.refresh(quote)

    assert quote.status == QuoteStatus.DRAFT
    # 10 * 1000 = 10000 subtotal, 10% discount = 1000, taxable = 9000, 18% tax = 1620, total = 10620
    assert quote.subtotal == Decimal("10000.00")
    assert quote.discount_amount == Decimal("1000.00")
    assert quote.tax_amount == Decimal("1620.00")
    assert quote.total == Decimal("10620.00")

    # TEST 7: Quote Lifecycle
    # Trigger send -> requires discount approval because discount (10%) > threshold (5%)
    quote = quote_service.send_quote(db, ctx, quote.id)
    assert quote.status == QuoteStatus.PENDING_APPROVAL

    # The requester cannot approve their own discount request
    from backend.app.core.exceptions import ForbiddenError

    with pytest.raises(ForbiddenError):
        quote_service.approve_quote(db, ctx, quote.id)

    # Another admin approves -> routed through approval_service; approval authorises, it does not send
    reviewer = User(email=f"reviewer_{uuid.uuid4().hex[:8]}@example.com", full_name="Reviewer", is_active=True)
    db.add(reviewer)
    db.flush()
    reviewer_membership = Membership(organization_id=org.id, user_id=reviewer.id, role="admin", status="active")
    db.add(reviewer_membership)
    db.commit()
    db.refresh(reviewer_membership)
    reviewer_ctx = CurrentContext(
        user=reviewer, organization=org, membership=reviewer_membership, ip_address=None, user_agent=None
    )
    quote = quote_service.approve_quote(db, reviewer_ctx, quote.id)
    assert quote.status == QuoteStatus.APPROVED
    assert quote.accepted_at is None

    # Staff send the approved quote
    quote = quote_service.send_quote(db, ctx, quote.id)
    assert quote.status == QuoteStatus.SENT

    # Mark viewed
    quote = quote_service.mark_viewed(db, ctx, quote.id)
    assert quote.status == QuoteStatus.VIEWED

    # The customer accepts on the hosted link
    quote = quote_service.public_accept(db, quote.public_token, "E2E Customer")
    assert quote.status == QuoteStatus.ACCEPTED

    # TEST 8: Convert Quote to Invoice
    conv_data = QuoteConvertIn(
        issue_date=timezones.org_today(org),
        due_date=timezones.org_today(org) + timedelta(days=30),
    )
    inv_out = quote_service.convert_to_invoice(db, ctx, quote.id, conv_data)
    db.refresh(quote)

    invoice = db.scalars(quote_service.select(Invoice).where(Invoice.id == quote.converted_invoice_id)).first()

    # Verify quote state updated to INVOICED
    assert quote.status in [QuoteStatus.INVOICED, QuoteStatus.CONVERTED]

    # Verify all invoice properties match quote
    assert invoice.customer_id == customer.id
    assert invoice.quote_id == quote.id
    assert invoice.subtotal == Decimal("10000.00")
    assert invoice.discount_amount == Decimal("1000.00")
    assert invoice.tax_amount == Decimal("1620.00")
    assert invoice.total == Decimal("10620.00")
    assert invoice.amount_due == Decimal("10620.00")
    assert invoice.amount_paid == Decimal("0.00")
    assert len(invoice.items) == 1
    assert invoice.items[0].offering_id == plan.id
    assert invoice.items[0].pricing_explanation == "Per Unit 10 x ₹1,000"


def test_9_to_11_invoice_lifecycle_payments_and_overdue(db: Session, org_and_user):
    """TEST 9 to 11: Invoice send, partial payment, full payment, and overdue status."""
    org, user, customer, ctx = org_and_user

    # Create Invoice directly
    inv_create = InvoiceCreate(
        customer_id=customer.id,
        issue_date=timezones.org_today(org) - timedelta(days=40),
        due_date=timezones.org_today(org) - timedelta(days=10),
        currency="INR",
        items=[
            LineItemIn(
                description="Consulting Retainer",
                quantity=Decimal("1"),
                unit_price=Decimal("5000.00"),
                tax_rate_pct=Decimal("18.00"),
            )
        ],
    )
    invoice = invoice_service.create_invoice(db, ctx, inv_create)
    db.refresh(invoice)

    # Total = 5000 + 18% = 5900
    assert invoice.total == Decimal("5900.00")
    assert invoice.amount_due == Decimal("5900.00")
    assert invoice.status == InvoiceStatus.DRAFT

    # Send Invoice
    invoice = invoice_service.send_invoice(db, ctx, invoice)
    assert invoice.status == InvoiceStatus.SENT

    # TEST 10: Partial Payment (Pay ₹2,000)
    pay_in = RecordPaymentIn(
        amount=Decimal("2000.00"),
        # Payment dates are checked against the server (UTC) date, invoice dates against the org's day.
        paid_at=timezones.utc_today(),
        method="bank_transfer",
        reference="TXN-PARTIAL-01",
    )
    payment_service.record_invoice_payment(db, ctx, invoice, pay_in)
    db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PARTIALLY_PAID
    assert invoice.amount_paid == Decimal("2000.00")
    assert invoice.amount_due == Decimal("3900.00")

    # TEST 9: Full Payment (Pay remaining ₹3,900)
    pay_full = RecordPaymentIn(
        amount=Decimal("3900.00"),
        paid_at=timezones.utc_today(),
        method="upi",
        reference="TXN-FULL-02",
    )
    payment_service.record_invoice_payment(db, ctx, invoice, pay_full)
    db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.amount_paid == Decimal("5900.00")
    assert invoice.amount_due == Decimal("0.00")

    # TEST 11: Past due unpaid invoice calculation
    overdue_create = InvoiceCreate(
        customer_id=customer.id,
        issue_date=timezones.org_today(org) - timedelta(days=30),
        due_date=timezones.org_today(org) - timedelta(days=5),
        currency="INR",
        items=[
            LineItemIn(
                description="Server Maintenance",
                quantity=Decimal("1"),
                unit_price=Decimal("2000.00"),
                tax_rate_pct=Decimal("0.00"),
            )
        ],
    )
    overdue_inv = invoice_service.create_invoice(db, ctx, overdue_create)
    invoice_service.send_invoice(db, ctx, overdue_inv)
    db.refresh(overdue_inv)

    # Recompute status or check overdue
    invoice_service.recompute_invoice(db, overdue_inv, ctx=ctx)
    db.refresh(overdue_inv)
    assert overdue_inv.status == InvoiceStatus.OVERDUE


def test_12_and_13_historical_pricing_snapshot_preservation(db: Session, org_and_user):
    """TEST 12 & 13: Changing Plan price after Quote/Invoice creation preserves historical snapshot."""
    org, user, customer, ctx = org_and_user

    # Create Plan at ₹1,000
    plan = Offering(
        organization_id=org.id,
        name="Dedicated Server",
        sku="PLAN-DEDICATED-01",
        type="plan",
        pricing_model="per_unit",
        base_price=Decimal("1000.00"),
        tax_rate_pct=Decimal("18.00"),
        billing_frequency="monthly",
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    # Create Quote with Plan
    quote = quote_service.create_quote(
        db,
        ctx,
        QuoteCreate(
            customer_id=customer.id,
            title="Historical Price Quote",
            issue_date=timezones.org_today(org),
            expiry_date=timezones.org_today(org) + timedelta(days=30),
            currency="INR",
            discount_pct=Decimal("0.00"),
            items=[
                LineItemIn(
                    offering_id=plan.id,
                    description="Dedicated Server",
                    quantity=Decimal("2"),
                    unit_price=Decimal("1000.00"),
                    tax_rate_pct=Decimal("18.00"),
                )
            ],
        ),
    )
    db.refresh(quote)

    # Create Invoice directly with Plan
    invoice = invoice_service.create_invoice(
        db,
        ctx,
        InvoiceCreate(
            customer_id=customer.id,
            issue_date=timezones.org_today(org),
            due_date=timezones.org_today(org) + timedelta(days=30),
            currency="INR",
            items=[
                LineItemIn(
                    offering_id=plan.id,
                    description="Dedicated Server",
                    quantity=Decimal("2"),
                    unit_price=Decimal("1000.00"),
                    tax_rate_pct=Decimal("18.00"),
                )
            ],
        ),
    )
    db.refresh(invoice)

    # Mutate the Offering base price from ₹1,000 to ₹5,000
    plan.base_price = Decimal("5000.00")
    db.add(plan)
    db.commit()
    db.refresh(plan)

    # Re-fetch quote and invoice from DB
    db.refresh(quote)
    db.refresh(invoice)

    # TEST 12: Verify quote retains original snapshot
    assert quote.subtotal == Decimal("2000.00")
    assert quote.total == Decimal("2360.00")
    assert quote.items[0].unit_price == Decimal("1000.00")

    # TEST 13: Verify invoice retains original snapshot
    assert invoice.subtotal == Decimal("2000.00")
    assert invoice.total == Decimal("2360.00")
    assert invoice.items[0].unit_price == Decimal("1000.00")
