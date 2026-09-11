"""0013_user_avatar_url

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-09-10 23:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    insp = _inspector()
    if insp.has_table('users'):
        columns = [col['name'] for col in insp.get_columns('users')]
        if 'avatar_url' not in columns:
            op.add_column(
                'users',
                sa.Column('avatar_url', sa.String(500), nullable=True),
            )


def downgrade() -> None:
    insp = _inspector()
    if insp.has_table('users'):
        columns = [col['name'] for col in insp.get_columns('users')]
        if 'avatar_url' in columns:
            op.drop_column('users', 'avatar_url')
