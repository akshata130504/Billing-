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

from fastapi import status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import AppException, NotFoundError
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


# --- customer-facing pages (public invoice/quote/checkout links, customer portal) -----------------

CUSTOMER_UNAVAILABLE_MESSAGE = (
    "This merchant's account is temporarily unavailable. No new payments or changes can be made "
    "right now; please contact the merchant."
)


class OrganizationUnavailableError(AppException):
    """A customer-initiated action on a non-ACTIVE organization (design §8: suspended orgs take no
    new payments or Razorpay orders, quotes cannot be accepted or declined, the portal is read-only)."""

    def __init__(self, message: str = CUSTOMER_UNAVAILABLE_MESSAGE):
        super().__init__(message=message, code="ORGANIZATION_UNAVAILABLE", status_code=status.HTTP_403_FORBIDDEN)


def _status_of(db: Session, organization_id: Optional[str]) -> Optional[OrganizationStatus]:
    if not organization_id:
        return None
    return db.scalars(select(Organization.status).where(Organization.id == organization_id)).first()


def customer_actions_allowed(db: Session, organization_id: Optional[str]) -> bool:
    """True when customers may start new payments or change anything for this organization.

    Payments the customer already completed (signature verification, webhooks) are always
    recorded; this only gates starting new ones.
    """
    return _status_of(db, organization_id) == OrganizationStatus.ACTIVE


def assert_customer_actions_allowed(db: Session, organization_id: Optional[str]) -> None:
    if not customer_actions_allowed(db, organization_id):
        raise OrganizationUnavailableError()


def customer_pages_visible(db: Session, organization_id: Optional[str]) -> bool:
    """Read-only customer access (portal, public links): ACTIVE and SUSPENDED only."""
    return _status_of(db, organization_id) in (OrganizationStatus.ACTIVE, OrganizationStatus.SUSPENDED)


def assert_customer_pages_visible(db: Session, organization_id: Optional[str]) -> None:
    """Public invoice/quote/checkout links of an organization that is pending deletion, deleted,
    or was never approved are refused as invalid links (design §8)."""
    if not customer_pages_visible(db, organization_id):
        raise NotFoundError("This link is no longer available.")
