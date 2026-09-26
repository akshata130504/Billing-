"""Scheduler heartbeat reporting in /health/ready and the generic DB health error."""
from datetime import datetime, timedelta, timezone

import backend.app.api.v1.endpoints.health as health_endpoint
import backend.app.services.scheduler as scheduler_module
from backend.app.core import database


def _patch_ready(monkeypatch):
    monkeypatch.setattr(health_endpoint, "check_db_health", lambda: {"status": "connected"})
    monkeypatch.setattr(
        health_endpoint, "migration_status", lambda: {"status": "at_head", "current": "a", "head": "a"}
    )


def test_heartbeat_fresh_is_ok_and_never_fails_readiness(client, monkeypatch):
    _patch_ready(monkeypatch)
    monkeypatch.setattr(
        scheduler_module,
        "get_scheduler_heartbeat",
        lambda db: datetime.now(timezone.utc) - timedelta(seconds=30),
        raising=False,
    )
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    hb = response.json()["features"]["scheduler_heartbeat"]
    assert hb["status"] == "ok"
    assert hb["age_seconds"] < 120


def test_heartbeat_stale_is_reported_but_api_stays_ready(client, monkeypatch):
    _patch_ready(monkeypatch)
    monkeypatch.setattr(
        scheduler_module,
        "get_scheduler_heartbeat",
        lambda db: {
            "last_finished_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "last_error_count": 2,
        },
        raising=False,
    )
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["failures"] == []
    assert data["features"]["scheduler_heartbeat"]["status"] == "stale"
    assert data["features"]["scheduler_heartbeat"]["last_error_count"] == 2


def test_heartbeat_never_ran_is_missing(client, monkeypatch):
    _patch_ready(monkeypatch)
    monkeypatch.setattr(scheduler_module, "get_scheduler_heartbeat", lambda db: None, raising=False)
    hb = client.get("/api/v1/health/ready").json()["features"]["scheduler_heartbeat"]
    assert hb["status"] == "missing"


def test_heartbeat_missing_function_is_unavailable(client, monkeypatch):
    _patch_ready(monkeypatch)
    monkeypatch.delattr(scheduler_module, "get_scheduler_heartbeat", raising=False)
    hb = client.get("/api/v1/health/ready").json()["features"]["scheduler_heartbeat"]
    assert hb["status"] == "unavailable"


def test_heartbeat_lookup_error_is_contained(client, monkeypatch):
    _patch_ready(monkeypatch)

    def boom(db):
        raise RuntimeError("secret connection detail")

    monkeypatch.setattr(scheduler_module, "get_scheduler_heartbeat", boom, raising=False)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    hb = response.json()["features"]["scheduler_heartbeat"]
    assert hb["status"] == "unknown"
    assert "secret" not in response.text


def test_db_health_error_is_generic(monkeypatch):
    class _BrokenEngine:
        class dialect:
            name = "postgresql"

        url = "postgresql://user:pw@db-host/x"

        def connect(self):
            raise RuntimeError('could not connect to server "db-host" as user "rooman"')

    monkeypatch.setattr(database, "engine", _BrokenEngine())
    result = database.check_db_health()
    assert result["status"] == "disconnected"
    assert result["error"] == "database unreachable"
    assert "db-host" not in str(result)
