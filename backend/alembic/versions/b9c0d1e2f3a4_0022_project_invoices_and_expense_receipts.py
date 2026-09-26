"""0022_project_invoices_and_expense_receipts

Adds the project -> invoice link table (milestone invoices raised from a project)
and the server-side storage key for uploaded expense receipts.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-09-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9c0d1e2f3a4'
down_revision: Union[str, None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _create_table(table_name, *args, **kwargs):
    if not _inspector().has_table(table_name):
        op.create_table(table_name, *args, **kwargs)


def _create_index(index_name, table_name, *args, **kwargs):
    insp = _inspector()
    if not insp.has_table(table_name):
        return
    if index_name in {ix["name"] for ix in insp.get_indexes(table_name)}:
        return
    op.create_index(index_name, table_name, *args, **kwargs)


def _drop_index(index_name, table_name=None, **kwargs):
    insp = _inspector()
    if table_name is None or not insp.has_table(table_name):
        return
    if index_name not in {ix["name"] for ix in insp.get_indexes(table_name)}:
        return
    op.drop_index(index_name, table_name, **kwargs)


def _drop_table(table_name):
    if _inspector().has_table(table_name):
        op.drop_table(table_name)


def _has_column(table_name, column_name):
    insp = _inspector()
    if not insp.has_table(table_name):
        return False
    return column_name in {c["name"] for c in insp.get_columns(table_name)}


def upgrade() -> None:
    _create_table(
        'project_invoices',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('invoice_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'invoice_id', name='uq_project_invoice'),
    )
    _create_index('ix_project_invoices_organization_id', 'project_invoices', ['organization_id'])
    _create_index('ix_project_invoices_project_id', 'project_invoices', ['project_id'])
    _create_index('ix_project_invoices_invoice_id', 'project_invoices', ['invoice_id'])

    if _inspector().has_table('expenses') and not _has_column('expenses', 'receipt_storage_key'):
        with op.batch_alter_table('expenses') as batch_op:
            batch_op.add_column(sa.Column('receipt_storage_key', sa.String(length=255), nullable=True))


def downgrade() -> None:
    if _has_column('expenses', 'receipt_storage_key'):
        with op.batch_alter_table('expenses') as batch_op:
            batch_op.drop_column('receipt_storage_key')
    _drop_index('ix_project_invoices_invoice_id', 'project_invoices')
    _drop_index('ix_project_invoices_project_id', 'project_invoices')
    _drop_index('ix_project_invoices_organization_id', 'project_invoices')
    _drop_table('project_invoices')
