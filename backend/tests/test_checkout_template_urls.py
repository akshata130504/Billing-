"""BUG-47: checkout template redirect/logo URLs are validated when saved, not only when a
session is created. BUG-60: a new checkout session returns an absolute link.

External-host allow-listing for redirects is a product decision; only the scheme, host
and obviously unsafe characters are enforced here.
"""
import pytest

from backend.app.core.config import settings

TEMPLATES = "/api/v1/checkout/templates"


def _create(client, headers, **extra):
    return client.post(TEMPLATES, headers=headers, json={"name": "Brand page", **extra})


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        " JavaScript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "//evil.example.com/steal",
        "/relative/thanks",
        "ftp://example.com/x",
        "https://",
        "https://user:pass@example.com/",
    ],
)
def test_unsafe_redirect_url_rejected_on_create(client, tenant, auth_headers, url):
    res = _create(client, auth_headers, redirect_url=url)
    assert res.status_code == 422, res.text


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "data:image/svg+xml;base64,PHN2Zz4=", "/uploads/../secret.png", "//evil.example.com/l.png"],
)
def test_unsafe_logo_url_rejected_on_create(client, tenant, auth_headers, url):
    res = _create(client, auth_headers, logo_url=url)
    assert res.status_code == 422, res.text


@pytest.mark.parametrize(
    "redirect,logo",
    [
        ("https://shop.example.com/thanks", "/uploads/logos/acme.png"),
        ("http://shop.example.com/done", "https://cdn.example.com/l.png"),
        (None, None),
    ],
)
def test_safe_urls_are_accepted(client, tenant, auth_headers, redirect, logo):
    res = _create(client, auth_headers, redirect_url=redirect, logo_url=logo)
    assert res.status_code == 201, res.text
    assert res.json()["redirect_url"] == redirect
    assert res.json()["logo_url"] == logo


def test_update_schema_validates_the_same_way():
    """There is no update endpoint yet; the update schema must not become a bypass."""
    from pydantic import ValidationError

    from backend.app.schemas.checkout import CheckoutTemplateUpdate

    with pytest.raises(ValidationError):
        CheckoutTemplateUpdate(redirect_url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        CheckoutTemplateUpdate(logo_url="javascript:alert(1)")
    assert CheckoutTemplateUpdate(redirect_url="https://ok.example.com").redirect_url == "https://ok.example.com"


def test_checkout_session_link_is_absolute(client, tenant, auth_headers):
    customer = tenant.customer()
    invoice = tenant.invoice(customer, amount="500.00")
    res = client.post(
        "/api/v1/checkout/sessions",
        headers=auth_headers,
        json={"purpose": "invoice_payment", "invoice_id": invoice.id},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["checkout_url"] == f"{settings.FRONTEND_URL.rstrip('/')}/checkout/{body['token']}"
    assert body["checkout_url"].startswith(("http://", "https://"))
