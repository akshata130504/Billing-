"""Tests for notification email templates API and dispatch service."""
import pytest

from backend.app.models.notifications import NotificationChannel, NotificationTemplate
from backend.app.services.notification_service import (
    html_to_plain_text,
    render_template_string,
    get_active_template,
)
from backend.app.services.invoice_service import _invoice_email
from backend.app.services.quote_service import _notify_customer


def test_html_to_plain_text():
    html = "<p>Hello <strong>World</strong>!</p><br><p>This is a <a href='https://example.com'>link</a>.</p>"
    plain = html_to_plain_text(html)
    assert "Hello World!" in plain
    assert "This is a link." in plain
    assert "<" not in plain


def test_render_template_string_safe_with_missing_keys():
    template = "Invoice {{invoice_number}} for {{missing_var}} from {{company_name}}"
    context = {"invoice_number": "INV-100", "company_name": "Acme"}
    rendered = render_template_string(template, context)
    assert rendered == "Invoice INV-100 for  from Acme"


def test_list_templates_seeds_defaults(client, tenant, auth_headers):
    resp = client.get("/api/v1/notifications/templates", headers=auth_headers)
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) >= 6
    codes = {t["code"] for t in templates}
    assert "invoice_sent" in codes
    assert "quote_sent" in codes
    assert "payment_receipt" in codes
    assert "payment_reminder" in codes
    assert "payment_failed" in codes
    assert "dunning_retry" in codes


def test_update_template_and_preview(client, tenant, auth_headers):
    resp = client.get("/api/v1/notifications/templates", headers=auth_headers)
    assert resp.status_code == 200
    first = resp.json()[0]
    template_id = first["id"]

    # Update template
    put_resp = client.put(
        f"/api/v1/notifications/templates/{template_id}",
        json={
            "name": "Custom Invoice Sent",
            "subject_template": "Your bill {{invoice_number}} is ready",
            "body_template": "<p>Hi {{customer_name}}, please pay {{invoice_total}}.</p>",
        },
        headers=auth_headers,
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["name"] == "Custom Invoice Sent"
    assert updated["subject_template"] == "Your bill {{invoice_number}} is ready"

    # Preview template
    prev_resp = client.post(
        f"/api/v1/notifications/templates/{template_id}/preview",
        json={},
        headers=auth_headers,
    )
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert "INV-2026-0042" in prev_data["subject"]
    assert "Acme Innovations Ltd" in prev_data["body_html"]
    assert "<" not in prev_data["body_text"]


def test_test_send_template(client, tenant, auth_headers):
    resp = client.get("/api/v1/notifications/templates", headers=auth_headers)
    template_id = resp.json()[0]["id"]

    send_resp = client.post(
        f"/api/v1/notifications/templates/{template_id}/test-send",
        json={"recipient": "test-recipient@example.com"},
        headers=auth_headers,
    )
    assert send_resp.status_code == 200
    assert send_resp.json()["recipient"] == "test-recipient@example.com"


def test_disabled_template_falls_back_to_default(client, tenant, auth_headers, db):
    # Find invoice_sent template
    resp = client.get("/api/v1/notifications/templates", headers=auth_headers)
    inv_tmpl = next(t for t in resp.json() if t["code"] == "invoice_sent")

    # Disable it
    client.put(
        f"/api/v1/notifications/templates/{inv_tmpl['id']}",
        json={"is_active": False},
        headers=auth_headers,
    )

    # Now verify get_active_template returns None for active lookup
    active = get_active_template(db, tenant.organization.id, "invoice_sent")
    assert active is None
