"""0006_phase5_dunning_management

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-08 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- idempotent DDL helpers ---------------------------------------------------
# The baseline migration (bb647ceacf66) builds the schema with
# Base.metadata.create_all(), so by the time this revision runs the tables it
# declares may already exist. Mirrors the guard style used by the lifecycle /
# timesheet migrations.


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
    # 1. dunning_policies
    _create_table(
        'dunning_policies',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('applies_to_autocharge', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('min_amount', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default=sa.text('3')),
        sa.Column('retry_intervals_days', sa.JSON(), nullable=False),
        sa.Column('total_span_days', sa.Integer(), nullable=False, server_default=sa.text('30')),
        sa.Column('notify_on_failure', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notify_on_retry', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notify_on_success', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('first_ach_immediate_cancel', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column(
            'final_action',
            sa.Enum('unpaid', 'cancel_and_void', 'suspend', name='dunning_final_action'),
            nullable=False,
            server_default='unpaid',
        ),
        sa.Column('non_autocharge_grace_days', sa.Integer(), nullable=False, server_default=sa.text('15')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'name', name='uq_dunning_policy_name_per_org'),
    )
    _create_index(op.f('ix_dunning_policies_organization_id'), 'dunning_policies', ['organization_id'], unique=False)

    # 2. dunning_cases
    _create_table(
        'dunning_cases',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('case_number', sa.String(length=32), nullable=False),
        sa.Column('policy_id', sa.String(length=36), nullable=False),
        sa.Column('customer_id', sa.String(length=36), nullable=False),
        sa.Column('subscription_id', sa.String(length=36), nullable=True),
        sa.Column('invoice_id', sa.String(length=36), nullable=False),
        sa.Column(
            'status',
            sa.Enum('open', 'retry_scheduled', 'retrying', 'recovered', 'paused', 'stopped', 'exhausted', 'finalized', name='dunning_case_status'),
            nullable=False,
            server_default='open',
        ),
        sa.Column('trigger_reason', sa.String(length=200), nullable=False),
        sa.Column('amount_due', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='INR'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default=sa.text('3')),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pause_reason', sa.String(length=255), nullable=True),
        sa.Column('stopped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stop_reason', sa.String(length=255), nullable=True),
        sa.Column('recovered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('recovered_by_payment_id', sa.String(length=36), nullable=True),
        sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('final_action_taken', sa.String(length=50), nullable=True),
        sa.Column('metadata_snapshot', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['policy_id'], ['dunning_policies.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['recovered_by_payment_id'], ['payments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'case_number', name='uq_dunning_case_number_per_org'),
    )
    _create_index(op.f('ix_dunning_cases_organization_id'), 'dunning_cases', ['organization_id'], unique=False)
    _create_index(op.f('ix_dunning_cases_case_number'), 'dunning_cases', ['case_number'], unique=False)
    _create_index(op.f('ix_dunning_cases_policy_id'), 'dunning_cases', ['policy_id'], unique=False)
    _create_index(op.f('ix_dunning_cases_customer_id'), 'dunning_cases', ['customer_id'], unique=False)
    _create_index(op.f('ix_dunning_cases_subscription_id'), 'dunning_cases', ['subscription_id'], unique=False)
    _create_index(op.f('ix_dunning_cases_invoice_id'), 'dunning_cases', ['invoice_id'], unique=False)
    _create_index(op.f('ix_dunning_cases_status'), 'dunning_cases', ['status'], unique=False)
    _create_index(op.f('ix_dunning_cases_next_retry_at'), 'dunning_cases', ['next_retry_at'], unique=False)

    # 3. dunning_attempts
    _create_table(
        'dunning_attempts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('case_id', sa.String(length=36), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'status',
            sa.Enum('scheduled', 'processing', 'succeeded', 'failed', 'skipped', name='dunning_attempt_status'),
            nullable=False,
            server_default='scheduled',
        ),
        sa.Column('payment_attempt_id', sa.String(length=36), nullable=True),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.Column('notification_sent', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['dunning_cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['payment_attempt_id'], ['payment_attempts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_dunning_attempts_organization_id'), 'dunning_attempts', ['organization_id'], unique=False)
    _create_index(op.f('ix_dunning_attempts_case_id'), 'dunning_attempts', ['case_id'], unique=False)
    _create_index(op.f('ix_dunning_attempts_status'), 'dunning_attempts', ['status'], unique=False)

    # 4. dunning_communications
    _create_table(
        'dunning_communications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('case_id', sa.String(length=36), nullable=False),
        sa.Column('recipient_email', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('template_type', sa.String(length=50), nullable=False),
        sa.Column('body_preview', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['dunning_cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_dunning_communications_organization_id'), 'dunning_communications', ['organization_id'], unique=False)
    _create_index(op.f('ix_dunning_communications_case_id'), 'dunning_communications', ['case_id'], unique=False)


def downgrade() -> None:
    _drop_table('dunning_communications')
    _drop_table('dunning_attempts')
    _drop_table('dunning_cases')
    _drop_table('dunning_policies')
    # Enum types
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute('DROP TYPE IF EXISTS dunning_attempt_status;')
        op.execute('DROP TYPE IF EXISTS dunning_case_status;')
        op.execute('DROP TYPE IF EXISTS dunning_final_action;')
