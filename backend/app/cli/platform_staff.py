"""Server-side management of Rooman platform staff (there is deliberately no HTTP endpoint for this).

Run where the API runs (it uses the same DATABASE_URL), e.g. inside the API container:

    python -m backend.app.cli.platform_staff create --email you@rooman.com --name "Your Name" \\
        --role platform_administrator
    python -m backend.app.cli.platform_staff list
    python -m backend.app.cli.platform_staff deactivate --email you@rooman.com --reason "left the team"
    python -m backend.app.cli.platform_staff activate --email you@rooman.com --reason "rejoined"
    python -m backend.app.cli.platform_staff reset-2fa --email you@rooman.com --reason "lost phone"
    python -m backend.app.cli.platform_staff set-password --email you@rooman.com

Passwords are read with a hidden prompt (or one line from stdin with --password-stdin); they are
never taken as command-line arguments, printed or logged. `create` and `reset-2fa` print the new
TOTP secret ONCE so it can be added to an authenticator app - store it nowhere else. There is no
default account and nothing is created automatically.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from typing import Optional

from backend.app.models.platform import PlatformRole

ACTOR = f"cli:{os.environ.get('USER') or os.environ.get('USERNAME') or 'unknown'}"


def _read_password(args: argparse.Namespace) -> str:
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("New password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        raise SystemExit("Passwords do not match.")
    return first


def _print_enrolment(title: str, enrolment) -> None:
    print(title)
    print(f"  email: {enrolment.staff.email}")
    print(f"  role:  {enrolment.staff.role.value}")
    print("")
    print("Add this to the staff member's authenticator app now; it is shown only once:")
    print(f"  otpauth URI: {enrolment.otpauth_uri}")
    print(f"  secret:      {enrolment.totp_secret}")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="platform_staff", description="Manage Rooman platform staff.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a staff member (TOTP enrolled immediately)")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--role", required=True, choices=[r.value for r in PlatformRole])
    create.add_argument("--password-stdin", action="store_true", help="read the password from stdin")

    sub.add_parser("list", help="list staff (no secrets)")

    for name in ("deactivate", "activate", "reset-2fa"):
        p = sub.add_parser(name)
        p.add_argument("--email", required=True)
        p.add_argument("--reason", required=True)

    setpw = sub.add_parser("set-password", help="set a new password (revokes all sessions)")
    setpw.add_argument("--email", required=True)
    setpw.add_argument("--password-stdin", action="store_true")

    args = parser.parse_args(argv)

    from backend.app.core.config import settings
    from backend.app.core.database import SessionLocal
    from backend.app.core.exceptions import AppException
    from backend.app.models.platform import PlatformStaff
    from backend.app.services import platform_auth_service as svc

    if not settings.platform_auth_enabled:
        print("Note: PLATFORM_JWT_SECRET is not set, so platform sign-in is disabled on this server.", file=sys.stderr)

    db = SessionLocal()
    try:
        if args.command == "create":
            enrolment = svc.create_staff(
                db, email=args.email, full_name=args.name, role=PlatformRole(args.role),
                password=_read_password(args), actor=ACTOR,
            )
            _print_enrolment("Platform staff member created.", enrolment)
        elif args.command == "list":
            for s in db.query(PlatformStaff).order_by(PlatformStaff.created_at).all():
                state = "active" if s.is_active else "deactivated"
                print(f"{s.email}\t{s.role.value}\t{state}\tlast login: {s.last_login_at or '-'}")
        elif args.command == "deactivate":
            svc.deactivate_staff(db, email=args.email, reason=args.reason, actor=ACTOR)
            print("Deactivated; all sessions revoked.")
        elif args.command == "activate":
            svc.activate_staff(db, email=args.email, reason=args.reason, actor=ACTOR)
            print("Activated.")
        elif args.command == "reset-2fa":
            _print_enrolment("Two-factor secret replaced; all sessions revoked.",
                             svc.reset_two_factor(db, email=args.email, reason=args.reason, actor=ACTOR))
        elif args.command == "set-password":
            svc.set_password(db, email=args.email, password=_read_password(args), actor=ACTOR)
            print("Password updated; all sessions revoked.")
    except AppException as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
