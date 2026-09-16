"""Field-level validation added by the form-validation audit.

Pure schema-level tests (no DB/HTTP) for the Pydantic rules that guard
financial and statutory fields. Each rule here is also expected to be
reachable through its real endpoint — see test_customers.py, test_catalog.py,
test_quotes.py, test_invoices.py, test_payments.py, test_projects.py,
test_expenses.py and test_timesheets.py for the end-to-end paths.
"""
from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.app.schemas.common_refs import LineItemIn
from backend.app.schemas.customers import ContactIn, CustomerCreate
from backend.app.schemas.catalog import PlanCreate, ProductCreate
from backend.app.schemas.catalog_cpq import OfferingCreate
from backend.app.schemas.expenses import ExpenseCreate, RecurringExpenseCreate
from backend.app.schemas.invoices import InvoiceCreate, RecordPaymentIn
from backend.app.schemas.organization import OrganizationUpdate
from backend.app.schemas.payments import PaymentCreate
from backend.app.schemas.portal import CustomerPortalSettingsUpdate
from backend.app.schemas.projects import ProjectCreate
from backend.app.schemas.quotes import QuoteCreate
from backend.app.schemas.timesheets import TimeEntryCreate


def _item(**overrides):
    data = {"description": "Consulting", "quantity": "1", "unit_price": "100", "tax_rate_pct": "18"}
    data.update(overrides)
    return data


# --- Line items (Priority 1) --------------------------------------------------------------


class TestLineItemValidation:
    def test_zero_quantity_rejected(self):
        with pytest.raises(ValidationError):
            LineItemIn(**_item(quantity="0"))

    def test_negative_quantity_rejected(self):
        with pytest.raises(ValidationError):
            LineItemIn(**_item(quantity="-1"))

    def test_negative_unit_price_rejected(self):
        with pytest.raises(ValidationError):
            LineItemIn(**_item(unit_price="-5"))

    def test_tax_rate_over_100_rejected(self):
        with pytest.raises(ValidationError):
            LineItemIn(**_item(tax_rate_pct="150"))

    def test_negative_tax_rate_rejected(self):
        with pytest.raises(ValidationError):
            LineItemIn(**_item(tax_rate_pct="-1"))

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            LineItemIn(**_item(description=""))

    def test_whitespace_only_description_rejected(self):
        with pytest.raises(ValidationError):
            LineItemIn(**_item(description="   "))

    def test_description_too_long_rejected(self):
        with pytest.raises(ValidationError):
            LineItemIn(**_item(description="x" * 501))

    @pytest.mark.parametrize(
        "description",
        ["Server Package 2", "Windows Server 2026", "Plan 360", "A&B Enterprises 2.0"],
    )
    def test_legitimate_descriptions_with_numbers_accepted(self, description):
        item = LineItemIn(**_item(description=description))
        assert item.description == description

    def test_nan_and_infinite_amounts_rejected(self):
        with pytest.raises(ValidationError):
            LineItemIn(**_item(unit_price="nan"))
        with pytest.raises(ValidationError):
            LineItemIn(**_item(unit_price="Infinity"))

    def test_non_numeric_text_rejected(self):
        with pytest.raises(ValidationError):
            LineItemIn(**_item(unit_price="100abc"))


# --- Customers (Priority 2) -------------------------------------------------------------


class TestCustomerValidation:
    def test_numeric_only_display_name_rejected(self):
        with pytest.raises(ValidationError):
            CustomerCreate(display_name="123456")

    def test_whitespace_only_display_name_rejected(self):
        with pytest.raises(ValidationError):
            CustomerCreate(display_name="   ")

    @pytest.mark.parametrize(
        "name", ["Rooman Technologies 2.0", "A&B Enterprises", "St. John's Hospital", "Plan 360"]
    )
    def test_legitimate_business_names_accepted(self, name):
        assert CustomerCreate(display_name=name).display_name == name

    def test_short_name_still_accepted(self):
        """A single letter/initial is a legitimate short name, not garbage input."""
        assert CustomerCreate(display_name="A").display_name == "A"

    def test_malformed_email_rejected(self):
        with pytest.raises(ValidationError):
            CustomerCreate(display_name="Acme", email="not-an-email")

    @pytest.mark.parametrize("phone", ["abcdef", "call-me-maybe", "123"])
    def test_invalid_phone_rejected(self, phone):
        with pytest.raises(ValidationError):
            CustomerCreate(display_name="Acme", phone=phone)

    @pytest.mark.parametrize("phone", ["+91 98765 43210", "(022) 4567-8900", "9876543210"])
    def test_legitimate_phone_formats_accepted(self, phone):
        assert CustomerCreate(display_name="Acme", phone=phone).phone == phone

    def test_invalid_website_rejected(self):
        with pytest.raises(ValidationError):
            CustomerCreate(display_name="Acme", website="hello world")

    def test_website_without_scheme_gets_normalized(self):
        c = CustomerCreate(display_name="Acme", website="acme.com")
        assert c.website == "https://acme.com"

    @pytest.mark.parametrize("gstin", ["INVALIDGSTIN", "29ABCDE1234F1Z", "1234567890123456"])
    def test_malformed_gstin_rejected(self, gstin):
        with pytest.raises(ValidationError):
            CustomerCreate(display_name="Acme", gstin=gstin)

    def test_valid_gstin_accepted_and_uppercased(self):
        c = CustomerCreate(display_name="Acme", gstin="29abcde1234f1z5")
        assert c.gstin == "29ABCDE1234F1Z5"

    @pytest.mark.parametrize("pan", ["INVALID", "ABCDE12345", "12345ABCDE"])
    def test_malformed_pan_rejected(self, pan):
        with pytest.raises(ValidationError):
            CustomerCreate(display_name="Acme", pan=pan)

    def test_valid_pan_accepted_and_uppercased(self):
        c = CustomerCreate(display_name="Acme", pan="abcde1234f")
        assert c.pan == "ABCDE1234F"

    def test_invalid_billing_country_rejected(self):
        with pytest.raises(ValidationError):
            CustomerCreate(display_name="Acme", billing_country="12")

    def test_valid_billing_country_uppercased(self):
        c = CustomerCreate(display_name="Acme", billing_country="in")
        assert c.billing_country == "IN"

    def test_contact_garbage_phone_rejected(self):
        with pytest.raises(ValidationError):
            ContactIn(name="Jane Doe", phone="abcdef")

    def test_contact_short_name_still_accepted(self):
        assert ContactIn(name="A").name == "A"


# --- Catalog: products & plans (Priority 3) ----------------------------------------------


class TestCatalogValidation:
    def test_malformed_hsn_sac_rejected(self):
        with pytest.raises(ValidationError):
            ProductCreate(name="Widget", hsn_sac_code="ABCD")

    def test_valid_hsn_sac_accepted(self):
        assert ProductCreate(name="Widget", hsn_sac_code="998314").hsn_sac_code == "998314"

    def test_sku_with_spaces_rejected(self):
        with pytest.raises(ValidationError):
            ProductCreate(name="Widget", sku="bad sku with spaces")

    def test_tax_rate_over_100_rejected_on_product(self):
        with pytest.raises(ValidationError):
            ProductCreate(name="Widget", tax_rate_pct="101")

    def test_offering_sku_and_hsn_validated(self):
        with pytest.raises(ValidationError):
            OfferingCreate(name="Widget", base_price="10", sku="has spaces")
        with pytest.raises(ValidationError):
            OfferingCreate(name="Widget", base_price="10", hsn_sac_code="not-digits")

    def test_plan_interval_count_must_be_positive(self):
        with pytest.raises(ValidationError):
            PlanCreate(
                product_id="p1", name="Starter", code="STARTER", billing_interval="monthly",
                pricing_model="per_unit", unit_amount="100", interval_count=0,
            )

    def test_plan_negative_unit_amount_rejected(self):
        with pytest.raises(ValidationError):
            PlanCreate(
                product_id="p1", name="Starter", code="STARTER", billing_interval="monthly",
                pricing_model="per_unit", unit_amount="-10",
            )

    def test_plan_negative_trial_days_rejected(self):
        with pytest.raises(ValidationError):
            PlanCreate(
                product_id="p1", name="Starter", code="STARTER", billing_interval="monthly",
                pricing_model="per_unit", unit_amount="10", trial_days=-1,
            )


# --- Quotes / invoices (Priority 4) -------------------------------------------------------


class TestQuoteInvoiceValidation:
    def test_quote_expiry_before_issue_rejected(self):
        with pytest.raises(ValidationError):
            QuoteCreate(
                customer_id="c1", issue_date="2026-09-16", expiry_date="2026-01-01", items=[_item()],
            )

    def test_quote_discount_over_100_rejected(self):
        with pytest.raises(ValidationError):
            QuoteCreate(customer_id="c1", discount_pct="150", items=[_item()])

    def test_invoice_requires_at_least_one_item(self):
        with pytest.raises(ValidationError):
            InvoiceCreate(customer_id="c1", items=[])

    def test_invoice_notes_over_technical_limit_rejected(self):
        with pytest.raises(ValidationError):
            InvoiceCreate(customer_id="c1", items=[_item()], notes="x" * 10001)

    def test_invoice_line_item_negative_quantity_rejected(self):
        with pytest.raises(ValidationError):
            InvoiceCreate(customer_id="c1", items=[_item(quantity="-2")])


# --- Payments / refunds (Priority 5) ------------------------------------------------------


class TestPaymentValidation:
    def test_zero_amount_rejected(self):
        with pytest.raises(ValidationError):
            PaymentCreate(customer_id="c1", amount="0", method="cash")

    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            PaymentCreate(customer_id="c1", amount="-10", method="cash")

    def test_future_paid_at_rejected(self):
        future = (datetime.now() + timedelta(days=10)).isoformat()
        with pytest.raises(ValidationError):
            PaymentCreate(customer_id="c1", amount="100", method="cash", paid_at=future)

    def test_today_paid_at_accepted(self):
        p = PaymentCreate(customer_id="c1", amount="100", method="cash", paid_at=datetime.now().isoformat())
        assert p.amount == 100

    def test_record_payment_future_date_rejected(self):
        future = (datetime.now() + timedelta(days=10)).isoformat()
        with pytest.raises(ValidationError):
            RecordPaymentIn(amount="100", method="cash", paid_at=future)


# --- Projects (Priority 7) ----------------------------------------------------------------


class TestProjectValidation:
    def test_end_date_before_start_date_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(name="Website Revamp", start_date="2026-09-16", end_date="2026-01-01")

    def test_negative_budget_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(name="Website Revamp", budget="-100")

    def test_whitespace_only_name_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(name="   ")

    def test_malformed_budget_string_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(name="Website Revamp", budget="100abc")


# --- Expenses (Priority 8) ----------------------------------------------------------------


class TestExpenseValidation:
    def test_zero_amount_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(name="Taxi", date="2026-09-16", category="Travel", amount="0")

    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(name="Taxi", date="2026-09-16", category="Travel", amount="-10")

    def test_tax_rate_over_100_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(name="Taxi", date="2026-09-16", category="Travel", amount="100", tax_rate="150")

    def test_whitespace_only_name_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(name="   ", date="2026-09-16", category="Travel", amount="100")

    def test_recurring_end_before_start_rejected(self):
        with pytest.raises(ValidationError):
            RecurringExpenseCreate(
                name="Rent", category="Office", amount="5000", start_date="2026-09-16", end_date="2026-01-01",
            )


# --- Timesheets (Priority 9) --------------------------------------------------------------


class TestTimesheetValidation:
    def test_future_date_rejected(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        with pytest.raises(ValidationError):
            TimeEntryCreate(date=future, duration_hours="2", description="Work")

    def test_zero_duration_rejected(self):
        with pytest.raises(ValidationError):
            TimeEntryCreate(date=date.today().isoformat(), duration_hours="0", description="Work")

    def test_duration_over_24_hours_rejected(self):
        with pytest.raises(ValidationError):
            TimeEntryCreate(date=date.today().isoformat(), duration_hours="25", description="Work")

    def test_whitespace_only_description_rejected(self):
        with pytest.raises(ValidationError):
            TimeEntryCreate(date=date.today().isoformat(), duration_hours="2", description="   ")

    def test_negative_billing_rate_rejected(self):
        with pytest.raises(ValidationError):
            TimeEntryCreate(
                date=date.today().isoformat(), duration_hours="2", description="Work", billing_rate="-1",
            )

    def test_description_with_numbers_accepted(self):
        entry = TimeEntryCreate(
            date=date.today().isoformat(), duration_hours="2", description="Migrated Plan 360 to Windows Server 2026",
        )
        assert "2026" in entry.description


# --- Profile / organization / portal (Priority 10 & 11) -----------------------------------


class TestOrgProfilePortalValidation:
    def test_organization_invalid_phone_rejected(self):
        with pytest.raises(ValidationError):
            OrganizationUpdate(phone="not-a-phone-at-all")

    def test_organization_invalid_website_rejected(self):
        with pytest.raises(ValidationError):
            OrganizationUpdate(website="just some text")

    def test_organization_malformed_gstin_rejected(self):
        with pytest.raises(ValidationError):
            OrganizationUpdate(gstin="INVALIDGSTIN")

    def test_organization_malformed_pan_rejected(self):
        with pytest.raises(ValidationError):
            OrganizationUpdate(pan="INVALID")

    def test_portal_slug_with_spaces_rejected(self):
        with pytest.raises(ValidationError):
            CustomerPortalSettingsUpdate(portal_url_slug="not a slug!")

    def test_portal_slug_normalized_to_lowercase(self):
        s = CustomerPortalSettingsUpdate(portal_url_slug="Acme-Corp")
        assert s.portal_url_slug == "acme-corp"
