"""0004_phase3_trial_management

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
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
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'TRIAL_EXPIRED'")

    # 1. trial_periods
    _create_table(
        'trial_periods',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('subscription_id', sa.String(length=36), nullable=False),
        sa.Column('trial_start_date', sa.Date(), nullable=False),
        sa.Column('trial_end_date', sa.Date(), nullable=False),
        sa.Column('extension_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_extensions_allowed', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('allow_customer_extension', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('allow_early_conversion', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('auto_charge_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('fallback_plan_id', sa.String(length=36), nullable=True),
        sa.Column(
            'status',
            sa.Enum('active', 'expired', 'converted', 'cancelled', name='trial_period_status'),
            nullable=False,
            server_default='active',
        ),
        sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['fallback_plan_id'], ['plans.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'subscription_id', name='uq_trial_period_subscription'),
    )
    _create_index(op.f('ix_trial_periods_organization_id'), 'trial_periods', ['organization_id'], unique=False)
    _create_index(op.f('ix_trial_periods_subscription_id'), 'trial_periods', ['subscription_id'], unique=False)
    _create_index(op.f('ix_trial_periods_trial_end_date'), 'trial_periods', ['trial_end_date'], unique=False)
    _create_index(op.f('ix_trial_periods_status'), 'trial_periods', ['status'], unique=False)

    # 2. trial_extensions
    _create_table(
        'trial_extensions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('trial_period_id', sa.String(length=36), nullable=False),
        sa.Column('subscription_id', sa.String(length=36), nullable=False),
        sa.Column('previous_trial_end', sa.Date(), nullable=False),
        sa.Column('new_trial_end', sa.Date(), nullable=False),
        sa.Column('extended_days', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('is_customer_initiated', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('extended_by_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['extended_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trial_period_id'], ['trial_periods.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_trial_extensions_organization_id'), 'trial_extensions', ['organization_id'], unique=False)
    _create_index(op.f('ix_trial_extensions_trial_period_id'), 'trial_extensions', ['trial_period_id'], unique=False)
    _create_index(op.f('ix_trial_extensions_subscription_id'), 'trial_extensions', ['subscription_id'], unique=False)

    # 3. trial_conversion_attempts
    _create_table(
        'trial_conversion_attempts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('trial_period_id', sa.String(length=36), nullable=False),
        sa.Column('subscription_id', sa.String(length=36), nullable=False),
        sa.Column(
            'attempt_type',
            sa.Enum('automatic_trial_end', 'customer_early_conversion', 'admin_conversion', name='trial_conversion_attempt_type'),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('pending', 'succeeded', 'failed', name='trial_conversion_status'),
            nullable=False,
            server_default='pending',
        ),
        sa.Column('payment_method_id', sa.String(length=36), nullable=True),
        sa.Column('payment_attempt_id', sa.String(length=36), nullable=True),
        sa.Column('invoice_id', sa.String(length=36), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['payment_attempt_id'], ['payment_attempts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['payment_method_id'], ['customer_payment_methods.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trial_period_id'], ['trial_periods.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_trial_conversion_attempts_organization_id'), 'trial_conversion_attempts', ['organization_id'], unique=False)
    _create_index(op.f('ix_trial_conversion_attempts_trial_period_id'), 'trial_conversion_attempts', ['trial_period_id'], unique=False)
    _create_index(op.f('ix_trial_conversion_attempts_subscription_id'), 'trial_conversion_attempts', ['subscription_id'], unique=False)

    # 4. trial_reminders
    _create_table(
        'trial_reminders',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('trial_period_id', sa.String(length=36), nullable=False),
        sa.Column('subscription_id', sa.String(length=36), nullable=False),
        sa.Column('reminder_type', sa.String(length=64), nullable=False),
        sa.Column('scheduled_for', sa.Date(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notification_delivery_id', sa.String(length=36), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['notification_delivery_id'], ['notification_deliveries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trial_period_id'], ['trial_periods.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_trial_reminders_organization_id'), 'trial_reminders', ['organization_id'], unique=False)
    _create_index(op.f('ix_trial_reminders_trial_period_id'), 'trial_reminders', ['trial_period_id'], unique=False)
    _create_index(op.f('ix_trial_reminders_subscription_id'), 'trial_reminders', ['subscription_id'], unique=False)
    _create_index(op.f('ix_trial_reminders_scheduled_for'), 'trial_reminders', ['scheduled_for'], unique=False)


def downgrade() -> None:
    _drop_index(op.f('ix_trial_reminders_scheduled_for'), table_name='trial_reminders')
    _drop_index(op.f('ix_trial_reminders_subscription_id'), table_name='trial_reminders')
    _drop_index(op.f('ix_trial_reminders_trial_period_id'), table_name='trial_reminders')
    _drop_index(op.f('ix_trial_reminders_organization_id'), table_name='trial_reminders')
    _drop_table('trial_reminders')

    _drop_index(op.f('ix_trial_conversion_attempts_subscription_id'), table_name='trial_conversion_attempts')
    _drop_index(op.f('ix_trial_conversion_attempts_trial_period_id'), table_name='trial_conversion_attempts')
    _drop_index(op.f('ix_trial_conversion_attempts_organization_id'), table_name='trial_conversion_attempts')
    _drop_table('trial_conversion_attempts')

    _drop_index(op.f('ix_trial_extensions_subscription_id'), table_name='trial_extensions')
    _drop_index(op.f('ix_trial_extensions_trial_period_id'), table_name='trial_extensions')
    _drop_index(op.f('ix_trial_extensions_organization_id'), table_name='trial_extensions')
    _drop_table('trial_extensions')

    _drop_index(op.f('ix_trial_periods_status'), table_name='trial_periods')
    _drop_index(op.f('ix_trial_periods_trial_end_date'), table_name='trial_periods')
    _drop_index(op.f('ix_trial_periods_subscription_id'), table_name='trial_periods')
    _drop_index(op.f('ix_trial_periods_organization_id'), table_name='trial_periods')
    _drop_table('trial_periods')
