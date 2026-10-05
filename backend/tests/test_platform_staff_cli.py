"""Bootstrap CLI for platform staff (python -m backend.app.cli.platform_staff)."""
import io
import uuid

import pytest
from sqlalchemy import select

from backend.app.cli import platform_staff as cli
from backend.app.models.platform import PlatformAuditLog, PlatformStaff

PASSWORD = "Bootstrap-Passw0rd-2026"


def _run(monkeypatch, capsys, argv, stdin=""):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = cli.main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_no_platform_staff_exist_by_default(db):
    """Nothing is seeded: no default account, no known password."""
    assert db.scalars(select(PlatformStaff).where(PlatformStaff.email.like("admin@%"))).first() is None


def test_password_is_never_a_command_line_argument():
    with pytest.raises(SystemExit):
        cli.main(["create", "--email", "a@rooman.test", "--name", "A", "--role", "platform_administrator",
                  "--password", PASSWORD])


def test_create_prints_no_secret(db, monkeypatch, capsys):
    email = f"boot-{uuid.uuid4().hex[:6]}@rooman.test"
    code, out, _ = _run(monkeypatch, capsys, ["create", "--email", email, "--name", "Boot Admin",
                                              "--role", "platform_administrator", "--password-stdin"], PASSWORD + "\n")
    assert code == 0
    assert "Platform staff member created." in out and email in out and "platform_administrator" in out
    assert PASSWORD not in out and "secret" not in out.lower() and "otpauth" not in out
    db.expire_all()
    staff = db.scalars(select(PlatformStaff).where(PlatformStaff.email == email)).first()
    assert staff is not None and staff.is_active and staff.totp_enabled_at is None
    assert staff.hashed_password not in out
    assert db.scalars(select(PlatformAuditLog).where(
        PlatformAuditLog.platform_staff_id == staff.id, PlatformAuditLog.action == "PLATFORM_STAFF_CREATED")).first()

    code, listing, _ = _run(monkeypatch, capsys, ["list"])
    assert code == 0 and email in listing
    assert "otpauth" not in listing and staff.hashed_password not in listing


def test_create_refuses_weak_password_and_duplicates(db, monkeypatch, capsys):
    email = f"weak-{uuid.uuid4().hex[:6]}@rooman.test"
    code, _, err = _run(monkeypatch, capsys, ["create", "--email", email, "--name", "W",
                                              "--role", "platform_support", "--password-stdin"], "short\n")
    assert code == 1 and "Error" in err
    assert _run(monkeypatch, capsys, ["create", "--email", email, "--name", "W", "--role", "platform_support",
                                      "--password-stdin"], PASSWORD + "\n")[0] == 0
    assert _run(monkeypatch, capsys, ["create", "--email", email, "--name", "W", "--role", "platform_support",
                                      "--password-stdin"], PASSWORD + "\n")[0] == 1


def test_deactivate(db, monkeypatch, capsys):
    email = f"cycle-{uuid.uuid4().hex[:6]}@rooman.test"
    _run(monkeypatch, capsys, ["create", "--email", email, "--name", "C", "--role", "platform_operations",
                               "--password-stdin"], PASSWORD + "\n")
    assert _run(monkeypatch, capsys, ["deactivate", "--email", email, "--reason", "left"])[0] == 0
    db.expire_all()
    assert db.scalars(select(PlatformStaff).where(PlatformStaff.email == email)).first().is_active is False
    assert _run(monkeypatch, capsys, ["deactivate", "--email", "nobody@rooman.test", "--reason", "x"])[0] == 1


def test_reset_2fa_command_no_longer_exists():
    with pytest.raises(SystemExit):
        cli.main(["reset-2fa", "--email", "a@rooman.test", "--reason", "lost phone"])
