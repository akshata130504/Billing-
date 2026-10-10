"""Document templates: custom CSS is sanitised (BUG-48) and templates apply only to
their own document type (BUG-49)."""
import socket
import urllib.request

import pytest

from backend.app.models import Invoice, Organization
from backend.app.models.customization import DocumentTemplate, DocumentType, TemplateLayoutType
from backend.app.services import customization_service
from backend.app.services.invoice_pdf import render_invoice_pdf
from backend.tests.test_quote_pdf import _create_sample_quote, _extract_pdf_text

TEMPLATES = "/api/v1/templates"


def _create(client, headers, **extra):
    return client.post(
        TEMPLATES, headers=headers, json={"document_type": "invoice", "name": "CSS Tmpl", **extra}
    )


@pytest.mark.parametrize(
    "css",
    [
        "</style><script>alert(1)</script>",
        "body{color:red}</STYLE><img src=x onerror=alert(1)>",
        "@import url(http://169.254.169.254/latest/meta-data);",
        "@IMPORT 'https://evil.example.com/x.css';",
        "body{background:url(http://169.254.169.254/latest/meta-data)}",
        "body{background:url('http://cdn.example.com/bg.png')}",
        "body{background:url(https://127.0.0.1/x.png)}",
        "body{background:url(https://10.0.0.5/x.png)}",
        "body{background:url(https://localhost/x.png)}",
        "body{background:url(\"https://169.254.169.254/x\")}",
        "body{background:u\\72l(http://169.254.169.254/)}",
        "body{background:image-set('http://169.254.169.254/x' 1x)}",
        "body{width:expression(alert(1))}",
        "a{background:url(javascript:alert(1))}",
        "a{background:url(/uploads/../etc/passwd)}",
    ],
)
def test_unsafe_custom_css_rejected_on_create_and_update(client, tenant, auth_headers, css):
    assert _create(client, auth_headers, custom_css=css).status_code == 422

    ok = _create(client, auth_headers, custom_css="body { color: #111; }")
    assert ok.status_code == 200, ok.text
    res = client.put(f"{TEMPLATES}/{ok.json()['id']}", headers=auth_headers, json={"custom_css": css})
    if res.status_code == 405:
        res = client.patch(f"{TEMPLATES}/{ok.json()['id']}", headers=auth_headers, json={"custom_css": css})
    assert res.status_code == 422, res.text


@pytest.mark.parametrize(
    "css",
    [
        "body { color: #111; font-size: 12px; }\n.accent { font-weight: 700; } /* brand */",
        "@media print { .footer { display: none; } }",
        "body { background: url(/uploads/logos/bg.png) no-repeat; }",
        "body { background: url(data:image/png;base64,iVBORw0KGgo=); }",
    ],
)
def test_safe_custom_css_is_kept(client, tenant, auth_headers, css):
    res = _create(client, auth_headers, custom_css=css)
    assert res.status_code == 200, res.text
    assert res.json()["custom_css"] == css


def test_preview_drops_unsafe_css_stored_before_validation(client, tenant, auth_headers, db):
    """Rows saved before save-time validation existed must not break out at render."""
    tmpl = DocumentTemplate(
        organization_id=tenant.organization.id,
        document_type=DocumentType.INVOICE,
        name="Legacy",
        layout_type=TemplateLayoutType.STANDARD,
        custom_css="</style><script>alert(1)</script>@import url(http://169.254.169.254/);",
        font_family="x}</style><img src=x onerror=alert(1)>",
    )
    db.add(tmpl)
    db.commit()
    html = customization_service.render_template_preview(db, tmpl.id, tenant.organization.id)["rendered_html"]
    assert "<script" not in html
    assert "169.254.169.254" not in html
    assert "onerror" not in html
    assert html.count("</style>") == 1


def test_invoice_pdf_never_fetches_urls_from_template_css(client, tenant, auth_headers, db, monkeypatch):
    """The PDF renderer (ReportLab) does not consume CSS; prove no network access happens."""
    customer = tenant.customer()
    created = client.post(
        "/api/v1/invoices",
        headers=auth_headers,
        json={"customer_id": customer.id, "items": [{"description": "X", "quantity": 1, "unit_price": "10"}]},
    ).json()
    db.add(
        DocumentTemplate(
            organization_id=tenant.organization.id,
            document_type=DocumentType.INVOICE,
            name="Hostile",
            is_default=True,
            custom_css="@import url(http://169.254.169.254/); body{background:url(http://10.0.0.1/x)}",
            logo_url="http://169.254.169.254/logo.png",
        )
    )
    db.commit()

    def _boom(*_a, **_kw):
        raise AssertionError("PDF rendering must not open network connections")

    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket.socket, "connect", _boom)
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    invoice = db.get(Invoice, created["id"])
    assert render_invoice_pdf(invoice, db.get(Organization, invoice.organization_id)).startswith(b"%PDF")


# --- BUG-49 -------------------------------------------------------------------------------------


def test_invoice_template_is_not_applied_to_quote_pdfs(client, tenant, auth_headers, db):
    quote = _create_sample_quote(tenant, db)
    invoice_tmpl = DocumentTemplate(
        organization_id=tenant.organization.id,
        document_type=DocumentType.INVOICE,
        name="Invoice brand",
        is_default=True,
        is_active=True,
        header_text="INVOICE_ONLY_HEADER",
        footer_text="INVOICE_ONLY_FOOTER",
    )
    db.add(invoice_tmpl)
    db.commit()

    resp = client.get(f"/api/v1/quotes/{quote.id}/pdf", headers=auth_headers)
    assert resp.status_code == 200
    text = _extract_pdf_text(resp.content)
    assert "INVOICE_ONLY_HEADER" not in text
    assert "INVOICE_ONLY_FOOTER" not in text

    # Nor when the invoice template is requested explicitly.
    resp = client.get(f"/api/v1/quotes/{quote.id}/pdf?template_id={invoice_tmpl.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert "INVOICE_ONLY_HEADER" not in _extract_pdf_text(resp.content)


def test_quote_template_still_applies_to_quote_pdfs(client, tenant, auth_headers, db):
    quote = _create_sample_quote(tenant, db)
    db.add(
        DocumentTemplate(
            organization_id=tenant.organization.id,
            document_type=DocumentType.QUOTE,
            name="Quote brand",
            is_default=True,
            header_text="QUOTE_ONLY_HEADER",
        )
    )
    db.commit()
    resp = client.get(f"/api/v1/quotes/{quote.id}/pdf", headers=auth_headers)
    assert "QUOTE_ONLY_HEADER" in _extract_pdf_text(resp.content)
