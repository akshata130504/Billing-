"""0043 platform payment reviews: auditable review cases with resolution history

- platform_payment_reviews: one row per review CASE of a checkout's payment. Opened by
  platform_payment_service._review; repeated findings while open update latest_reason / last_seen_at /
  finding_count; a finding after resolution opens a NEW case, so every resolution stays as recorded. At most one
  open case per checkout (partial unique index). Resolution = category + explanation (+ optional ticket) + who /
  when (staff id, e-mail and role snapshots). Resolving is bookkeeping only - no payment, plan or access change.
- Backfill: every checkout already flagged by 0041 (review_flagged_at set) gets one open case with its current
  reason. platform_checkout_attempts.review_reason / review_flagged_at are kept unchanged.
- Platform table, no row level security. Unrelated to the on-hold scheduled plan switch.

Additive only. Downgrade refuses while any case exists.

Revision ID: b1213243a4b5
Revises: a0213243a4b5
Create Date: 2026-10-14
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "b1213243a4b5"
down_revision = "a0213243a4b5"
branch_labels = None
depends_on = None

TABLE = "platform_payment_reviews"
CATEGORIES = ("no_action_needed", "resolved_by_payment_lifecycle", "handled_in_razorpay", "customer_contacted",
              "duplicate_case", "other")


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("checkout_attempt_id", sa.String(length=36),
                      sa.ForeignKey("platform_checkout_attempts.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
                      nullable=False),
            sa.Column("provider_subscription_id", sa.String(length=64), nullable=True),
            sa.Column("mode", sa.String(length=8), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("first_reason", sa.String(length=300), nullable=False),
            sa.Column("latest_reason", sa.String(length=300), nullable=False),
            sa.Column("finding_count", sa.Integer(), nullable=False),
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolution_category", sa.String(length=40), nullable=True),
            sa.Column("resolution_note", sa.String(length=500), nullable=True),
            sa.Column("resolution_ticket_ref", sa.String(length=100), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_by_staff_id", sa.String(length=36), sa.ForeignKey("platform_staff.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("resolved_by_email", sa.String(length=255), nullable=True),
            sa.Column("resolved_by_role", sa.String(length=32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("status IN ('open', 'resolved')", name="ck_platform_payment_reviews_status"),
            sa.CheckConstraint("resolution_category IS NULL OR resolution_category IN (%s)"
                               % ", ".join(f"'{c}'" for c in CATEGORIES), name="ck_platform_payment_reviews_category"),
            sa.CheckConstraint("(status = 'open' AND resolved_at IS NULL) OR (status = 'resolved' AND resolved_at IS NOT "
                               "NULL AND resolution_category IS NOT NULL AND resolution_note IS NOT NULL)",
                               name="ck_platform_payment_reviews_resolution"),
        )
        op.create_index("uq_platform_payment_reviews_one_open", TABLE, ["checkout_attempt_id"], unique=True,
                        postgresql_where=sa.text("status = 'open'"), sqlite_where=sa.text("status = 'open'"))
        op.create_index("ix_platform_payment_reviews_status_opened", TABLE, ["status", "opened_at"])
        op.create_index("ix_platform_payment_reviews_checkout_attempt_id", TABLE, ["checkout_attempt_id"])
        op.create_index("ix_platform_payment_reviews_organization_id", TABLE, ["organization_id"])

    # Backfill: each checkout flagged before 0043 becomes one open case (skipped when one is already open).
    flagged = bind.execute(sa.text(
        "SELECT id, organization_id, provider_subscription_id, mode, review_reason, review_flagged_at, updated_at "
        "FROM platform_checkout_attempts WHERE review_flagged_at IS NOT NULL")).all()
    for attempt_id, org_id, sid, mode, reason, flagged_at, updated_at in flagged:
        exists = bind.execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE checkout_attempt_id = :a AND status = 'open'"),
                              {"a": attempt_id}).first()
        if exists:
            continue
        bind.execute(sa.text(
            f"INSERT INTO {TABLE} (id, checkout_attempt_id, organization_id, provider_subscription_id, mode, status, "
            "first_reason, latest_reason, finding_count, opened_at, last_seen_at, created_at, updated_at) VALUES "
            "(:id, :a, :o, :s, :m, 'open', :r, :r, 1, :f, :f, :f, :f)"),
            {"id": str(uuid.uuid4()), "a": attempt_id, "o": org_id, "s": sid, "m": mode,
             "r": (reason or "needs_review: reason not recorded")[:300], "f": flagged_at})


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return
    if bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar():
        raise RuntimeError("Refusing to downgrade 0043: platform_payment_reviews holds review cases.")
    op.drop_table(TABLE)
