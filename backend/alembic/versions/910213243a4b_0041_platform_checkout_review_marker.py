"""0041 platform checkout review marker: a durable "needs review" record on checkout attempts

- platform_checkout_attempts.review_reason (String 300, NULL): the latest review finding for this checkout's
  Razorpay subscription, "<outcome>: <detail>" written by platform_payment_service._review (callback, webhook and
  scheduled reconciliation all pass through it). Application text only - never keys, signatures or payloads.
- platform_checkout_attempts.review_flagged_at (timestamptz, NULL): when the checkout was FIRST flagged.
- Index on review_flagged_at for the platform console's review queue.

Additive only: existing rows keep every value (both columns NULL). Unrelated to the on-hold scheduled plan switch,
which would need a separate later migration. Downgrade refuses while any review is recorded.

Revision ID: 910213243a4b
Revises: 80910213243a
Create Date: 2026-10-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "910213243a4b"
down_revision = "80910213243a"
branch_labels = None
depends_on = None

ATTEMPTS = "platform_checkout_attempts"
INDEX = "ix_platform_checkout_attempts_review_flagged_at"


def _columns() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(ATTEMPTS)}


def _indexes() -> set:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(ATTEMPTS)}


def upgrade() -> None:
    existing = _columns()
    with op.batch_alter_table(ATTEMPTS) as batch:
        if "review_reason" not in existing:
            batch.add_column(sa.Column("review_reason", sa.String(length=300), nullable=True))
        if "review_flagged_at" not in existing:
            batch.add_column(sa.Column("review_flagged_at", sa.DateTime(timezone=True), nullable=True))
    if INDEX not in _indexes():
        op.create_index(INDEX, ATTEMPTS, ["review_flagged_at"])


def downgrade() -> None:
    if "review_flagged_at" in _columns() and op.get_bind().execute(
            sa.text(f"SELECT COUNT(*) FROM {ATTEMPTS} WHERE review_flagged_at IS NOT NULL")).scalar():
        raise RuntimeError("Refusing to downgrade 0041: checkout attempts carry review records.")
    if INDEX in _indexes():
        op.drop_index(INDEX, table_name=ATTEMPTS)
    existing = _columns()
    with op.batch_alter_table(ATTEMPTS) as batch:
        for name in ("review_flagged_at", "review_reason"):
            if name in existing:
                batch.drop_column(name)
