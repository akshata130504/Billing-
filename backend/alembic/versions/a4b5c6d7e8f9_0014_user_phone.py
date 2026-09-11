"""0014_user_phone

Adds `users.phone`. The profile settings screen edits a phone number, but the
User model had no column for it (the existing `phone` lives on Organization), so
the value was being kept in browser localStorage and never reached the server.

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-09-11 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if "users" in {t for t in sa.inspect(op.get_bind()).get_table_names()} and "phone" not in _columns("users"):
        op.add_column("users", sa.Column("phone", sa.String(length=40), nullable=True))


def downgrade() -> None:
    if "phone" in _columns("users"):
        op.drop_column("users", "phone")
