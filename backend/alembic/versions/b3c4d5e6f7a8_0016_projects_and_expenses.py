"""0016_projects_and_expenses

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-09-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
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


def upgrade() -> None:
    # 1. projects table
    _create_table(
        'projects',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('customer_id', sa.String(length=36), nullable=True),
        sa.Column('customer_name', sa.String(length=200), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('billing_method', sa.String(length=50), nullable=False, server_default='fixed_price'),
        sa.Column('budget', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column('project_manager', sa.String(length=200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    _create_index('ix_projects_organization_id', 'projects', ['organization_id'])
    _create_index('ix_projects_name', 'projects', ['name'])
    _create_index('ix_projects_customer_id', 'projects', ['customer_id'])
    _create_index('ix_projects_status', 'projects', ['status'])

    # 2. expenses table
    _create_table(
        'expenses',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='INR'),
        sa.Column('billable', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('customer_id', sa.String(length=36), nullable=True),
        sa.Column('customer_name', sa.String(length=200), nullable=True),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('project_name', sa.String(length=200), nullable=True),
        sa.Column('billable_amount', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('tax_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('invoice_treatment', sa.String(length=50), nullable=True),
        sa.Column('invoice_id', sa.String(length=36), nullable=True),
        sa.Column('payment_method', sa.String(length=50), nullable=False, server_default='Cash'),
        sa.Column('paid_by', sa.String(length=200), nullable=False, server_default='Self'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='recorded'),
        sa.Column('receipt_file_name', sa.String(length=255), nullable=True),
        sa.Column('receipt_file_size', sa.String(length=50), nullable=True),
        sa.Column('receipt_file_type', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    _create_index('ix_expenses_organization_id', 'expenses', ['organization_id'])
    _create_index('ix_expenses_date', 'expenses', ['date'])
    _create_index('ix_expenses_category', 'expenses', ['category'])
    _create_index('ix_expenses_status', 'expenses', ['status'])
    _create_index('ix_expenses_customer_id', 'expenses', ['customer_id'])
    _create_index('ix_expenses_project_id', 'expenses', ['project_id'])
    _create_index('ix_expenses_billable', 'expenses', ['billable'])

    # 3. recurring_expenses table
    _create_table(
        'recurring_expenses',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='INR'),
        sa.Column('frequency', sa.String(length=50), nullable=False, server_default='monthly'),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('never_ends', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('next_run', sa.Date(), nullable=True),
        sa.Column('last_run', sa.Date(), nullable=True),
        sa.Column('billable', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('customer_id', sa.String(length=36), nullable=True),
        sa.Column('customer_name', sa.String(length=200), nullable=True),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('project_name', sa.String(length=200), nullable=True),
        sa.Column('billable_amount', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('invoice_treatment', sa.String(length=50), nullable=True),
        sa.Column('payment_method', sa.String(length=50), nullable=False, server_default='Cash'),
        sa.Column('paid_by', sa.String(length=200), nullable=False, server_default='Self'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    _create_index('ix_recurring_expenses_organization_id', 'recurring_expenses', ['organization_id'])
    _create_index('ix_recurring_expenses_status', 'recurring_expenses', ['status'])
    _create_index('ix_recurring_expenses_frequency', 'recurring_expenses', ['frequency'])


def downgrade() -> None:
    _drop_index('ix_recurring_expenses_frequency', table_name='recurring_expenses')
    _drop_index('ix_recurring_expenses_status', table_name='recurring_expenses')
    _drop_index('ix_recurring_expenses_organization_id', table_name='recurring_expenses')
    _drop_table('recurring_expenses')

    _drop_index('ix_expenses_billable', table_name='expenses')
    _drop_index('ix_expenses_project_id', table_name='expenses')
    _drop_index('ix_expenses_customer_id', table_name='expenses')
    _drop_index('ix_expenses_status', table_name='expenses')
    _drop_index('ix_expenses_category', table_name='expenses')
    _drop_index('ix_expenses_date', table_name='expenses')
    _drop_index('ix_expenses_organization_id', table_name='expenses')
    _drop_table('expenses')

    _drop_index('ix_projects_status', table_name='projects')
    _drop_index('ix_projects_customer_id', table_name='projects')
    _drop_index('ix_projects_name', table_name='projects')
    _drop_index('ix_projects_organization_id', table_name='projects')
    _drop_table('projects')
