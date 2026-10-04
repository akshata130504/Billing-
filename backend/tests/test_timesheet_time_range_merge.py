"""A time entry update that sends only start_time or only end_time is validated against
the stored other end of the range (the request schema only checks when both are sent)."""
from datetime import date

from fastapi.testclient import TestClient

BASE = "/api/v1/timesheets"


def _create(client: TestClient, headers, **extra):
    body = {
        "project_name": "Range",
        "date": date.today().isoformat(),
        "start_time": "09:00",
        "end_time": "11:00",
        "duration_hours": 2.0,
        "description": "Range check",
        "billable": False,
        **extra,
    }
    res = client.post(BASE, headers=headers, json=body)
    assert res.status_code in (200, 201), res.text
    return res.json()


def test_update_only_end_time_before_stored_start_is_rejected(client: TestClient, tenant, auth_headers):
    entry = _create(client, auth_headers)

    res = client.patch(f"{BASE}/{entry['id']}", headers=auth_headers, json={"end_time": "08:30"})
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "End time must be later than start time" in res.text

    # Equal to the start is not "later" either.
    res = client.patch(f"{BASE}/{entry['id']}", headers=auth_headers, json={"end_time": "09:00"})
    assert res.status_code == 422, res.text

    stored = client.get(f"{BASE}/{entry['id']}", headers=auth_headers).json()
    assert stored["end_time"] == "11:00"


def test_update_only_start_time_after_stored_end_is_rejected(client: TestClient, tenant, auth_headers):
    entry = _create(client, auth_headers)

    res = client.patch(f"{BASE}/{entry['id']}", headers=auth_headers, json={"start_time": "12:00"})
    assert res.status_code == 422, res.text
    assert "End time must be later than start time" in res.text

    stored = client.get(f"{BASE}/{entry['id']}", headers=auth_headers).json()
    assert stored["start_time"] == "09:00"


def test_update_single_valid_time_succeeds(client: TestClient, tenant, auth_headers):
    entry = _create(client, auth_headers)

    res = client.patch(f"{BASE}/{entry['id']}", headers=auth_headers, json={"end_time": "12:30"})
    assert res.status_code == 200, res.text
    assert res.json()["end_time"] == "12:30"

    res = client.patch(f"{BASE}/{entry['id']}", headers=auth_headers, json={"start_time": "10:00"})
    assert res.status_code == 200, res.text
    assert res.json()["start_time"] == "10:00"


def test_update_time_on_entry_without_stored_range_is_allowed(client: TestClient, tenant, auth_headers):
    entry = _create(client, auth_headers, start_time=None, end_time=None)

    res = client.patch(f"{BASE}/{entry['id']}", headers=auth_headers, json={"end_time": "08:00"})
    assert res.status_code == 200, res.text
