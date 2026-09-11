"""0012_user_tokens_valid_after

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-09-10 18:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    insp = _inspector()
    if insp.has_table('users'):
        columns = [col['name'] for col in insp.get_columns('users')]
        if 'tokens_valid_after' not in columns:
            op.add_column(
                'users',
                sa.Column('tokens_valid_after', sa.DateTime(timezone=True), nullable=True),
            )


def downgrade() -> None:
    insp = _inspector()
    if insp.has_table('users'):
        columns = [col['name'] for col in insp.get_columns('users')]
        if 'tokens_valid_after' in columns:
            op.drop_column('users', 'tokens_valid_after')
