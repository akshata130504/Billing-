"""Tests for Phase 6: Customization & Automation.

Verifies:
- Number series token resolution (format preview) and atomic next-number generation.
- Document template default enforcement per document_type, and HTML/text preview rendering.
- Automation rule condition matching (module + trigger_event + conditions) via dry-run test.
- Automation rule action execution: email alert, webhook delivery (+ logging), field update.
- Webhook delivery failure + retry recovery.
- Schedule creation, manual trigger, and next_date advancement.
"""
from backend.app.models.customization import AutomationLogStatus, AutomationTriggerEvent
from backend.app.schemas.customization import AutomationRuleCreate
from backend.app.services import customization_service


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


def test_automation_engine_executes_actions_and_logs(client, tenant, auth_headers, db):
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
                    "configuration": {"field": "account_risk_flag", "value": True},
                    "execution_order": 2,
                },
            ],
        ),
    )
    db.commit()

    result = customization_service.process_automation_event(
        db,
        tenant.organization.id,
        module="invoice",
        trigger_event=AutomationTriggerEvent.INVOICE_OVERDUE,
        event_data={"invoice_id": "inv-123", "amount_due": 2000},
        entity_type="invoice",
        entity_id="inv-123",
    )
    db.commit()

    assert result["rules_triggered"] == 1
    assert len(result["action_results"]) == 2
    assert result["action_results"][0]["status"] == "success"
    assert result["action_results"][1]["status"] == "success"

    logs = customization_service.list_automation_logs(db, tenant.organization.id, entity_type="invoice")
    assert len(logs) == 2
    assert {log.status for log in logs} == {AutomationLogStatus.SUCCESS}

    deliveries = customization_service.list_webhook_deliveries(db, tenant.organization.id)
    assert len(deliveries) == 1
    assert deliveries[0].status == "delivered"
    assert deliveries[0].rule_id == rule.id


def test_webhook_delivery_failure_and_retry(client, tenant, auth_headers, db):
    rule = customization_service.create_rule(
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
                    "configuration": {
                        "url": "https://ops.example.test/hooks/payment-failed",
                        "simulate_failure": True,
                    },
                    "execution_order": 1,
                }
            ],
        ),
    )
    db.commit()

    result = customization_service.process_automation_event(
        db,
        tenant.organization.id,
        module="payment",
        trigger_event=AutomationTriggerEvent.PAYMENT_FAILED,
        event_data={"payment_id": "pay-1"},
        entity_type="payment",
        entity_id="pay-1",
    )
    db.commit()
    assert result["action_results"][0]["status"] == "success"  # action executed; delivery itself failed

    deliveries = customization_service.list_webhook_deliveries(db, tenant.organization.id, status="failed")
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery.attempt_count == 1

    # Retry via API succeeds (simulated recovery)
    retry_res = client.post(
        f"/api/v1/webhook-deliveries/{delivery.id}/retry",
        headers=auth_headers,
    )
    assert retry_res.status_code == 200
    retried = retry_res.json()
    assert retried["status"] == "delivered"
    assert retried["attempt_count"] == 2

    # A second retry on an already-delivered webhook is rejected
    second_retry_res = client.post(
        f"/api/v1/webhook-deliveries/{delivery.id}/retry",
        headers=auth_headers,
    )
    assert second_retry_res.status_code == 422


def test_automation_schedule_creation_and_manual_trigger(client, tenant, auth_headers, db):
    create_res = client.post(
        "/api/v1/automation/schedules",
        headers=auth_headers,
        json={
            "name": "Nightly Overdue Sweep",
            "description": "Scans for overdue invoices and triggers dunning",
            "frequency": "daily",
            "target_action": "run_billing_jobs",
            "status": "active",
            "is_active": True,
        },
    )
    assert create_res.status_code == 200
    schedule = create_res.json()
    assert schedule["last_executed_on"] is None
    assert schedule["next_date"] is not None

    trigger_res = client.post(
        f"/api/v1/automation/schedules/{schedule['id']}/trigger",
        headers=auth_headers,
    )
    assert trigger_res.status_code == 200
    trigger_data = trigger_res.json()
    assert trigger_data["target_action"] == "run_billing_jobs"
    assert trigger_data["result"]["executed"] is True

    get_res = client.get(f"/api/v1/automation/schedules/{schedule['id']}", headers=auth_headers)
    assert get_res.status_code == 200
    updated = get_res.json()
    assert updated["last_executed_on"] is not None
    assert updated["next_date"] > schedule["next_date"]

    logs_res = client.get("/api/v1/automation/logs?entity_type=automation_schedule", headers=auth_headers)
    assert logs_res.status_code == 200
    assert len(logs_res.json()) >= 1
