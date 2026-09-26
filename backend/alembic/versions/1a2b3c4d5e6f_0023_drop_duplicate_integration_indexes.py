"""0023_drop_duplicate_integration_indexes

Databases created before the models declared explicit index names ended up with two
indexes per column on organization_integrations: the migration-named
ix_org_integrations_org_id / ix_org_integrations_provider and the auto-named
ix_organization_integrations_organization_id / ix_organization_integrations_provider
(from index=True). The models now declare only the ix_org_integrations_* pair, so the
auto-named duplicates are dropped - but only when the replacement index exists, so a
column is never left unindexed. Fresh databases never had the duplicates (no-op).

Revision ID: 1a2b3c4d5e6f
Revises: b9c0d1e2f3a4
Create Date: 2026-09-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, None] = 'b9c0d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "organization_integrations"
# duplicate (auto-named) -> replacement (declared in the model)
DUPLICATES = {
    "ix_organization_integrations_organization_id": "ix_org_integrations_org_id",
    "ix_organization_integrations_provider": "ix_org_integrations_provider",
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE):
        return
    existing = {ix["name"] for ix in inspector.get_indexes(TABLE)}
    for duplicate, replacement in DUPLICATES.items():
        if duplicate in existing and replacement in existing:
            op.drop_index(duplicate, table_name=TABLE)


def downgrade() -> None:
    # Intentionally a no-op: re-creating redundant duplicate indexes has no value, and the
    # ix_org_integrations_* indexes that serve the same queries remain in place.
    pass
