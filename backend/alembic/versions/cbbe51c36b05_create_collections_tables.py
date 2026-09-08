"""create_collections_tables

Revision ID: cbbe51c36b05
Revises: bb647ceacf66
Create Date: 2026-09-08 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import backend.app.models  # noqa: F401
from backend.app.core.database import Base


# revision identifiers, used by Alembic.
revision: str = 'cbbe51c36b05'
down_revision: Union[str, None] = 'bb647ceacf66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # checkfirst=True: only the new collections tables (not yet present) get created;
    # every table from the prior revision is left untouched.
    Base.metadata.create_all(bind=conn, checkfirst=True)


def downgrade() -> None:
    op.drop_table("promise_to_pay")
    op.drop_table("collection_activities")
    op.drop_table("invoice_collections")
