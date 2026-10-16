"""File-handling hygiene: private receipts are removed with their expense; oversized logos stay rejected."""
import os
from datetime import date

from fastapi.testclient import TestClient

from backend.app.models.expenses import Expense
from backend.app.services import expense_service, logo_service

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def test_deleting_an_expense_removes_its_private_receipt(client: TestClient, tenant, auth_headers, db):
    exp = client.post(
        "/api/v1/expenses", headers=auth_headers,
        json={"name": "Taxi", "category": "Travel", "date": date.today().isoformat(), "amount": 20.0},
    ).json()
    res = client.post(
        f"/api/v1/expenses/{exp['id']}/receipt", headers=auth_headers,
        files={"file": ("taxi.pdf", b"%PDF-1.4 receipt", "application/pdf")},
    )
    assert res.status_code == 200, res.text
    path = expense_service._receipt_path(db.get(Expense, exp["id"]))
    assert path and os.path.isfile(path)

    assert client.delete(f"/api/v1/expenses/{exp['id']}", headers=auth_headers).status_code == 204
    assert not os.path.exists(path)


def test_oversized_logo_is_still_rejected_with_the_size_message(client: TestClient, auth_headers):
    big = PNG_HEADER + b"\0" * logo_service.MAX_LOGO_SIZE
    res = client.post(
        "/api/v1/organization/logo", headers=auth_headers, files={"file": ("logo.png", big, "image/png")},
    )
    assert res.status_code in (400, 413, 422), res.text
    assert "5 MB" in res.text
