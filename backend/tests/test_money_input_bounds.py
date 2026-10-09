"""BUG-19 / BUG-30: money inputs are bounded to NUMERIC(14, 2) and reject more than
two decimal places with a 422, instead of overflowing (500) or silently rounding."""
from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.schemas.credits import CreditApplicationIn, CreditNoteLineIn
from backend.app.schemas.expenses import ExpenseUpdate, RecurringExpenseCreate, RecurringExpenseUpdate
from backend.app.schemas.invoices import RecordPaymentIn
from backend.app.schemas.payments import PaymentCreate, RefundIn
from backend.app.schemas.projects import ProjectCreate
from backend.app.schemas.timesheets import TimeEntryCreate, TimeEntryUpdate

TOO_BIG = ["1e15", "1000000000000.00"]
TOO_PRECISE = ["1.005", "0.001"]


def _expense(amount):
    return {"name": "Cloud", "category": "Hosting", "date": date.today().isoformat(), "amount": amount}


@pytest.mark.parametrize("amount", [1e15, "1e15", "1000000000000", 1.005, "10.999"])
def test_expense_api_rejects_out_of_range_amount_with_422(client, auth_headers, amount):
    res = client.post("/api/v1/expenses", headers=auth_headers, json=_expense(amount))
    assert res.status_code == 422, res.text


def test_expense_api_accepts_max_money(client, auth_headers):
    res = client.post("/api/v1/expenses", headers=auth_headers, json=_expense("999999999999.99"))
    assert res.status_code == 201, res.text


def test_payment_api_rejects_three_decimals_instead_of_rounding(client, tenant, auth_headers):
    customer = tenant.customer()
    body = {"customer_id": customer.id, "amount": 1.005, "method": "cash"}
    res = client.post("/api/v1/payments", headers=auth_headers, json=body)
    assert res.status_code == 422, res.text
    body["amount"] = "1.01"
    res = client.post("/api/v1/payments", headers=auth_headers, json=body)
    assert res.status_code == 201, res.text
    assert res.json()["amount"] == "1.01"


_TODAY = date.today().isoformat()
MONEY_INPUTS = {
    "payment": lambda v: PaymentCreate(customer_id="c1", amount=v, method="cash"),
    "record_payment": lambda v: RecordPaymentIn(amount=v, method="cash"),
    "refund": lambda v: RefundIn(amount=v),
    "credit_note_line": lambda v: CreditNoteLineIn(description="Credit", amount=v),
    "credit_application": lambda v: CreditApplicationIn(invoice_id="i1", amount=v),
    "expense_update": lambda v: ExpenseUpdate(amount=v),
    "expense_billable_amount": lambda v: ExpenseUpdate(billable_amount=v),
    "recurring_expense": lambda v: RecurringExpenseCreate(name="Rent", category="Office", amount=v, start_date=_TODAY),
    "recurring_expense_update": lambda v: RecurringExpenseUpdate(amount=v),
    "project_budget": lambda v: ProjectCreate(name="Website", budget=v),
    "time_entry_rate": lambda v: TimeEntryCreate(date=_TODAY, duration_hours="1", description="Work", billing_rate=v),
    "time_entry_update_rate": lambda v: TimeEntryUpdate(billing_rate=v),
}


@pytest.mark.parametrize("bad", TOO_BIG + TOO_PRECISE)
@pytest.mark.parametrize("field", sorted(MONEY_INPUTS))
def test_money_schemas_reject_overflow_and_extra_decimals(field, bad):
    with pytest.raises(ValidationError):
        MONEY_INPUTS[field](bad)


def test_billing_rate_bounded_so_a_full_day_fits_the_amount_column():
    with pytest.raises(ValidationError):
        TimeEntryCreate(date=date.today().isoformat(), duration_hours="24", description="Work", billing_rate="99999999999")
    entry = TimeEntryCreate(date=date.today().isoformat(), duration_hours="24", description="Work", billing_rate="9999999999.99")
    assert entry.billing_rate * 24 < 10**12


def test_two_decimal_money_still_accepted():
    assert PaymentCreate(customer_id="c1", amount="999999999999.99", method="cash").amount
    assert RecordPaymentIn(amount="1.50", method="cash").amount
    assert CreditNoteLineIn(description="Credit", amount="10.25").amount
