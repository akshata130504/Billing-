"""Tests for ORM Tenant Isolation and PostgreSQL Row Level Security (RLS).

Validates Section 20 and Section 21 of the platform administration design:
- Explicit tenant context enforcement
- Fail closed behavior when context is absent
- Query without explicit WHERE filter returns only context organization's rows
- Cross-tenant queries are blocked
- Strict mode raises MissingTenantContextError
- System context bypasses filtering for scheduler and maintenance
- PostgreSQL RLS enforces row isolation at database engine level
"""
import uuid
from decimal import Decimal
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal, engine
from backend.app.core.tenant_context import (
    MissingTenantContextError,
    get_current_tenant_id,
    is_system_context,
    reset_tenant_context,
    set_tenant_context,
    strict_context,
    system_context,
    tenant_context,
)
from backend.app.models import (
    Customer,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Membership,
    MemberRole,
    MembershipStatus,
    Organization,
    User,
)


def _make_org(db: Session, name: str) -> Organization:
    org = Organization(name=name, slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_customer(db: Session, org_id: str, name: str) -> Customer:
    cust = Customer(
        organization_id=org_id,
        customer_number=f"CUS-{uuid.uuid4().hex[:6].upper()}",
        display_name=name,
        currency="INR",
        payment_terms_days=30,
    )
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return cust


def test_tenant_context_manager():
    """Verify tenant_context sets and restores context variable."""
    assert get_current_tenant_id() is None
    with tenant_context("org-alpha"):
        assert get_current_tenant_id() == "org-alpha"
        with tenant_context("org-beta"):
            assert get_current_tenant_id() == "org-beta"
        assert get_current_tenant_id() == "org-alpha"
    assert get_current_tenant_id() is None


def test_system_context_manager():
    """Verify system_context sets and restores context variable."""
    assert not is_system_context()
    with system_context():
        assert is_system_context()
    assert not is_system_context()


def test_orm_isolation_filters_to_context_org(db: Session):
    """A query deliberately written without a filter returns only the context org's rows."""
    org1 = _make_org(db, "Org One")
    org2 = _make_org(db, "Org Two")

    with system_context():
        c1 = _make_customer(db, org1.id, "Customer Org1")
        c2 = _make_customer(db, org2.id, "Customer Org2")

    # In Org1 context: select(Customer) without ANY where filter returns only c1
    with tenant_context(org1.id):
        customers = db.scalars(select(Customer)).all()
        ids = {c.id for c in customers}
        assert c1.id in ids
        assert c2.id not in ids

    # In Org2 context: select(Customer) returns only c2
    with tenant_context(org2.id):
        customers = db.scalars(select(Customer)).all()
        ids = {c.id for c in customers}
        assert c2.id in ids
        assert c1.id not in ids


def test_orm_isolation_fails_closed_without_context(db: Session):
    """Without tenant context or system context, querying tenant-scoped models fails closed (0 rows)."""
    org = _make_org(db, "Org FailClosed")
    with system_context():
        cust = _make_customer(db, org.id, "Cust FC")

    # Outside any context
    reset_tenant_context()
    customers = db.scalars(select(Customer)).all()
    # Fails closed: 0 rows returned
    assert cust.id not in {c.id for c in customers}
    assert customers == []


def test_orm_isolation_strict_mode_raises(db: Session):
    """In strict mode, querying tenant-scoped models without context raises MissingTenantContextError."""
    reset_tenant_context()
    with strict_context(True):
        with pytest.raises(MissingTenantContextError):
            db.scalars(select(Customer)).all()


def test_system_context_allows_cross_tenant_reads(db: Session):
    """System context allows cross-tenant queries for background jobs/scheduler."""
    org1 = _make_org(db, "Org Sys1")
    org2 = _make_org(db, "Org Sys2")

    with system_context():
        c1 = _make_customer(db, org1.id, "Cust Sys1")
        c2 = _make_customer(db, org2.id, "Cust Sys2")

        customers = db.scalars(select(Customer)).all()
        ids = {c.id for c in customers}
        assert c1.id in ids
        assert c2.id in ids


def test_orm_isolation_applies_to_joined_and_related_tables(db: Session):
    """Isolation criteria apply to joined child tables (e.g. Invoice -> InvoiceItem)."""
    org1 = _make_org(db, "Org Inv1")
    org2 = _make_org(db, "Org Inv2")

    with system_context():
        c1 = _make_customer(db, org1.id, "Cust Inv1")
        inv1 = Invoice(
            organization_id=org1.id,
            customer_id=c1.id,
            invoice_number=f"INV-{uuid.uuid4().hex[:6].upper()}",
            status=InvoiceStatus.SENT,
            issue_date=org1.created_at.date() if hasattr(org1.created_at, 'date') else None,
            due_date=org1.created_at.date() if hasattr(org1.created_at, 'date') else None,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            amount_due=Decimal("100.00"),
            public_token=uuid.uuid4().hex,
        )
        db.add(inv1)
        db.flush()
        item1 = InvoiceItem(
            organization_id=org1.id,
            invoice_id=inv1.id,
            description="Item 1",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            amount=Decimal("100.00"),
        )
        db.add(item1)
        db.commit()

    # Query items under org1 context: found
    with tenant_context(org1.id):
        items = db.scalars(select(InvoiceItem)).all()
        assert any(i.id == item1.id for i in items)

    # Query items under org2 context: empty
    with tenant_context(org2.id):
        items = db.scalars(select(InvoiceItem)).all()
        assert not any(i.id == item1.id for i in items)


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL RLS requires PostgreSQL dialect")
def test_postgresql_rls_enforcement():
    """Verify PostgreSQL Row Level Security rejects cross-tenant reads even via raw SQL."""
    with SessionLocal() as db:
        org1 = _make_org(db, "PG Org 1")
        org2 = _make_org(db, "PG Org 2")
        org1_id = org1.id
        org2_id = org2.id

        with system_context():
            c1 = _make_customer(db, org1_id, "Cust PG1")
            c2 = _make_customer(db, org2_id, "Cust PG2")
            c1_id = c1.id
            c2_id = c2.id

    # In PostgreSQL, superusers (like 'postgres') bypass RLS.
    # We test RLS under an application role without SUPERUSER or BYPASSRLS permissions.
    role = f"rb_rls_test_{uuid.uuid4().hex[:8]}"
    with engine.connect() as conn:
        conn.execute(text(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS'))
        conn.execute(text(f'GRANT ALL ON customers, organizations TO "{role}"'))
        conn.commit()

    try:
        with engine.connect() as conn:
            conn.execute(text(f'SET ROLE "{role}"'))

            # Context set to Org1:
            conn.execute(text("SELECT set_config('app.current_organization_id', :oid, true)"), {"oid": org1_id})
            rows = conn.execute(text("SELECT id, display_name FROM customers WHERE organization_id = :oid"), {"oid": org1_id}).fetchall()
            ids = [r[0] for r in rows]
            assert c1_id in ids

            # Attempt to read Org2's customer via raw SQL under Org1 context: RLS prevents returning Org2 rows
            rows_other = conn.execute(text("SELECT id, display_name FROM customers WHERE organization_id = :oid"), {"oid": org2_id}).fetchall()
            assert rows_other == []

            # Raw SELECT without WHERE returns only Org1 rows
            all_rows = conn.execute(text("SELECT id FROM customers")).fetchall()
            all_ids = [r[0] for r in all_rows]
            assert c1_id in all_ids
            assert c2_id not in all_ids

            # Context set to __NONE__: 0 rows returned
            conn.execute(text("SELECT set_config('app.current_organization_id', '__NONE__', true)"))
            unscoped_rows = conn.execute(text("SELECT id FROM customers")).fetchall()
            assert unscoped_rows == []

            # Context set to __SYSTEM__: both rows visible
            conn.execute(text("SELECT set_config('app.current_organization_id', '__SYSTEM__', true)"))
            system_rows = conn.execute(text("SELECT id FROM customers")).fetchall()
            system_ids = [r[0] for r in system_rows]
            assert c1_id in system_ids
            assert c2_id in system_ids
            conn.rollback()
    finally:
        with engine.connect() as conn:
            conn.execute(text("RESET ROLE"))
            conn.execute(text(f'REVOKE ALL ON customers, organizations FROM "{role}"'))
            conn.execute(text(f'DROP ROLE "{role}"'))
            conn.commit()
