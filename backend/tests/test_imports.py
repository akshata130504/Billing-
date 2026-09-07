"""CSV import tests."""
import io
import json
import uuid

from backend.app.models import AuditLog, Customer, ImportJob, MemberRole, Plan, Product

BASE = "/api/v1/imports"


def _upload(client, headers, entity, csv_text, dry_run=False, name="data.csv"):
    files = {"file": (name, io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
    return client.post(f"{BASE}/{entity}", files=files, data={"dry_run": "true" if dry_run else "false"}, headers=headers)


def test_templates(client, auth_headers):
    resp = client.get(f"{BASE}/templates/customers", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.text.strip() == (
        "display_name,company_name,email,phone,gstin,pan,currency,payment_terms_days,billing_address_line1,"
        "billing_address_line2,billing_city,billing_state,billing_postal_code,billing_country,notes"
    )
    assert client.get(f"{BASE}/templates/products", headers=auth_headers).text.strip() == (
        "name,sku,description,type,unit,hsn_sac_code,tax_rate_pct,is_active"
    )
    assert client.get(f"{BASE}/templates/plans", headers=auth_headers).text.strip() == (
        "product_sku,name,code,billing_interval,interval_count,pricing_model,unit_amount,currency,setup_fee,trial_days,is_active"
    )
    assert client.get(f"{BASE}/templates/invoices", headers=auth_headers).status_code == 422


def test_import_customers_with_errors(client, tenant, auth_headers, db):
    tenant.customer(email="exists@example.test")
    csv_text = "﻿" + "\n".join(
        [
            "display_name,email,payment_terms_days,currency,billing_country",
            "Good One,good@example.test,15,inr,in",
            "Dup In File,good@example.test,,,",
            "Existing,EXISTS@example.test,,,",
            ",noname@example.test,,,",
            "Bad Email,not-an-email,,,",
            "Bad Terms,terms@example.test,abc,,",
            "Defaults,,,,",
        ]
    )
    resp = _upload(client, auth_headers, "customers", csv_text, name="customers.csv")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entity"] == "customers"
    assert body["file_name"] == "customers.csv"
    assert body["dry_run"] is False
    assert body["total_rows"] == 7
    assert body["imported_rows"] == 2
    assert body["failed_rows"] == 5
    assert body["status"] == "completed_with_errors"
    assert [e["row"] for e in body["errors"]] == [2, 3, 4, 5, 6]
    assert "duplicate" in body["errors"][0]["error"]
    assert "already exists" in body["errors"][1]["error"]
    assert len(body["preview"]) == 7
    assert body["id"]

    good = db.query(Customer).filter_by(organization_id=tenant.organization.id, email="good@example.test").one()
    assert good.customer_number.startswith("CUS-")
    assert good.currency == "INR"
    assert good.payment_terms_days == 15
    assert good.billing_country == "IN"
    assert good.portal_token
    defaults = db.query(Customer).filter_by(organization_id=tenant.organization.id, display_name="Defaults").one()
    assert defaults.payment_terms_days == 30

    job = db.get(ImportJob, body["id"])
    assert job.imported_rows == 2 and job.failed_rows == 5
    assert db.query(AuditLog).filter_by(entity_id=job.id, action="IMPORT_COMPLETED").count() == 1

    history = client.get(BASE, headers=auth_headers).json()
    assert history["total"] == 1
    assert history["items"][0]["id"] == body["id"]
    assert history["items"][0]["status"] == "completed_with_errors"
    assert len(history["items"][0]["errors"]) == 5


def test_dry_run_commits_nothing(client, tenant, auth_headers, db):
    csv_text = "display_name,email\nDry Run Co,dry@example.test\n"
    resp = _upload(client, auth_headers, "customers", csv_text, dry_run=True)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    assert body["status"] == "completed"
    assert body["imported_rows"] == 1
    assert body["id"] is None
    assert db.query(Customer).filter_by(organization_id=tenant.organization.id, email="dry@example.test").count() == 0
    assert db.query(ImportJob).filter_by(organization_id=tenant.organization.id).count() == 0
    assert client.get(BASE, headers=auth_headers).json()["total"] == 0


def test_import_products_then_plans(client, tenant, auth_headers, db):
    sku = f"IMP-{uuid.uuid4().hex[:6]}"
    products_csv = "\n".join(
        [
            "name,sku,type,tax_rate_pct,is_active",
            f"Imported Product,{sku},goods,12,yes",
            f"Dup,{sku.lower()},goods,12,",
            "Bad Type,OTHER-1,widget,,",
            "Bad Tax,OTHER-2,service,abc,",
            "Bad Active,OTHER-3,service,5,maybe",
        ]
    )
    resp = _upload(client, auth_headers, "products", products_csv)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported_rows"] == 1 and body["failed_rows"] == 4
    product = db.query(Product).filter_by(organization_id=tenant.organization.id, sku=sku).one()
    assert str(product.tax_rate_pct) in ("12", "12.00")
    assert product.type.value == "goods"

    plans_csv = "\n".join(
        [
            "product_sku,name,code,billing_interval,interval_count,pricing_model,unit_amount,trial_days",
            f"{sku},Monthly,IMP-M-{sku},monthly,1,per_unit,499.99,7",
            f"{sku},Broken interval,IMP-B-{sku},weekly,1,flat,10,0",
            f"MISSING-{sku},No product,IMP-N-{sku},monthly,1,flat,10,0",
            f"{sku},No price,IMP-P-{sku},monthly,1,flat,,0",
        ]
    )
    resp = _upload(client, auth_headers, "plans", plans_csv)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported_rows"] == 1 and body["failed_rows"] == 3
    errors = {e["row"]: e["error"] for e in body["errors"]}
    assert "billing_interval" in errors[2]
    assert "not found" in errors[3]
    assert "unit_amount" in errors[4]
    plan = db.query(Plan).filter_by(organization_id=tenant.organization.id, code=f"IMP-M-{sku}").one()
    assert plan.product_id == product.id
    assert plan.trial_days == 7
    assert str(plan.unit_amount) == "499.99"


def test_missing_required_column_and_role(client, tenant, auth_headers):
    resp = _upload(client, auth_headers, "products", "name,description\nX,Y\n")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    resp = _upload(client, auth_headers, "customers", "")
    assert resp.status_code == 422
    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    assert _upload(client, viewer, "customers", "display_name\nX\n").status_code == 403
    assert client.get(f"{BASE}/templates/customers", headers=viewer).status_code == 200


def test_all_rows_failing_reports_failed(client, auth_headers):
    resp = _upload(client, auth_headers, "customers", "display_name,email\n,x\n,y\n")
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    assert resp.json()["imported_rows"] == 0


def test_too_many_rows_rejected(client, auth_headers):
    csv_text = "display_name\n" + "\n".join(f"Row {i}" for i in range(5001))
    resp = _upload(client, auth_headers, "customers", csv_text)
    assert resp.status_code == 422
    assert "5,000" in json.dumps(resp.json())
