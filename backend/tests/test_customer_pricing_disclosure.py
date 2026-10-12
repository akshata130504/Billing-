"""Internal pricing workings never reach the customer (BUG-41, BUG-04, BUG-06).

Catalog lines carry `pricing_explanation` (catalog base price, price-book adjustment, tier
workings). It is for staff only: customer PDFs, the hosted quote/invoice pages, the customer
portal and hosted checkout must not expose it, and customer documents must not print markup.
"""
import io
import json
from datetime import date, timedelta

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


from backend.app.models import MemberRole
from backend.app.services import customer_portal_service

# What the quote/invoice editors store for a catalog line (JSON.stringify of the simulator result).
EXPLANATION = json.dumps(
    {
        "catalog_base_price": "1200.00",
        "price_book_adjustment": "-200.00",
        "effective_unit_price": "1000.00",
        "tier_explanation": "Volume tier 1-10 @ 1000.00",
        "subtotal_pre_discount": "2000.00",
        "tax": {"rate_pct": "18", "amount": "324.00"},
    }
)
FORBIDDEN = ("pricing_explanation", "catalog_base_price", "price_book_adjustment", "<br/>", "<font", "&lt;")


def _items():
    return [
        {
            "description": "Analytics Seat",
            "quantity": "2",
            "unit_price": "1000.00",
            "tax_rate_pct": "18",
            "pricing_explanation": EXPLANATION,
        },
        {"description": "Onboarding", "quantity": "1", "unit_price": "500.00", "tax_rate_pct": "18"},
    ]


def _pdf_text(content: bytes) -> str:
    if PdfReader is not None:
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    import re, zlib
    text_chunks = []
    for stream in re.findall(rb"stream[\r\n]+(.*?)[\r\n]+endstream", content, re.DOTALL):
        try:
            decomp = zlib.decompress(stream)
        except Exception:
            decomp = stream
        for match in re.findall(rb"\((.*?)\)\s*Tj", decomp):
            text_chunks.append(match.decode("latin1", errors="ignore"))
    return "\n".join(text_chunks)



def _keys(value, found=None):
    """Every dict key at any depth of a JSON payload."""
    found = set() if found is None else found
    if isinstance(value, dict):
        for k, v in value.items():
            found.add(k)
            _keys(v, found)
    elif isinstance(value, list):
        for v in value:
            _keys(v, found)
    return found


def _assert_no_pricing_internals(payload):
    assert "pricing_explanation" not in _keys(payload)
    text = json.dumps(payload)
    assert "catalog_base_price" not in text
    assert "price_book_adjustment" not in text


def _quote(client, headers, customer):
    body = {"customer_id": customer.id, "title": "Catalog deal", "items": _items(), "discount_pct": "10"}
    resp = client.post("/api/v1/quotes", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    quote = resp.json()
    # Staff still see the explanation on the internal API.
    assert quote["items"][0]["pricing_explanation"] == EXPLANATION
    return quote


def _invoice(client, headers, customer):
    body = {
        "customer_id": customer.id,
        "issue_date": date.today().isoformat(),
        "due_date": (date.today() + timedelta(days=15)).isoformat(),
        "items": _items(),
        "discount_pct": "10",
    }
    resp = client.post("/api/v1/invoices", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    inv = resp.json()
    assert inv["items"][0]["pricing_explanation"] == EXPLANATION
    sent = client.post(f"/api/v1/invoices/{inv['id']}/send", headers=headers)
    assert sent.status_code == 200, sent.text
    return sent.json()


# --- BUG-41: customer PDFs ---------------------------------------------------------------------


def test_quote_pdf_prints_description_without_pricing_internals_or_markup(client, tenant, auth_headers):
    quote = _quote(client, auth_headers, tenant.customer())
    resp = client.get(f"/api/v1/quotes/{quote['id']}/pdf", headers=auth_headers)
    assert resp.status_code == 200
    text = _pdf_text(resp.content)
    assert "Analytics Seat" in text
    assert "Discount" in text
    for needle in FORBIDDEN + ("Volume tier", "1200.00"):
        assert needle not in text, needle


def test_invoice_pdf_prints_description_without_pricing_internals_or_markup(client, tenant, auth_headers):
    inv = _invoice(client, auth_headers, tenant.customer())
    resp = client.get(f"/api/v1/invoices/{inv['id']}/pdf", headers=auth_headers)
    assert resp.status_code == 200
    text = _pdf_text(resp.content)
    assert "Analytics Seat" in text
    for needle in FORBIDDEN + ("Volume tier", "1200.00"):
        assert needle not in text, needle


# --- BUG-04: public / customer-facing payloads ------------------------------------------------


def test_public_quote_payload_has_no_pricing_explanation(client, tenant, auth_headers):
    quote = _quote(client, auth_headers, tenant.customer())
    sent = client.post(f"/api/v1/quotes/{quote['id']}/send", headers=auth_headers)
    assert sent.status_code == 200, sent.text
    token = sent.json()["public_url"].rsplit("/", 1)[1]

    resp = client.get(f"/api/v1/public/quotes/{token}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["description"] == "Analytics Seat"
    _assert_no_pricing_internals(resp.json())


def test_public_invoice_payload_has_no_pricing_explanation(client, tenant, auth_headers):
    inv = _invoice(client, auth_headers, tenant.customer())
    token = inv["public_url"].rsplit("/", 1)[1]

    resp = client.get(f"/api/v1/public/invoices/{token}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["description"] == "Analytics Seat"
    _assert_no_pricing_internals(resp.json())


def test_portal_and_checkout_payloads_have_no_pricing_explanation(client, tenant, auth_headers, monkeypatch):
    customer = tenant.customer(email="pricing.portal@example.com")
    inv = _invoice(client, auth_headers, customer)

    links = []
    monkeypatch.setattr(customer_portal_service, "send_email", lambda **kw: links.append(kw["text_body"]) or True)
    assert client.post(f"/api/v1/customers/{customer.id}/portal-invite", headers=auth_headers, json={}).status_code == 200
    raw_token = links[0].split("token=")[1].split()[0]
    act = client.post("/api/v1/portal/auth/activate", json={"token": raw_token, "password": "SecurePassword123!"})
    assert act.status_code == 200, act.text
    portal_headers = {"X-Portal-Token": act.json()["token"]}

    listing = client.get("/api/v1/portal/invoices", headers=portal_headers)
    assert listing.status_code == 200
    _assert_no_pricing_internals(listing.json())
    detail = client.get(f"/api/v1/portal/invoices/{inv['id']}", headers=portal_headers)
    assert detail.status_code == 200
    assert detail.json()["items"]
    _assert_no_pricing_internals(detail.json())

    session = client.post(
        "/api/v1/checkout/sessions", headers=auth_headers, json={"purpose": "invoice_payment", "invoice_id": inv["id"]}
    )
    assert session.status_code == 201, session.text
    view = client.get(f"/api/v1/checkout/public/{session.json()['token']}")
    assert view.status_code == 200, view.text
    _assert_no_pricing_internals(view.json())


# --- BUG-06: customer activation link is not handed to the merchant ----------------------------


def _invite(client, headers, customer):
    resp = client.post(f"/api/v1/customers/{customer.id}/portal-invite", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_portal_invite_returns_no_link_when_email_delivered(client, tenant, auth_headers, monkeypatch):
    monkeypatch.setattr(customer_portal_service, "send_email", lambda **kw: True)
    customer = tenant.customer(email="delivered@example.com")

    body = _invite(client, auth_headers, customer)
    assert body["invite_url"] is None
    assert body["email_delivered"] is True
    assert "token" not in json.dumps(body)

    access = client.get(f"/api/v1/customers/{customer.id}/portal-access", headers=auth_headers)
    assert access.status_code == 200
    assert access.json()["status"] == "invitation_pending"
    assert access.json()["invitation"]["invite_url"] is None
    assert "token=" not in json.dumps(access.json())


def test_portal_invite_link_only_for_admin_when_email_fails(client, tenant, auth_headers, monkeypatch):
    monkeypatch.setattr(customer_portal_service, "send_email", lambda **kw: False)

    # Admin+ get the link to share by hand because delivery failed.
    owner_body = _invite(client, auth_headers, tenant.customer(email="undelivered@example.com"))
    assert owner_body["email_delivered"] is False
    assert "token=" in owner_body["invite_url"]
    admin_body = _invite(client, tenant.headers_for_role(MemberRole.ADMIN), tenant.customer(email="u2@example.com"))
    assert "token=" in admin_body["invite_url"]

    # Finance may send invitations but never sees the customer's credential.
    customer = tenant.customer(email="u3@example.com")
    finance_body = _invite(client, tenant.headers_for_role(MemberRole.FINANCE), customer)
    assert finance_body["email_delivered"] is False
    assert finance_body["invite_url"] is None

    # And GET never repeats it, whoever asks.
    access = client.get(f"/api/v1/customers/{customer.id}/portal-access", headers=auth_headers)
    assert "token=" not in json.dumps(access.json())
