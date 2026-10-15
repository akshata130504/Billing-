"""0044 platform notifications: durable Rooman subscription lifecycle emails

- platform_notifications: one row per (lifecycle event, recipient). Queued by the platform lifecycle code in the
  SAME transaction as the state change it reports (so a rolled-back change never emails), and sent only after that
  commit by the platform_notifications scheduler job through Rooman's server SMTP sender. UNIQUE (event_key,
  recipient): the callback, webhook and reconciliation reporting the same event cannot queue it twice. event_key
  is namespaced by kind ("<kind>:<entity>:<id>[:<time>]").
- status pending -> sent | failed (attempts exhausted) | superseded (no longer true when its turn came). Retries
  re-send the stored email only; they never touch payments, subscriptions or entitlements.
- organization_id FK CASCADE: these rows hold personal data (recipient addresses) and are not financial records,
  so an organization purge (none is implemented; deletion is a status today) takes them along instead of being
  blocked by them. The platform audit log keeps the lifecycle changes themselves.
- Platform table, no row level security; never exposed to tenants. Unrelated to the on-hold scheduled plan switch.

Additive only. Downgrade refuses while any notification exists.

Revision ID: c2213243a4b5
Revises: b1213243a4b5
Create Date: 2026-10-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c2213243a4b5"
down_revision = "b1213243a4b5"
branch_labels = None
depends_on = None

TABLE = "platform_notifications"
KINDS = ("subscription_activated", "renewal_payment_received", "payment_past_due", "access_expired",
         "cancellation_scheduled", "cancelled_immediately", "cancellation_effective")
STATUSES = ("pending", "sent", "failed", "superseded")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("platform_subscription_id", sa.String(length=36),
                  sa.ForeignKey("platform_subscriptions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("event_key", sa.String(length=200), nullable=False),
        sa.Column("reference_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=120), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_key", "recipient", name="uq_platform_notifications_event_recipient"),
        sa.CheckConstraint(f"kind IN ({_in(KINDS)})", name="ck_platform_notifications_kind"),
        sa.CheckConstraint(f"status IN ({_in(STATUSES)})", name="ck_platform_notifications_status"),
        sa.CheckConstraint("event_key LIKE kind || ':%'", name="ck_platform_notifications_key_namespace"),
        sa.CheckConstraint("(status = 'sent') = (sent_at IS NOT NULL)", name="ck_platform_notifications_sent_at"),
        sa.CheckConstraint("attempts >= 0", name="ck_platform_notifications_attempts"),
    )
    op.create_index("ix_platform_notifications_status_next", TABLE, ["status", "next_attempt_at"])
    op.create_index("ix_platform_notifications_organization_id", TABLE, ["organization_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return
    if bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar():
        raise RuntimeError("Refusing to downgrade 0044: platform_notifications holds notification history.")
    op.drop_table(TABLE)
