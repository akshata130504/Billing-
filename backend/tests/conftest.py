"""Shared pytest fixtures.

Tests run against an isolated database. By default that is a throwaway SQLite
file; set TEST_DATABASE_URL to a PostgreSQL URL (CI does) to run the exact same
suite against Postgres. Settings are forced before the application is imported.
"""
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

_TEST_DB_PATH = Path(__file__).resolve().parent / ".test_rooman_billing.sqlite3"
os.environ.setdefault("ENVIRONMENT", "test")
os.environ["DEBUG"] = "false"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "unit-test-secret-key-0123456789abcdef0123456789abcdef"
# Platform (Rooman staff) tokens are signed with a different key from tenant tokens.
os.environ["PLATFORM_JWT_SECRET"] = "unit-test-platform-signing-9f8e7d6c5b4a39281706f5e4d3c2b1a0"
os.environ["PLATFORM_APP_ORIGIN"] = "http://platform.test"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_TEST_DB_PATH.as_posix()}")
os.environ["RAZORPAY_KEY_ID"] = ""
os.environ["RAZORPAY_KEY_SECRET"] = ""
os.environ["SMTP_HOST"] = ""
os.environ["AUTH_RATE_LIMIT"] = "1000/minute"
# Public limits are per (client IP, endpoint) - every TestClient request shares one IP, so the
# production defaults would throttle unrelated tests. Rate-limit tests monkeypatch their own limit.
os.environ["PUBLIC_RATE_LIMIT"] = "1000/minute"
os.environ["PUBLIC_ACTION_RATE_LIMIT"] = "1000/minute"
os.environ["WEBHOOK_RATE_LIMIT"] = "1000/minute"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, close_all_sessions  # noqa: E402

from backend.app.core.database import Base, SessionLocal, engine  # noqa: E402
from backend.app.core.security import create_access_token, hash_password  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models import Customer, Invoice, InvoiceStatus, Membership, MemberRole, MembershipStatus, Organization, Plan, Product, User  # noqa: E402


def _local_iana_timezone() -> str:
    """An IANA zone whose current offset equals this machine's, so tests that build dates with
    date.today() agree with services that use the organization's local date (orgs default to
    Asia/Kolkata, which differs from a UTC CI runner for 5.5 hours a day)."""
    from datetime import datetime, timezone as dt_timezone
    from zoneinfo import ZoneInfo, available_timezones

    now = datetime.now(dt_timezone.utc)
    local_offset = now.astimezone().utcoffset()
    for name in ("UTC", "Asia/Kolkata", "Europe/London", "America/New_York", *sorted(available_timezones())):
        try:
            if now.astimezone(ZoneInfo(name)).utcoffset() == local_offset:
                return name
        except Exception:  # pragma: no cover - broken tzdata entry
            continue
    return "UTC"


TEST_ORG_TIMEZONE = _local_iana_timezone()


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    if engine.dialect.name == "postgresql":
        # PostgreSQL runs on the real migrated schema (RLS policies, triggers, constraints come
        # from Alembic, not create_all): bring the test database to head first - a no-op when
        # it already is - then empty every table.
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
        command.upgrade(alembic_cfg, "head")
        with engine.connect() as conn:
            conn.execute(
                __import__("sqlalchemy").text("""
                    SET session_replication_role = 'replica';
                    DO $$ DECLARE
                        r RECORD;
                    BEGIN
                        FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = current_schema() AND tablename != 'alembic_version') LOOP
                            EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
                        END LOOP;
                    END $$;
                    SET session_replication_role = 'origin';
                """)
            )
            conn.commit()
    else:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    yield
    # A session left open by any test would hold row/table locks and make DROP TABLE wait
    # forever on PostgreSQL; close every ORM session and return pooled connections first.
    close_all_sessions()
    engine.dispose()
    if engine.dialect.name != "postgresql":
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
    # Only remove the default file when THIS session used it: a run pointed elsewhere via
    # TEST_DATABASE_URL must never delete the database of another run in progress.
    if "TEST_DATABASE_URL" not in os.environ and _TEST_DB_PATH.exists():
        try:
            _TEST_DB_PATH.unlink()
        except OSError:
            pass


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class Tenant:
    """A fresh organization with an owner user, plus helpers to mint tokens for other roles."""

    def __init__(self, db: Session, suffix: str):
        self.db = db
        self.suffix = suffix
        self.organization = Organization(name=f"Test Org {suffix}", slug=f"test-org-{suffix}", timezone=TEST_ORG_TIMEZONE)
        db.add(self.organization)
        db.flush()
        self.owner = self.add_member("owner", MemberRole.OWNER)
        db.commit()

    def add_member(self, label: str, role: MemberRole) -> User:
        user = User(
            email=f"{label}-{self.suffix}@example.test",
            full_name=f"{label.title()} {self.suffix}",
            hashed_password=hash_password("Str0ngPassw0rd!"),
        )
        self.db.add(user)
        self.db.flush()
        self.db.add(
            Membership(
                organization_id=self.organization.id,
                user_id=user.id,
                role=role,
                status=MembershipStatus.ACTIVE,
            )
        )
        self.db.flush()
        return user

    def headers(self, user: User | None = None, role: MemberRole | None = None) -> dict:
        user = user or self.owner
        role = role or MemberRole.OWNER
        token = create_access_token(user.id, self.organization.id, role.value)
        return {"Authorization": f"Bearer {token}"}

    def headers_for_role(self, role: MemberRole) -> dict:
        user = self.add_member(f"{role.value}-{uuid.uuid4().hex[:6]}", role)
        self.db.commit()
        return self.headers(user, role)

    def customer(self, **overrides) -> Customer:
        from backend.app.core.tenant_context import tenant_context
        with tenant_context(self.organization.id):
            n = int(self.organization.customer_next_number or 1)
            self.organization.customer_next_number = n + 1
            data = dict(
                organization_id=self.organization.id,
                customer_number=f"CUS-{n:06d}",
                display_name=f"Customer {n} {self.suffix}",
                email=f"customer{n}-{self.suffix}@example.test",
                currency="INR",
                payment_terms_days=30,
            )
            data.update(overrides)
            customer = Customer(**data)
            self.db.add(customer)
            self.db.commit()
            self.db.refresh(customer)
            return customer

    def product_with_plan(self, unit_amount="1000.00", interval="monthly", trial_days=0) -> tuple[Product, Plan]:
        from backend.app.core.tenant_context import tenant_context
        from backend.app.models import BillingInterval, PricingModel, ProductType

        with tenant_context(self.organization.id):
            code = uuid.uuid4().hex[:8]
            product = Product(
                organization_id=self.organization.id,
                name=f"Product {code}",
                sku=f"SKU-{code}",
                type=ProductType.SUBSCRIPTION,
                tax_rate_pct=Decimal("18"),
            )
            self.db.add(product)
            self.db.flush()
            plan = Plan(
                organization_id=self.organization.id,
                product_id=product.id,
                name=f"Plan {code}",
                code=f"PLAN-{code}",
                billing_interval=BillingInterval(interval),
                interval_count=1,
                pricing_model=PricingModel.PER_UNIT,
                unit_amount=Decimal(unit_amount),
                currency="INR",
                trial_days=trial_days,
            )
            self.db.add(plan)
            self.db.commit()
            self.db.refresh(product)
            self.db.refresh(plan)
            return product, plan

    def invoice(self, customer: Customer, amount="1000.00", status=InvoiceStatus.SENT) -> Invoice:
        from backend.app.core.tenant_context import tenant_context

        with tenant_context(self.organization.id):
            today = date.today()
            code = uuid.uuid4().hex[:6].upper()
            amt = Decimal(amount)
            inv = Invoice(
                organization_id=self.organization.id,
                invoice_number=f"INV-{code}",
                customer_id=customer.id,
                status=status,
                issue_date=today,
                due_date=today + timedelta(days=30),
                subtotal=amt,
                total=amt,
                amount_paid=Decimal("0.00"),
                amount_due=amt,
                public_token=uuid.uuid4().hex,
            )
            self.db.add(inv)
            self.db.commit()
            self.db.refresh(inv)
            return inv


@pytest.fixture(autouse=True)
def _clean_context_per_test():
    from backend.app.core.tenant_context import _is_strict_context, _is_system_context, reset_tenant_context
    reset_tenant_context()
    _is_system_context.set(False)
    _is_strict_context.set(False)
    yield
    reset_tenant_context()
    _is_system_context.set(False)
    _is_strict_context.set(False)


@pytest.fixture()
def tenant(db: Session):
    from backend.app.core.tenant_context import tenant_context
    t = Tenant(db, uuid.uuid4().hex[:8])
    with tenant_context(t.organization.id):
        yield t



@pytest.fixture()
def auth_headers(tenant: Tenant) -> dict:
    """Owner credentials for a fresh organization."""
    return tenant.headers()


@pytest.fixture()
def today() -> date:
    return date.today()
