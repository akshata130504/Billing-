"""Organization lifecycle gate for unattended billing automation (platform phase 1).

The scheduler is the one legitimate cross-tenant actor. It may only start billing work for an
organization that is ACTIVE, not `jobs_paused` and has a paid subscription (not in its free trial,
running or ended): renewal invoices, trial conversion charges, dunning charge retries, scheduled
plan changes, overdue marking, billing emails, recurring expenses, outbox delivery and automation
schedules. A self-service organization is in its trial phase until a Platform Administrator
approves its subscription request (organizations.module_access 'trial' -> 'entitled'); during
that time its users can create billing data, but no money is collected (`billing_collection_allowed`,
`payment_collection_allowed`). Organizations that predate plans ('unrestricted') are unaffected.

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


# organizations.module_access while a self-service organization has no approved subscription yet.
TRIAL_ACCESS = "trial"


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
    stmt = select(Organization.status, Organization.jobs_paused, Organization.module_access).where(
        Organization.id == organization_id
    )
    if _is_postgres(db):
        stmt = stmt.with_for_update(key_share=True)  # FOR NO KEY UPDATE
    row = db.execute(stmt).first()
    if row is None:
        return False
    return row.status == OrganizationStatus.ACTIVE and not row.jobs_paused and row.module_access != TRIAL_ACCESS


def automation_allowed_org_ids() -> Select:
    """Organizations whose queued automation (outbox events, schedules) may be claimed.

    Used as a claim-time filter only, so work for suspended or paused organizations stays queued
    and never crowds out active tenants; the locked per-item `automation_allowed` check remains
    the authority when the work actually runs.
    """
    return select(Organization.id).where(
        Organization.status == OrganizationStatus.ACTIVE,
        Organization.jobs_paused.is_(False),
        Organization.module_access != TRIAL_ACCESS,
    )


# --- real money: only with a paid subscription -----------------------------------------------------

BILLING_NOT_ACTIVE_MESSAGE = (
    "Payment collection is not active during the free trial. It starts once Rooman approves your "
    "organization's subscription."
)
PAYMENTS_NOT_ACCEPTED_MESSAGE = (
    "This merchant is not accepting online payments yet. Please contact the merchant to pay."
)


class BillingCollectionNotActiveError(AppException):
    """A tenant user tried to collect money (charge a card, retry a charge) during the free trial."""

    def __init__(self, message: str = BILLING_NOT_ACTIVE_MESSAGE):
        super().__init__(message=message, code="BILLING_COLLECTION_NOT_ACTIVE", status_code=status.HTTP_403_FORBIDDEN)


def _status_and_access(db: Session, organization_id: Optional[str]):
    if not organization_id:
        return None
    return db.execute(
        select(Organization.status, Organization.module_access).where(Organization.id == organization_id)
    ).first()


def billing_collection_allowed(db: Session, organization_id: Optional[str]) -> bool:
    """True when real money may be collected for this organization: ACTIVE with a paid subscription
    (or one that predates plans). False during the free trial, running or ended."""
    row = _status_and_access(db, organization_id)
    return row is not None and row.status == OrganizationStatus.ACTIVE and row.module_access != TRIAL_ACCESS


def assert_billing_collection_allowed(db: Session, organization_id: Optional[str]) -> None:
    if not billing_collection_allowed(db, organization_id):
        raise BillingCollectionNotActiveError()


def payment_collection_allowed(db: Session, organization_id: Optional[str]) -> bool:
    """Customer-facing payments (pay links, hosted checkout, portal payments): the merchant must
    accept customer actions AND have a paid subscription. Quote accept/decline is NOT a payment and
    keeps using `customer_actions_allowed`."""
    return customer_actions_allowed(db, organization_id) and billing_collection_allowed(db, organization_id)


def assert_payment_collection_allowed(db: Session, organization_id: Optional[str]) -> None:
    if not customer_actions_allowed(db, organization_id):
        raise OrganizationUnavailableError()
    if not billing_collection_allowed(db, organization_id):
        raise OrganizationUnavailableError(PAYMENTS_NOT_ACCEPTED_MESSAGE)


class AutomationGuard:
    """Per-organization gate handed to service loops; counts how often it refused.

    `module`: the optional product module (core/modules.json) the work belongs to; the work is
    also refused while the organization is not entitled to it (services/org_access.py)."""

    def __init__(self, db: Session, organization_id: Optional[str], module: Optional[str] = None):
        self.db = db
        self.organization_id = organization_id
        self.module = module
        self.refused = 0

    def __call__(self) -> bool:
        allowed = automation_allowed(self.db, self.organization_id)
        if allowed and self.module:
            from backend.app.services.org_access import module_entitled

            allowed = module_entitled(self.db, self.organization_id, self.module)
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
