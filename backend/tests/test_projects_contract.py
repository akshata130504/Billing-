"""Characterisation tests for the Projects API (modularization P0).

They pin today's observable behaviour of /api/v1/projects - response shapes, filters,
validation, not-found handling, role checks, delete side effects, detail aggregates and
the OpenAPI contract - so that moving the Projects code into its own module can be shown
to change nothing. Where today's behaviour is surprising it is recorded as-is and marked
"current behaviour"; changing it is a product decision, not part of a code move.
"""
import json
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.models import MemberRole, ROLE_RANK
from backend.app.models.expenses import Expense, ExpenseStatus
from backend.app.models.governance import AuditLog
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.projects import ProjectInvoice
from backend.app.models.timesheets import TimeEntry, TimeEntryStatus

API = "/api/v1/projects"
SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "projects_openapi.json"

PROJECT_READ_KEYS = {
    "id", "organization_id", "name", "customer_id", "customer_name", "customer", "description",
    "status", "start_date", "end_date", "billing_method", "budget", "billed", "expenses",
    "project_manager", "notes", "created_at", "updated_at",
}
PROJECT_DETAIL_KEYS = PROJECT_READ_KEYS | {"timesheets", "expense_list", "invoices", "payments", "transactions"}
SUMMARY_KEYS = {"total_projects", "active_projects", "total_budget", "total_billed", "total_expenses"}
INVOICE_ROW_KEYS = {
    "id", "projectId", "invoiceNumber", "date", "dueDate", "amount", "amountDue", "currency", "status", "rawStatus",
}
TIMESHEET_ROW_KEYS = {"id", "projectId", "employee", "date", "description", "hours", "billable", "hourlyRate", "amount"}
EXPENSE_ROW_KEYS = {"id", "projectId", "date", "title", "category", "amount", "billable", "status"}
PAYMENT_ROW_KEYS = {"id", "paymentId", "projectId", "paymentDate", "reference", "invoiceNumber", "method", "amount", "status"}
TRANSACTION_ROW_KEYS = {"id", "projectId", "type", "reference", "date", "amount", "status"}


def _create(client, headers, **body):
    body.setdefault("name", f"Project {uuid.uuid4().hex[:6]}")
    res = client.post(API, headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _money(value) -> Decimal:
    return Decimal(str(value))


def _time_entry(db, tenant, project_id, status, hours, rate, **extra):
    entry = TimeEntry(
        organization_id=tenant.organization.id, user_id=tenant.owner.id, project_id=project_id,
        date=extra.pop("on", date.today()), description=extra.pop("description", "Characterised work"),
        duration_hours=Decimal(hours), billing_rate=Decimal(rate),
        billable_amount=Decimal(hours) * Decimal(rate), status=status, **extra,
    )
    db.add(entry)
    db.commit()
    return entry


def _expense(db, tenant, project_id, status, amount, **extra):
    expense = Expense(
        organization_id=tenant.organization.id, project_id=project_id, name=extra.pop("name", "Travel"),
        date=extra.pop("on", date.today()), category="Travel", amount=Decimal(amount), status=status, **extra,
    )
    db.add(expense)
    db.commit()
    return expense


# --- Response shapes -------------------------------------------------------------------


def test_create_and_read_return_the_documented_shape(client: TestClient, tenant, auth_headers):
    customer = tenant.customer(display_name="Shape Client")
    created = _create(
        client, auth_headers, name="  Shape Project  ", customer_id=customer.id, description="Desc",
        status="on_hold", start_date="2026-01-01", end_date="2026-03-31", billing_method="time_and_material",
        budget="1234.50", project_manager="PM", notes="N",
    )
    assert set(created) == PROJECT_READ_KEYS
    assert created["name"] == "Shape Project"  # surrounding whitespace is stripped
    assert created["organization_id"] == tenant.organization.id
    assert created["customer_name"] == created["customer"] == "Shape Client"
    assert (created["status"], created["billing_method"]) == ("on_hold", "time_and_material")
    assert (created["start_date"], created["end_date"]) == ("2026-01-01", "2026-03-31")
    assert _money(created["budget"]) == Decimal("1234.50")
    assert _money(created["billed"]) == _money(created["expenses"]) == Decimal("0")

    detail = client.get(f"{API}/{created['id']}", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert set(body) == PROJECT_DETAIL_KEYS
    assert {k: body[k] for k in PROJECT_READ_KEYS - {"updated_at"}} == {
        k: created[k] for k in PROJECT_READ_KEYS - {"updated_at"}
    }
    assert [body[k] for k in ("timesheets", "expense_list", "invoices", "payments", "transactions")] == [[]] * 5


def test_create_defaults(client: TestClient, tenant, auth_headers):
    created = _create(client, auth_headers, name="Defaults")
    assert created["status"] == "active"
    assert created["billing_method"] == "fixed_price"
    assert _money(created["budget"]) == Decimal("0")
    for key in ("customer_id", "customer_name", "customer", "description", "start_date", "end_date",
                "project_manager", "notes"):
        assert created[key] is None, key


def test_free_text_customer_name_is_kept_without_a_linked_customer(client: TestClient, tenant, auth_headers):
    created = _create(client, auth_headers, name="Legacy", customer_name="Walk-in Client")
    assert created["customer_id"] is None
    assert created["customer_name"] == created["customer"] == "Walk-in Client"


def test_linked_customer_name_wins_over_free_text(client: TestClient, tenant, auth_headers):
    customer = tenant.customer(display_name="Real Name")
    created = _create(client, auth_headers, customer_id=customer.id, customer_name="Typed Name")
    assert created["customer_name"] == "Real Name"


def test_summary_shape_for_an_empty_organization(client: TestClient, tenant, auth_headers):
    res = client.get(f"{API}/summary", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert set(body) == SUMMARY_KEYS
    assert body["total_projects"] == body["active_projects"] == 0
    assert all(_money(body[k]) == 0 for k in ("total_budget", "total_billed", "total_expenses"))


# --- List: filters, search, ordering ---------------------------------------------------


def test_list_is_a_plain_array_newest_first_without_pagination(client: TestClient, tenant, auth_headers):
    ids = [_create(client, auth_headers, name=f"Order {i}")["id"] for i in range(3)]
    res = client.get(API, headers=auth_headers)
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    assert {p["id"] for p in items} == set(ids)
    assert all(set(p) == PROJECT_READ_KEYS for p in items)
    stamps = [p["created_at"] for p in items]
    assert stamps == sorted(stamps, reverse=True)


def test_list_filters_and_search(client: TestClient, tenant, auth_headers):
    acme = tenant.customer(display_name="Acme Searchable")
    other = tenant.customer(display_name="Other Co")
    a = _create(client, auth_headers, name="Website Rebuild", customer_id=acme.id, status="active")
    b = _create(client, auth_headers, name="Data Lake", customer_id=other.id, status="completed",
                description="Nightly ETL pipeline")
    c = _create(client, auth_headers, name="Internal Tooling", status="draft")

    def ids(**params):
        res = client.get(API, headers=auth_headers, params=params)
        assert res.status_code == 200, res.text
        return {p["id"] for p in res.json()}

    everything = {a["id"], b["id"], c["id"]}
    assert ids() == everything
    assert ids(customer_id=acme.id) == {a["id"]}
    assert ids(status="completed") == {b["id"]}
    assert ids(status="draft") == {c["id"]}
    assert ids(status="all") == everything
    # Current behaviour: an unknown status value is ignored (no filter), not rejected.
    assert ids(status="not-a-status") == everything
    # Search covers name, customer name and description, case-insensitively.
    assert ids(search="website") == {a["id"]}
    assert ids(search="ACME") == {a["id"]}
    assert ids(search="etl") == {b["id"]}
    assert ids(search="   ") == everything
    assert ids(search="no-such-text") == set()
    assert ids(search="data", status="draft") == set()


# --- Validation ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body, field",
    [
        ({}, "name"),
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "x" * 201}, "name"),
        ({"name": "P", "budget": "-1"}, "budget"),
        ({"name": "P", "budget": "1.234"}, "budget"),
        ({"name": "P", "budget": "1000000000000"}, "budget"),
        ({"name": "P", "status": "bogus"}, "status"),
        ({"name": "P", "billing_method": "bogus"}, "billing_method"),
        ({"name": "P", "start_date": "2026-02-10", "end_date": "2026-02-09"}, "request"),
    ],
)
def test_create_validation_errors(client: TestClient, tenant, auth_headers, body, field):
    res = client.post(API, headers=auth_headers, json=body)
    assert res.status_code == 422, res.text
    error = res.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in error["details"]["fields"]


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"budget": "-5"},
        {"status": "bogus"},
        {"start_date": "2026-05-02", "end_date": "2026-05-01"},
    ],
)
def test_update_validation_errors(client: TestClient, tenant, auth_headers, body):
    project = _create(client, auth_headers)
    res = client.patch(f"{API}/{project['id']}", headers=auth_headers, json=body)
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_update_end_date_is_only_checked_against_a_start_date_in_the_same_request(
    client: TestClient, tenant, auth_headers
):
    # Current behaviour: the date-order rule only sees fields sent in the PATCH body.
    project = _create(client, auth_headers, start_date="2026-06-10")
    res = client.patch(f"{API}/{project['id']}", headers=auth_headers, json={"end_date": "2026-06-01"})
    assert res.status_code == 200, res.text
    assert (res.json()["start_date"], res.json()["end_date"]) == ("2026-06-10", "2026-06-01")


def test_update_changes_only_the_fields_sent(client: TestClient, tenant, auth_headers):
    project = _create(client, auth_headers, name="Before", description="Keep me", budget="10")
    res = client.patch(f"{API}/{project['id']}", headers=auth_headers, json={"name": "After"})
    assert res.status_code == 200
    body = res.json()
    assert (body["name"], body["description"], _money(body["budget"])) == ("After", "Keep me", Decimal("10"))


def test_update_links_and_unlinks_a_customer(client: TestClient, tenant, auth_headers):
    customer = tenant.customer(display_name="Linked Later")
    project = _create(client, auth_headers, customer_name="Free Text")
    linked = client.patch(f"{API}/{project['id']}", headers=auth_headers, json={"customer_id": customer.id}).json()
    assert (linked["customer_id"], linked["customer_name"]) == (customer.id, "Linked Later")
    # A free-text name is ignored while a customer is linked.
    kept = client.patch(f"{API}/{project['id']}", headers=auth_headers, json={"customer_name": "Ignored"}).json()
    assert kept["customer_name"] == "Linked Later"
    unlinked = client.patch(
        f"{API}/{project['id']}", headers=auth_headers, json={"customer_id": None, "customer_name": "Back To Text"}
    ).json()
    assert (unlinked["customer_id"], unlinked["customer_name"]) == (None, "Back To Text")


# --- Not found and tenant isolation ----------------------------------------------------


def test_unknown_project_is_404_on_every_route(client: TestClient, tenant, auth_headers):
    missing = str(uuid.uuid4())
    calls = [
        client.get(f"{API}/{missing}", headers=auth_headers),
        client.patch(f"{API}/{missing}", headers=auth_headers, json={"name": "X"}),
        client.delete(f"{API}/{missing}", headers=auth_headers),
        client.post(f"{API}/{missing}/invoices", headers=auth_headers, json={"amount": "10"}),
    ]
    for res in calls:
        assert res.status_code == 404, res.text
        assert res.json()["error"]["code"] == "ENTITY_NOT_FOUND"


def test_unknown_or_foreign_customer_is_404(client: TestClient, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    other = Tenant(db, suffix=uuid.uuid4().hex[:8])
    foreign_customer = other.customer()
    assert client.post(API, headers=auth_headers, json={"name": "P", "customer_id": foreign_customer.id}).status_code == 404
    project = _create(client, auth_headers)
    res = client.patch(f"{API}/{project['id']}", headers=auth_headers, json={"customer_id": foreign_customer.id})
    assert res.status_code == 404


def test_another_tenant_cannot_list_summarise_or_invoice_projects(client: TestClient, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    customer = tenant.customer()
    mine = _create(client, auth_headers, customer_id=customer.id, budget="500")
    other = Tenant(db, suffix=uuid.uuid4().hex[:8])
    other_headers = other.headers()

    assert mine["id"] not in {p["id"] for p in client.get(API, headers=other_headers).json()}
    summary = client.get(f"{API}/summary", headers=other_headers).json()
    assert summary["total_projects"] == 0 and _money(summary["total_budget"]) == 0
    res = client.post(f"{API}/{mine['id']}/invoices", headers=other_headers, json={"amount": "10"})
    assert res.status_code == 404


def test_requests_without_credentials_are_rejected(client: TestClient):
    anonymous = TestClient(client.app)  # own cookie jar: nothing carried over from other tests
    missing = str(uuid.uuid4())
    for method, path in [("get", API), ("get", f"{API}/summary"), ("post", API), ("get", f"{API}/{missing}"),
                         ("patch", f"{API}/{missing}"), ("delete", f"{API}/{missing}"),
                         ("post", f"{API}/{missing}/invoices")]:
        res = anonymous.request(method.upper(), path, json={} if method in ("post", "patch") else None)
        assert res.status_code == 401, (method, path, res.status_code)


# --- Role matrix -----------------------------------------------------------------------

ROLES = [MemberRole.VIEWER, MemberRole.FINANCE, MemberRole.ADMIN, MemberRole.OWNER]


@pytest.mark.parametrize(
    "route, minimum, ok",
    [
        ("list", MemberRole.VIEWER, 200),
        ("summary", MemberRole.VIEWER, 200),
        ("get", MemberRole.VIEWER, 200),
        ("create", MemberRole.FINANCE, 201),
        ("update", MemberRole.FINANCE, 200),
        ("delete", MemberRole.ADMIN, 204),
        ("invoice", MemberRole.FINANCE, 201),
    ],
)
def test_role_matrix(client: TestClient, tenant, auth_headers, route, minimum, ok):
    customer = tenant.customer()
    for role in ROLES:
        headers = tenant.headers_for_role(role)
        project = _create(client, auth_headers, customer_id=customer.id)
        pid = project["id"]
        res = {
            "list": lambda: client.get(API, headers=headers),
            "summary": lambda: client.get(f"{API}/summary", headers=headers),
            "get": lambda: client.get(f"{API}/{pid}", headers=headers),
            "create": lambda: client.post(API, headers=headers, json={"name": f"By {role.value}"}),
            "update": lambda: client.patch(f"{API}/{pid}", headers=headers, json={"notes": role.value}),
            "delete": lambda: client.delete(f"{API}/{pid}", headers=headers),
            "invoice": lambda: client.post(f"{API}/{pid}/invoices", headers=headers, json={"amount": "10"}),
        }[route]()
        expected = ok if ROLE_RANK[role] >= ROLE_RANK[minimum] else 403
        assert res.status_code == expected, (route, role.value, res.status_code, res.text)


# --- Delete side effects ---------------------------------------------------------------


def test_delete_side_effects_on_linked_records(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer()
    project = _create(client, auth_headers, customer_id=customer.id)
    entry = _time_entry(db, tenant, project["id"], TimeEntryStatus.APPROVED, "1", "100", project_name=project["name"])
    expense = _expense(db, tenant, project["id"], ExpenseStatus.RECORDED, "25")
    invoice = client.post(f"{API}/{project['id']}/invoices", headers=auth_headers, json={"amount": "100"}).json()
    entry_id, expense_id = entry.id, expense.id

    assert client.delete(f"{API}/{project['id']}", headers=auth_headers).status_code == 204
    db.expire_all()

    entry = db.get(TimeEntry, entry_id)
    expense = db.get(Expense, expense_id)
    # Time entries and expenses survive and are unlinked; the entry keeps its copied project name.
    assert entry is not None and entry.project_id is None and entry.project_name == project["name"]
    assert expense is not None and expense.project_id is None
    # The project-invoice link goes with the project; the invoice itself (a draft) stays.
    assert db.scalar(select(func.count()).select_from(ProjectInvoice).where(ProjectInvoice.project_id == project["id"])) == 0
    remaining = db.get(Invoice, invoice["id"])
    assert remaining is not None and remaining.status == InvoiceStatus.DRAFT
    assert client.get(f"/api/v1/customers/{customer.id}", headers=auth_headers).status_code == 200


# --- Detail aggregates and summary -----------------------------------------------------


def test_detail_aggregates_and_summary(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer(display_name="Aggregate Client")
    project = _create(client, auth_headers, customer_id=customer.id, billing_method="time_and_material", budget="5000")
    pid = project["id"]
    yesterday = date.today() - timedelta(days=1)

    _time_entry(db, tenant, pid, TimeEntryStatus.BILLED, "2", "150", on=yesterday)
    _time_entry(db, tenant, pid, TimeEntryStatus.APPROVED, "1", "100")
    expense_invoice = tenant.invoice(customer, amount="60.00")
    _expense(db, tenant, pid, ExpenseStatus.INVOICED, "50", billable=True, billable_amount=Decimal("60"),
             invoice_id=expense_invoice.id)
    _expense(db, tenant, pid, ExpenseStatus.RECORDED, "20")
    _expense(db, tenant, None, ExpenseStatus.RECORDED, "7")  # not on any project
    direct = client.post(f"{API}/{pid}/invoices", headers=auth_headers, json={"amount": "1000", "tax_rate_pct": "18"})
    assert direct.status_code == 201, direct.text
    pay = client.post("/api/v1/payments", headers=auth_headers, json={
        "customer_id": customer.id, "amount": "60.00", "method": "bank_transfer", "reference": "CHAR-REF",
        "allocations": [{"invoice_id": expense_invoice.id, "amount": "60.00"}],
    })
    assert pay.status_code in (200, 201), pay.text

    body = client.get(f"{API}/{pid}", headers=auth_headers).json()
    # billed = billed time (300) + invoiced expenses at their billable amount (60) + direct invoice pre-tax (1000)
    assert _money(body["billed"]) == Decimal("1360")
    # expenses = every expense on the project, whatever its status
    assert _money(body["expenses"]) == Decimal("70")

    assert len(body["timesheets"]) == 2 and all(set(r) == TIMESHEET_ROW_KEYS for r in body["timesheets"])
    billed_row = next(r for r in body["timesheets"] if r["amount"] == 300.0)
    assert (billed_row["hours"], billed_row["hourlyRate"], billed_row["employee"]) == (2.0, 150.0, tenant.owner.full_name)
    assert len(body["expense_list"]) == 2 and all(set(r) == EXPENSE_ROW_KEYS for r in body["expense_list"])
    assert {r["status"] for r in body["expense_list"]} == {"invoiced", "recorded"}

    assert all(set(r) == INVOICE_ROW_KEYS for r in body["invoices"])
    by_id = {r["id"]: r for r in body["invoices"]}
    assert set(by_id) == {direct.json()["id"], expense_invoice.id}
    assert (by_id[direct.json()["id"]]["status"], by_id[direct.json()["id"]]["rawStatus"]) == ("draft", "draft")
    assert by_id[direct.json()["id"]]["amount"] == 1180.0
    assert (by_id[expense_invoice.id]["status"], by_id[expense_invoice.id]["rawStatus"]) == ("paid", "paid")

    assert len(body["payments"]) == 1 and set(body["payments"][0]) == PAYMENT_ROW_KEYS
    payment_row = body["payments"][0]
    assert (payment_row["amount"], payment_row["status"], payment_row["reference"], payment_row["method"]) == (
        60.0, "completed", "CHAR-REF", "bank_transfer"
    )
    assert payment_row["invoiceNumber"] == expense_invoice.invoice_number

    txns = body["transactions"]
    assert all(set(t) == TRANSACTION_ROW_KEYS for t in txns)
    assert sorted(t["type"] for t in txns) == ["Invoice", "Invoice", "Payment"]
    assert all(t["id"].startswith("inv-" if t["type"] == "Invoice" else "pay-") for t in txns)
    assert [t["date"] for t in txns] == sorted((t["date"] for t in txns), reverse=True)

    summary = client.get(f"{API}/summary", headers=auth_headers).json()
    assert (summary["total_projects"], summary["active_projects"]) == (1, 1)
    assert _money(summary["total_budget"]) == Decimal("5000")
    # Current behaviour: the summary counts only billed time as "billed" (unlike the per-project
    # figure) and totals every expense in the organization, including ones on no project.
    assert _money(summary["total_billed"]) == Decimal("300")
    assert _money(summary["total_expenses"]) == Decimal("77")


def test_void_project_invoice_drops_out_of_billed_and_lists(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer()
    project = _create(client, auth_headers, customer_id=customer.id)
    created = client.post(f"{API}/{project['id']}/invoices", headers=auth_headers, json={"amount": "400"}).json()
    invoice = db.get(Invoice, created["id"])
    invoice.status = InvoiceStatus.VOID
    db.commit()
    body = client.get(f"{API}/{project['id']}", headers=auth_headers).json()
    assert _money(body["billed"]) == 0
    assert body["invoices"] == [] and body["transactions"] == []


# --- Project invoice -------------------------------------------------------------------


def test_project_invoice_contract(client: TestClient, tenant, auth_headers, db):
    customer = tenant.customer()
    project = _create(client, auth_headers, name="Invoice Contract", customer_id=customer.id)
    res = client.post(f"{API}/{project['id']}/invoices", headers=auth_headers, json={"amount": "1000"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert set(body) == INVOICE_ROW_KEYS
    assert body["projectId"] == project["id"]
    assert (body["status"], body["rawStatus"]) == ("draft", "draft")
    # Without tax_rate_pct the organization default applies (18% when none is configured).
    assert body["amount"] == 1180.0 and body["amountDue"] == 1180.0
    assert body["currency"] == "INR"

    invoice = client.get(f"/api/v1/invoices/{body['id']}", headers=auth_headers).json()
    assert invoice["items"][0]["description"] == "Project billing: Invoice Contract"
    link = db.scalars(select(ProjectInvoice).where(ProjectInvoice.invoice_id == body["id"])).one()
    assert link.project_id == project["id"]
    audit = db.scalars(select(AuditLog).where(AuditLog.entity_id == body["id"], AuditLog.action == "INVOICE_CREATED")).one()
    assert audit.after_state["project_id"] == project["id"]


@pytest.mark.parametrize(
    "body, field",
    [
        ({}, "amount"),
        ({"amount": "0"}, "amount"),
        ({"amount": "-1"}, "amount"),
        ({"amount": "1000000000000"}, "amount"),
        ({"amount": "10", "tax_rate_pct": "100.01"}, "tax_rate_pct"),
        ({"amount": "10", "tax_rate_pct": "-1"}, "tax_rate_pct"),
        ({"amount": "10", "description": "d" * 501}, "description"),
        ({"amount": "10", "issue_date": "2026-03-10", "due_date": "2026-03-09"}, "request"),
    ],
)
def test_project_invoice_validation(client: TestClient, tenant, auth_headers, body, field):
    customer = tenant.customer()
    project = _create(client, auth_headers, customer_id=customer.id)
    res = client.post(f"{API}/{project['id']}/invoices", headers=auth_headers, json=body)
    assert res.status_code == 422, res.text
    assert field in res.json()["error"]["details"]["fields"]


@pytest.mark.parametrize(
    "project_body, field",
    [({"billing_method": "non_billable"}, "billing_method"), ({}, "customer_id")],
)
def test_project_invoice_refusals_create_nothing(client: TestClient, tenant, auth_headers, db, project_body, field):
    if field == "billing_method":
        project_body = {**project_body, "customer_id": tenant.customer().id}
    project = _create(client, auth_headers, **project_body)
    count = lambda: db.scalar(select(func.count()).select_from(Invoice).where(Invoice.organization_id == tenant.organization.id))  # noqa: E731
    before = count()
    res = client.post(f"{API}/{project['id']}/invoices", headers=auth_headers, json={"amount": "10"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert field in res.json()["error"]["details"]["fields"]
    assert count() == before


# --- OpenAPI contract ------------------------------------------------------------------


def _projects_openapi(app) -> dict:
    spec = app.openapi()
    paths = {p: v for p, v in spec["paths"].items() if p == API or p.startswith(API + "/")}
    schemas = spec.get("components", {}).get("schemas", {})
    wanted, pending = set(), [paths]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[-1]
                if name not in wanted:
                    wanted.add(name)
                    pending.append(schemas[name])
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    return {"paths": paths, "schemas": {name: schemas[name] for name in sorted(wanted)}}


def test_projects_openapi_contract_is_unchanged(client: TestClient):
    current = _projects_openapi(client.app)
    if os.environ.get("UPDATE_PROJECTS_OPENAPI_SNAPSHOT") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert sorted(current["paths"]) == sorted(expected["paths"])
    assert current == expected, (
        "The /projects API contract changed. If intended, regenerate with "
        "UPDATE_PROJECTS_OPENAPI_SNAPSHOT=1 and review the diff."
    )
