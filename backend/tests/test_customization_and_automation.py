"""Tests for Phase 6: Customization & Automation.

Verifies:
- Number series token resolution (format preview) and atomic next-number generation.
- Document template default enforcement per document_type, and HTML/text preview rendering.
- Automation rule condition matching (module + trigger_event + conditions) via dry-run test.
- Automation rule action execution: webhook delivery via the outbox (signed bytes), allowlisted field update.
- Domain outbox events fire automation rules and subscribed Integrations webhooks.
- Webhook SSRF guard, per-endpoint secrets (revealed once), failure + backoff retry + manual retry.
- Schedules: real target actions (or honest SKIPPED/FAILED), next_date advancement, due-schedule runner.
"""
import json

import pytest

from backend.app.core.exceptions import ValidationAppError
from backend.app.models.customization import AutomationLogStatus, AutomationTriggerEvent, OutboundWebhookDelivery
from backend.app.schemas.customization import AutomationRuleCreate
from backend.app.services import customization_service
from backend.app.services.outbox_processor import emit_event, process_pending_outbox


def test_number_series_preview_and_next_number_generation(client, tenant, auth_headers, db):
    # 1. Preview a proposed series format via the API (pure calculation, no DB writes)
    preview_res = client.post(
        "/api/v1/settings/number-series/preview",
        headers=auth_headers,
        json={"prefix": "INV-{YYYY}-", "starting_number": 1, "padding": 4, "suffix": None},
    )
    assert preview_res.status_code == 200
    preview = preview_res.json()
    from datetime import date
    year = date.today().year
    assert preview["sample_number"] == f"INV-{year}-0001"

    # 2. Create a number series for the invoice module
    create_res = client.post(
        "/api/v1/settings/number-series",
        headers=auth_headers,
        json={
            "module": "invoice",
            "name": "Invoice Series A",
            "prefix": "INV-",
            "starting_number": 100,
            "padding": 5,
            "is_default": True,
            "is_active": True,
        },
    )
    assert create_res.status_code == 200
    series = create_res.json()
    assert series["current_number"] == 100
    assert series["is_default"] is True

    # 3. Reserve next numbers directly through the service (atomic increment)
    from backend.app.models.customization import TransactionNumberSeries
    db_series = db.get(TransactionNumberSeries, series["id"])
    first_number = customization_service.reserve_next_number(db, db_series)
    second_number = customization_service.reserve_next_number(db, db_series)
    db.commit()

    assert first_number == "INV-00100"
    assert second_number == "INV-00101"
    db.refresh(db_series)
    assert db_series.current_number == 102

    # 4. Reserve via the module-level default series lookup
    third_number = customization_service.reserve_next_number_for_module(db, tenant.organization.id, "invoice")
    db.commit()
    assert third_number == "INV-00102"

    # 5. Creating a second default series demotes the first
    second_series_res = client.post(
        "/api/v1/settings/number-series",
        headers=auth_headers,
        json={
            "module": "invoice",
            "name": "Invoice Series B",
            "prefix": "INV2-",
            "starting_number": 1,
            "padding": 6,
            "is_default": True,
            "is_active": True,
        },
    )
    assert second_series_res.status_code == 200

    list_res = client.get("/api/v1/settings/number-series?module=invoice", headers=auth_headers)
    assert list_res.status_code == 200
    series_list = list_res.json()
    defaults = [s for s in series_list if s["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["name"] == "Invoice Series B"


def test_document_template_default_selection_and_preview(client, tenant, auth_headers, db):
    # 1. Create the first invoice template, marked default
    tmpl1_res = client.post(
        "/api/v1/templates",
        headers=auth_headers,
        json={
            "document_type": "invoice",
            "name": "Standard Invoice",
            "layout_type": "standard",
            "is_default": True,
            "header_text": "Acme Corp",
            "footer_text": "Thank you for your business.",
            "terms_and_conditions": "Payment due within 30 days.",
        },
    )
    assert tmpl1_res.status_code == 200
    tmpl1 = tmpl1_res.json()
    assert tmpl1["is_default"] is True

    # 2. Create a second invoice template, also default -> should demote the first
    tmpl2_res = client.post(
        "/api/v1/templates",
        headers=auth_headers,
        json={
            "document_type": "invoice",
            "name": "Modern Invoice",
            "layout_type": "modern",
            "is_default": True,
        },
    )
    assert tmpl2_res.status_code == 200
    tmpl2 = tmpl2_res.json()
    assert tmpl2["is_default"] is True

    get_tmpl1 = client.get(f"/api/v1/templates/{tmpl1['id']}", headers=auth_headers)
    assert get_tmpl1.status_code == 200
    assert get_tmpl1.json()["is_default"] is False

    # 3. A quote template default does not conflict with the invoice template default
    quote_tmpl_res = client.post(
        "/api/v1/templates",
        headers=auth_headers,
        json={"document_type": "quote", "name": "Standard Quote", "is_default": True},
    )
    assert quote_tmpl_res.status_code == 200
    get_tmpl2_again = client.get(f"/api/v1/templates/{tmpl2['id']}", headers=auth_headers)
    assert get_tmpl2_again.json()["is_default"] is True

    # 4. Preview rendering includes configured header/footer/terms
    preview_res = client.post(f"/api/v1/templates/{tmpl1['id']}/preview", headers=auth_headers)
    assert preview_res.status_code == 200
    preview = preview_res.json()
    assert preview["document_type"] == "invoice"
    assert "Acme Corp" in preview["rendered_html"]
    assert "Thank you for your business." in preview["rendered_text"]
    assert "Payment due within 30 days." in preview["rendered_html"]


def test_template_preview_with_configured_logo(client, tenant, auth_headers, db):
    """Focused regression test for B12: template preview must not crash when logo is configured."""
    import os
    from backend.app.core.config import settings

    logo_filename = "test_preview_logo.png"
    logo_dir = os.path.join(settings.UPLOAD_DIR, "logos")
    os.makedirs(logo_dir, exist_ok=True)
    logo_path = os.path.join(logo_dir, logo_filename)
    with open(logo_path, "wb") as f:
        # 1x1 valid PNG
        f.write(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
            b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\x9f\x81\x01\x01\x00\x18\xfe\x02\xfeC\xa5P\x96\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    tenant.organization.logo_url = f"/uploads/logos/{logo_filename}"
    db.commit()

    try:
        tmpl_res = client.post(
            "/api/v1/templates",
            headers=auth_headers,
            json={
                "document_type": "invoice",
                "name": "Logo Preview Invoice",
                "layout_type": "modern",
                "is_default": False,
            },
        )
        assert tmpl_res.status_code == 200
        tmpl = tmpl_res.json()

        preview_res = client.post(f"/api/v1/templates/{tmpl['id']}/preview", headers=auth_headers)
        assert preview_res.status_code == 200
        preview = preview_res.json()
        assert "data:image/png;base64," in preview["rendered_html"]
        assert 'alt="Organization Logo"' in preview["rendered_html"]
    finally:
        if os.path.exists(logo_path):
            os.remove(logo_path)


def test_automation_rule_condition_matching_dry_run(client, tenant, auth_headers, db):
    rule_res = client.post(
        "/api/v1/automation/rules",
        headers=auth_headers,
        json={
            "name": "High Value Invoice Alert",
            "module": "invoice",
            "trigger_event": "created",
            "conditions": {"amount_due": {"operator": "gte", "value": 10000}},
            "is_active": True,
            "actions": [
                {
                    "action_type": "email_alert",
                    "name": "Notify Finance Team",
                    "configuration": {"recipient": "finance@example.test"},
                    "execution_order": 1,
                }
            ],
        },
    )
    assert rule_res.status_code == 200
    rule = rule_res.json()
    assert len(rule["actions"]) == 1

    # Matches when condition satisfied
    match_res = client.post(
        f"/api/v1/automation/rules/{rule['id']}/test",
        headers=auth_headers,
        json={"event_data": {"amount_due": 15000}},
    )
    assert match_res.status_code == 200
    assert match_res.json()["matches"] is True
    assert match_res.json()["would_execute_actions"] == ["Notify Finance Team"]

    # Does not match when condition not satisfied
    no_match_res = client.post(
        f"/api/v1/automation/rules/{rule['id']}/test",
        headers=auth_headers,
        json={"event_data": {"amount_due": 500}},
    )
    assert no_match_res.status_code == 200
    assert no_match_res.json()["matches"] is False
    assert no_match_res.json()["would_execute_actions"] == []


class _FakeWebhookNetwork:
    """Stubs DNS/SSRF resolution and the HTTP POST so webhook tests never touch the network."""

    def __init__(self):
        self.calls = []
        self.status_code = 200
        self.response_text = "ok"

    def post(self, url, body, headers, timeout):
        self.calls.append({"url": url, "body": body, "headers": dict(headers)})
        return self.status_code, self.response_text


@pytest.fixture()
def webhook_network(monkeypatch):
    from backend.app.core import network_security

    fake = _FakeWebhookNetwork()
    real_is_safe_url = network_security.is_safe_url

    def _is_safe_url(url):
        # Hosts under the reserved .test TLD stand in for public receivers; literal IPs and
        # everything else go through the real guard.
        from urllib.parse import urlsplit

        host = (urlsplit(url or "").hostname or "").lower()
        if host.endswith(".example.test") and (url or "").startswith(("http://", "https://")):
            return True
        return real_is_safe_url(url)

    monkeypatch.setattr(network_security, "is_safe_url", _is_safe_url)
    monkeypatch.setattr(customization_service, "_post_webhook", fake.post)
    return fake


def _verify_signature(call, secret):
    ts = call["headers"]["X-Rooman-Timestamp"]
    expected = customization_service.sign_webhook_body(call["body"], secret, ts)
    return call["headers"]["X-Rooman-Signature"] == f"sha256={expected}"


def test_automation_engine_executes_actions_and_logs(client, tenant, auth_headers, db, webhook_network):
    customer = tenant.customer()
    invoice = tenant.invoice(customer)
    rule = customization_service.create_rule(
        db,
        tenant.organization.id,
        AutomationRuleCreate(
            name="Overdue Invoice Webhook",
            module="invoice",
            trigger_event=AutomationTriggerEvent.INVOICE_OVERDUE,
            conditions={},
            is_active=True,
            actions=[
                {
                    "action_type": "webhook",
                    "name": "Notify External CRM",
                    "configuration": {"url": "https://crm.example.test/hooks/invoice-overdue"},
                    "execution_order": 1,
                },
                {
                    "action_type": "field_update",
                    "name": "Flag Account At Risk",
                    "configuration": {"field": "notes", "value": "At risk: overdue"},
                    "execution_order": 2,
                },
            ],
        ),
    )
    secret = next(a.configuration["secret"] for a in rule.actions if a.action_type.value == "webhook")
    assert secret.startswith("whsec_")
    db.commit()

    result = customization_service.process_automation_event(
        db,
        tenant.organization.id,
        module="invoice",
        trigger_event=AutomationTriggerEvent.INVOICE_OVERDUE,
        event_data={"invoice_id": invoice.id, "amount_due": 2000},
        entity_type="invoice",
        entity_id=invoice.id,
    )
    db.commit()

    assert result["rules_triggered"] == 1
    assert [r["status"] for r in result["action_results"]] == ["success", "success"]
    db.refresh(invoice)
    assert invoice.notes == "At risk: overdue"

    logs = customization_service.list_automation_logs(db, tenant.organization.id, entity_type="invoice")
    assert {log.status for log in logs} == {AutomationLogStatus.SUCCESS}

    # Webhook is queued, then delivered by the outbox worker with a verifiable signature.
    deliveries = customization_service.list_webhook_deliveries(db, tenant.organization.id)
    assert len(deliveries) == 1 and deliveries[0].status == "pending"
    assert webhook_network.calls == []

    process_pending_outbox(db, organization_id=tenant.organization.id)
    db.refresh(deliveries[0])
    assert deliveries[0].status == "delivered"
    assert deliveries[0].rule_id == rule.id
    assert deliveries[0].attempt_count == 1
    assert len(webhook_network.calls) == 1
    call = webhook_network.calls[0]
    assert call["headers"]["Content-Type"] == "application/json"
    assert json.loads(call["body"]) == {"invoice_id": invoice.id, "amount_due": 2000}
    assert _verify_signature(call, secret)
    assert not _verify_signature(call, "rooman_webhook_default_secret")


def test_field_update_is_allowlisted_and_never_a_fake_success(client, tenant, auth_headers, db):
    with pytest.raises(ValidationAppError):
        customization_service.create_rule(
            db,
            tenant.organization.id,
            AutomationRuleCreate(
                name="Bad Field Update",
                module="invoice",
                trigger_event=AutomationTriggerEvent.CREATED,
                actions=[{"action_type": "field_update", "name": "x", "configuration": {"field": "total", "value": 0}}],
            ),
        )
    db.rollback()

    customization_service.create_rule(
        db,
        tenant.organization.id,
        AutomationRuleCreate(
            name="Customer Notes Update",
            module="payment",
            trigger_event=AutomationTriggerEvent.PAYMENT_FAILED,
            actions=[{"action_type": "field_update", "name": "Note it", "configuration": {"field": "notes", "value": "x"}}],
        ),
    )
    db.commit()
    # "payment.notes" is not on the allowlist -> the action fails and is logged as FAILED.
    result = customization_service.process_automation_event(
        db,
        tenant.organization.id,
        module="payment",
        trigger_event=AutomationTriggerEvent.PAYMENT_FAILED,
        event_data={},
        entity_type="payment",
        entity_id="pay-1",
    )
    db.commit()
    assert result["action_results"][0]["status"] == "failed"
    logs = customization_service.list_automation_logs(db, tenant.organization.id, entity_type="payment")
    assert [log.status for log in logs] == [AutomationLogStatus.FAILED]


def test_webhook_delivery_failure_is_retried_with_backoff_and_manual_retry(client, tenant, auth_headers, db, webhook_network):
    from backend.app.models.events import OutboxEvent, OutboxStatus

    customization_service.create_rule(
        db,
        tenant.organization.id,
        AutomationRuleCreate(
            name="Payment Failed Webhook",
            module="payment",
            trigger_event=AutomationTriggerEvent.PAYMENT_FAILED,
            conditions={},
            is_active=True,
            actions=[
                {
                    "action_type": "webhook",
                    "name": "Notify Billing Ops",
                    "configuration": {"url": "https://ops.example.test/hooks/payment-failed"},
                    "execution_order": 1,
                }
            ],
        ),
    )
    db.commit()

    customization_service.process_automation_event(
        db,
        tenant.organization.id,
        module="payment",
        trigger_event=AutomationTriggerEvent.PAYMENT_FAILED,
        event_data={"payment_id": "pay-1"},
        entity_type="payment",
        entity_id="pay-1",
    )
    db.commit()

    webhook_network.status_code = 500
    webhook_network.response_text = "x" * 5000
    assert process_pending_outbox(db, organization_id=tenant.organization.id) == 0

    deliveries = customization_service.list_webhook_deliveries(db, tenant.organization.id, status="failed")
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery.attempt_count == 1
    assert delivery.error_message == "Webhook recipient responded with HTTP 500"
    assert len(delivery.response_body) == 1024  # truncated

    retry_event = db.query(OutboxEvent).filter(OutboxEvent.aggregate_id == delivery.id).one()
    assert retry_event.status == OutboxStatus.PENDING
    assert retry_event.retry_count == 1
    assert retry_event.next_attempt_at is not None
    # Backoff: not claimed again immediately.
    process_pending_outbox(db, organization_id=tenant.organization.id)
    assert len(webhook_network.calls) == 1

    # Manual retry performs an immediate attempt.
    webhook_network.status_code = 200
    retry_res = client.post(f"/api/v1/webhook-deliveries/{delivery.id}/retry", headers=auth_headers)
    assert retry_res.status_code == 200
    retried = retry_res.json()
    assert retried["status"] == "delivered"
    assert retried["attempt_count"] == 2

    second_retry_res = client.post(f"/api/v1/webhook-deliveries/{delivery.id}/retry", headers=auth_headers)
    assert second_retry_res.status_code == 422


def test_webhook_ssrf_destinations_are_blocked(client, tenant, auth_headers, db, webhook_network):
    for url in ("http://127.0.0.1:8000/hook", "http://169.254.169.254/latest/meta-data", "ftp://files.example.test/x", "http://10.0.0.5/h"):
        res = client.post(
            "/api/v1/automation/rules",
            headers=auth_headers,
            json={
                "name": f"SSRF {url}",
                "module": "invoice",
                "trigger_event": "created",
                "actions": [{"action_type": "webhook", "name": "hook", "configuration": {"url": url}}],
            },
        )
        assert res.status_code == 422, url

    # A legacy row pointing at a metadata IP is never contacted.
    delivery = OutboundWebhookDelivery(
        organization_id=tenant.organization.id,
        destination_url="http://169.254.169.254/latest",
        event_type="invoice.created",
        payload={"a": 1},
        status="pending",
        attempt_count=0,
    )
    db.add(delivery)
    db.flush()
    customization_service.deliver_webhook(db, delivery)
    db.commit()
    assert delivery.status == "failed"
    assert "not permitted" in delivery.error_message
    assert webhook_network.calls == []


def test_rule_webhook_secret_is_revealed_once_then_masked(client, tenant, auth_headers, db, webhook_network):
    res = client.post(
        "/api/v1/automation/rules",
        headers=auth_headers,
        json={
            "name": "Secret Once",
            "module": "invoice",
            "trigger_event": "created",
            "actions": [{"action_type": "webhook", "name": "hook", "configuration": {"url": "https://a.example.test/h"}}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    action_id = body["actions"][0]["id"]
    secret = body["revealed_signing_secrets"][action_id]
    assert secret.startswith("whsec_")
    assert body["actions"][0]["configuration"]["secret"] != secret

    get_res = client.get(f"/api/v1/automation/rules/{body['id']}", headers=auth_headers)
    got = get_res.json()
    assert got["revealed_signing_secrets"] is None
    assert got["actions"][0]["configuration"]["secret"] == "••••" + secret[-4:]
    assert secret not in get_res.text


def test_webhook_delivery_response_body_is_admin_only(client, tenant, auth_headers, db):
    from backend.app.models import MemberRole

    db.add(
        OutboundWebhookDelivery(
            organization_id=tenant.organization.id,
            destination_url="https://a.example.test/h",
            event_type="invoice.created",
            payload={},
            status="failed",
            response_status_code=500,
            response_body="internal receiver details",
            attempt_count=1,
        )
    )
    db.commit()
    viewer = client.get("/api/v1/webhook-deliveries", headers=tenant.headers_for_role(MemberRole.VIEWER)).json()
    assert viewer[0]["response_body"] is None
    owner = client.get("/api/v1/webhook-deliveries", headers=auth_headers).json()
    assert owner[0]["response_body"] == "internal receiver details"


def test_outbox_domain_event_fires_automation_rules(client, tenant, auth_headers, db):
    customer = tenant.customer()
    invoice = tenant.invoice(customer, amount="15000.00")
    customization_service.create_rule(
        db,
        tenant.organization.id,
        AutomationRuleCreate(
            name="Paid High Value",
            module="invoice",
            trigger_event=AutomationTriggerEvent.PAYMENT_SUCCEEDED,
            conditions={"total": {"operator": "gte", "value": 10000}},
            actions=[
                {"action_type": "field_update", "name": "Tag", "configuration": {"field": "notes", "value": "VIP payment"}}
            ],
        ),
    )
    emit_event(db, tenant.organization.id, "invoice.paid", {"invoice_id": invoice.id, "amount": "15000.00"})
    db.commit()

    assert process_pending_outbox(db, organization_id=tenant.organization.id) >= 1
    db.refresh(invoice)
    assert invoice.notes == "VIP payment"
    logs = customization_service.list_automation_logs(db, tenant.organization.id, entity_type="invoice")
    assert any(log.status == AutomationLogStatus.SUCCESS and log.entity_id == invoice.id for log in logs)


def test_integrations_webhook_receives_subscribed_domain_events(client, tenant, auth_headers, db, webhook_network):
    from backend.app.schemas.integrations import WebhookConfigureRequest
    from backend.app.services import integrations_service

    status = integrations_service.save_webhook_config(
        db,
        tenant.organization.id,
        WebhookConfigureRequest(url="https://hooks.example.test/billing", events=["invoice.paid"], is_enabled=True),
    )
    secret = status.generated_signing_secret
    assert secret and secret.startswith("whsec_")
    # Re-saving without a secret keeps the existing one and does not reveal it again.
    again = integrations_service.save_webhook_config(
        db,
        tenant.organization.id,
        WebhookConfigureRequest(url="https://hooks.example.test/billing", events=["invoice.paid"], is_enabled=True),
    )
    assert again.generated_signing_secret is None

    emit_event(db, tenant.organization.id, "invoice.paid", {"invoice_id": "inv-1", "amount": "10.00"})
    emit_event(db, tenant.organization.id, "subscription.created", {"subscription_id": "sub-1"})
    db.commit()
    process_pending_outbox(db, organization_id=tenant.organization.id)

    assert len(webhook_network.calls) == 1
    call = webhook_network.calls[0]
    envelope = json.loads(call["body"])
    assert envelope["type"] == "invoice.paid"
    assert envelope["data"] == {"invoice_id": "inv-1", "amount": "10.00"}
    assert call["headers"]["X-Rooman-Event"] == "invoice.paid"
    assert _verify_signature(call, secret)


def test_template_preview_logo_path_traversal_is_contained(client, tenant, auth_headers, db):
    import os
    from backend.app.core.config import settings

    outside = os.path.abspath(os.path.join(settings.UPLOAD_DIR, "..", "cust_traversal_probe.png"))
    with open(outside, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\nsecret")
    try:
        tenant.organization.logo_url = "/uploads/../cust_traversal_probe.png"
        db.commit()
        tmpl = client.post(
            "/api/v1/templates",
            headers=auth_headers,
            json={"document_type": "invoice", "name": "Traversal", "layout_type": "standard"},
        ).json()
        preview = client.post(f"/api/v1/templates/{tmpl['id']}/preview", headers=auth_headers).json()
        assert "data:image" not in preview["rendered_html"]
        assert "<img" not in preview["rendered_html"]
    finally:
        os.remove(outside)


def test_automation_schedule_creation_and_manual_trigger(client, tenant, auth_headers, db):
    create_res = client.post(
        "/api/v1/automation/schedules",
        headers=auth_headers,
        json={
            "name": "Month to date KPIs",
            "description": "Snapshot of month-to-date KPIs",
            "frequency": "daily",
            "target_action": "export_reports",
            "status": "active",
            "is_active": True,
        },
    )
    assert create_res.status_code == 200
    schedule = create_res.json()
    assert schedule["last_executed_on"] is None
    assert schedule["next_date"] is not None

    trigger_res = client.post(f"/api/v1/automation/schedules/{schedule['id']}/trigger", headers=auth_headers)
    assert trigger_res.status_code == 200
    trigger_data = trigger_res.json()
    assert trigger_data["target_action"] == "export_reports"
    assert trigger_data["result"]["executed"] is True
    assert "kpis" in trigger_data["result"]["details"]

    updated = client.get(f"/api/v1/automation/schedules/{schedule['id']}", headers=auth_headers).json()
    assert updated["last_executed_on"] is not None
    assert updated["next_date"] > schedule["next_date"]

    logs = client.get("/api/v1/automation/logs?entity_type=automation_schedule", headers=auth_headers).json()
    assert logs[0]["status"] == "success"


def test_schedule_platform_managed_action_is_skipped_not_faked(client, tenant, auth_headers, db):
    schedule = client.post(
        "/api/v1/automation/schedules",
        headers=auth_headers,
        json={"name": "Nightly Billing", "frequency": "daily", "target_action": "run_billing_jobs"},
    ).json()
    result = client.post(f"/api/v1/automation/schedules/{schedule['id']}/trigger", headers=auth_headers).json()["result"]
    assert result["executed"] is False
    assert result["status"] == "skipped"
    logs = client.get("/api/v1/automation/logs?entity_type=automation_schedule", headers=auth_headers).json()
    assert logs[0]["status"] == "skipped"

    bad = client.post(
        "/api/v1/automation/schedules",
        headers=auth_headers,
        json={"name": "Unknown", "frequency": "daily", "target_action": "launch_rockets"},
    )
    assert bad.status_code == 422
    bad_cron = client.post(
        "/api/v1/automation/schedules",
        headers=auth_headers,
        json={"name": "Bad cron", "frequency": "daily", "target_action": "export_reports", "cron_expression": "not a cron"},
    )
    assert bad_cron.status_code == 422


def test_run_due_automation_schedules_executes_due_rows(client, tenant, auth_headers, db):
    from datetime import timedelta

    from backend.app.models.base import utcnow
    from backend.app.models.customization import AutomationSchedule, ScheduleFrequency

    due = AutomationSchedule(
        organization_id=tenant.organization.id,
        name="Due KPI export",
        frequency=ScheduleFrequency.MONTHLY,
        target_action="export_reports",
        next_date=utcnow() - timedelta(minutes=5),
    )
    later = AutomationSchedule(
        organization_id=tenant.organization.id,
        name="Future KPI export",
        frequency=ScheduleFrequency.DAILY,
        target_action="export_reports",
        next_date=utcnow() + timedelta(days=1),
    )
    db.add_all([due, later])
    db.commit()

    assert customization_service.run_due_automation_schedules(db) >= 1
    db.refresh(due)
    db.refresh(later)
    assert due.last_executed_on is not None
    assert later.last_executed_on is None
    next_date = due.next_date if due.next_date.tzinfo else due.next_date.replace(tzinfo=utcnow().tzinfo)
    assert next_date > utcnow() + timedelta(days=27)
    # Not due any more -> a second pass does not re-run it.
    before = due.last_executed_on
    customization_service.run_due_automation_schedules(db)
    db.refresh(due)
    assert due.last_executed_on == before


def test_compute_next_schedule_date_monthly_and_cron():
    from datetime import datetime, timezone

    from backend.app.models.customization import ScheduleFrequency

    jan31 = datetime(2026, 1, 31, 9, 0, tzinfo=timezone.utc)
    assert customization_service.compute_next_schedule_date(ScheduleFrequency.MONTHLY, jan31) == datetime(2026, 2, 28, 9, 0, tzinfo=timezone.utc)
    nxt = customization_service.compute_next_schedule_date(ScheduleFrequency.DAILY, jan31, "30 2 * * *")
    assert (nxt.day, nxt.hour, nxt.minute) == (1, 2, 30)
