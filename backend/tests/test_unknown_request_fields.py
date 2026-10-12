"""BUG-46: state-changing request bodies refuse unknown fields (422) instead of silently
ignoring them - a misspelt `effective` must never apply a subscription change immediately."""
import pytest

from backend.app.models import Subscription
from backend.app.schemas import checkout, credits, customization, invoices, payments, proration, quotes, subscriptions


def _subscription(client, tenant, auth_headers):
    customer = tenant.customer()
    _, plan_basic = tenant.product_with_plan(unit_amount="1000.00")
    _, plan_prem = tenant.product_with_plan(unit_amount="2500.00")
    res = client.post(
        "/api/v1/subscriptions",
        json={"customer_id": customer.id, "plan_id": plan_basic.id, "quantity": 1},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"], plan_basic, plan_prem


def test_misspelt_effective_type_is_refused_and_nothing_changes(client, tenant, auth_headers, db):
    sub_id, plan_basic, plan_prem = _subscription(client, tenant, auth_headers)
    res = client.post(
        f"/api/v1/subscriptions/{sub_id}/changes",
        json={"target_plan_id": plan_prem.id, "effective": "end_of_period"},
        headers=auth_headers,
    )
    assert res.status_code == 422, res.text
    assert "effective" in res.text
    db.expire_all()
    assert db.get(Subscription, sub_id).plan_id == plan_basic.id


def test_checkout_template_unknown_field_is_refused(client, auth_headers):
    res = client.post(
        "/api/v1/checkout/templates",
        json={"name": "Default", "success_url": "https://example.test/thanks"},
        headers=auth_headers,
    )
    assert res.status_code == 422, res.text
    assert "success_url" in res.text
    ok = client.post("/api/v1/checkout/templates", json={"name": "Default", "redirect_url": "https://example.test/thanks"},
                     headers=auth_headers)
    assert ok.status_code == 201, ok.text


def test_payment_unknown_field_is_refused(client, tenant, auth_headers):
    body = {"customer_id": tenant.customer().id, "amount": "10.00", "method": "cash", "refrence": "UTR-1"}
    res = client.post("/api/v1/payments", headers=auth_headers, json=body)
    assert res.status_code == 422, res.text


@pytest.mark.parametrize(
    "model, data",
    [
        (proration.SubscriptionChangePreviewIn, {"target_plan_id": "p"}),
        (proration.SubscriptionChangeApplyIn, {"target_plan_id": "p"}),
        (subscriptions.SubscriptionCancelIn, {}),
        (payments.PaymentCreate, {"customer_id": "c", "amount": "1", "method": "cash"}),
        (payments.PaymentUpdate, {}),
        (payments.RefundIn, {"amount": "1"}),
        (payments.AllocationsPut, {"allocations": []}),
        (invoices.InvoiceCreate, {"customer_id": "c", "items": [{"description": "x"}]}),
        (invoices.InvoiceUpdate, {}),
        (invoices.InvoiceVoidIn, {"reason": "x"}),
        (invoices.RecordPaymentIn, {"amount": "1", "method": "cash"}),
        (quotes.QuoteUpdate, {}),
        (quotes.QuoteDeclineIn, {}),
        (credits.CreditNoteCreateIn, {"customer_id": "c", "lines": [{"description": "x", "amount": "1"}]}),
        (credits.CreditApplicationIn, {"invoice_id": "i", "amount": "1"}),
        (checkout.CheckoutTemplateCreate, {"name": "T"}),
        (checkout.CheckoutTemplateUpdate, {}),
        (checkout.CheckoutSessionCreate, {}),
        (customization.DocumentTemplateUpdate, {}),
        (customization.AutomationRuleUpdate, {}),
        (customization.AutomationScheduleUpdate, {}),
    ],
)
def test_request_schemas_forbid_unknown_fields(model, data):
    model(**data)  # the minimal valid body is accepted
    with pytest.raises(Exception) as exc:
        model(**data, definitely_not_a_field=1)
    assert "definitely_not_a_field" in str(exc.value)


def test_nested_line_items_forbid_unknown_fields():
    with pytest.raises(Exception):
        invoices.InvoiceCreate(customer_id="c", items=[{"description": "x", "unit_prise": "5"}])
    with pytest.raises(Exception):
        credits.CreditNoteCreateIn(customer_id="c", lines=[{"description": "x", "amount": "1", "taxrate": "5"}])
