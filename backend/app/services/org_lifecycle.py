"""Organization lifecycle gate for unattended billing automation (platform phase 1).

The scheduler is the one legitimate cross-tenant actor. It may only start billing work for an
organization that is ACTIVE and not `jobs_paused`: renewal invoices, trial conversion charges,
dunning charge retries, scheduled plan changes, overdue marking, billing emails, recurring
expenses, outbox delivery and automation schedules.

The check is made INSIDE the transaction that performs and commits that work, after any earlier
commit: `automation_allowed` re-reads the organization row under `SELECT ... FOR NO KEY UPDATE`
(PostgreSQL). A concurrent status change (a plain UPDATE of the row) therefore waits until the
billing transaction commits, and a change that committed first is seen by the check. The lock
does not conflict with the FOR KEY SHARE locks taken by inserts that reference the organization,
so ordinary tenant writes are not blocked by it. SQLite (tests, local dev) has no row locks and a
single writer; the check still reads the committed value.

Callers pass `AutomationGuard` into service loops that commit per item, so each item re-checks.
Services called without a guard (API requests, tests) behave exactly as before.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from backend.app.models import Organization, OrganizationStatus


def _is_postgres(db: Session) -> bool:
    bind = db.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def automation_allowed(db: Session, organization_id: Optional[str]) -> bool:
    """True when unattended billing work may run for this organization right now.

    Re-reads status and jobs_paused from the database (never the identity map) and, on
    PostgreSQL, locks the organization row until the current transaction ends. Call it inside
    the transaction that commits the work, after any earlier commit in that code path.
    """
    if not organization_id:
        return False
    stmt = select(Organization.status, Organization.jobs_paused).where(Organization.id == organization_id)
    if _is_postgres(db):
        stmt = stmt.with_for_update(key_share=True)  # FOR NO KEY UPDATE
    row = db.execute(stmt).first()
    if row is None:
        return False
    return row.status == OrganizationStatus.ACTIVE and not row.jobs_paused


def automation_allowed_org_ids() -> Select:
    """Organizations whose queued automation (outbox events, schedules) may be claimed.

    Used as a claim-time filter only, so work for suspended or paused organizations stays queued
    and never crowds out active tenants; the locked per-item `automation_allowed` check remains
    the authority when the work actually runs.
    """
    return select(Organization.id).where(
        Organization.status == OrganizationStatus.ACTIVE,
        Organization.jobs_paused.is_(False),
    )


class AutomationGuard:
    """Per-organization gate handed to service loops; counts how often it refused."""

    def __init__(self, db: Session, organization_id: Optional[str]):
        self.db = db
        self.organization_id = organization_id
        self.refused = 0

    def __call__(self) -> bool:
        allowed = automation_allowed(self.db, self.organization_id)
        if not allowed:
            self.refused += 1
        return allowed
