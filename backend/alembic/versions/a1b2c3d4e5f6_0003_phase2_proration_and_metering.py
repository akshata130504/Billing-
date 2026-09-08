"""0003_phase2_proration_and_metering

Revision ID: a1b2c3d4e5f6
Revises: f34df9d017e1
Create Date: 2026-09-08 12:51:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f34df9d017e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. subscription_changes
    op.create_table(
        'subscription_changes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('subscription_id', sa.String(length=36), nullable=False),
        sa.Column('change_type', sa.Enum('upgrade', 'downgrade', 'quantity_change', 'addon_change', 'cancellation', name='sub_change_type'), nullable=False),
        sa.Column('status', sa.Enum('previewed', 'scheduled', 'applied', 'cancelled', 'failed', name='sub_change_status'), nullable=False),
        sa.Column('effective_type', sa.Enum('immediate', 'end_of_term', 'scheduled', name='proration_effective_type'), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('target_plan_id', sa.String(length=36), nullable=True),
        sa.Column('target_quantity', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('proration_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('old_plan_amount', sa.Numeric(precision=14, scale=2), nullable=False, default=0),
        sa.Column('new_plan_amount', sa.Numeric(precision=14, scale=2), nullable=False, default=0),
        sa.Column('prorated_credit', sa.Numeric(precision=14, scale=2), nullable=False, default=0),
        sa.Column('prorated_charge', sa.Numeric(precision=14, scale=2), nullable=False, default=0),
        sa.Column('net_amount', sa.Numeric(precision=14, scale=2), nullable=False, default=0),
        sa.Column('invoice_id', sa.String(length=36), nullable=True),
        sa.Column('credit_note_id', sa.String(length=36), nullable=True),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['credit_note_id'], ['credit_notes.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_plan_id'], ['plans.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subscription_changes_organization_id'), 'subscription_changes', ['organization_id'], unique=False)
    op.create_index(op.f('ix_subscription_changes_subscription_id'), 'subscription_changes', ['subscription_id'], unique=False)
    op.create_index(op.f('ix_subscription_changes_status'), 'subscription_changes', ['status'], unique=False)

    # 2. proration_adjustments
    op.create_table(
        'proration_adjustments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('subscription_change_id', sa.String(length=36), nullable=False),
        sa.Column('subscription_id', sa.String(length=36), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('total_days', sa.Integer(), nullable=False),
        sa.Column('days_used', sa.Integer(), nullable=False),
        sa.Column('days_remaining', sa.Integer(), nullable=False),
        sa.Column('old_unit_price', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('new_unit_price', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('old_quantity', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column('new_quantity', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column('unused_credit', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('remaining_charge', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('net_adjustment', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, default='INR'),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_change_id'], ['subscription_changes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subscription_change_id', name='uq_proration_sub_change')
    )
    op.create_index(op.f('ix_proration_adjustments_organization_id'), 'proration_adjustments', ['organization_id'], unique=False)
    op.create_index(op.f('ix_proration_adjustments_subscription_id'), 'proration_adjustments', ['subscription_id'], unique=False)

    # 3. usage_meters
    op.create_table(
        'usage_meters',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.String(length=300), nullable=True),
        sa.Column('unit_name', sa.String(length=40), nullable=False),
        sa.Column('aggregation_type', sa.Enum('sum', 'max', 'count', 'last', name='meter_aggregation_type'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'code', name='uq_usage_meter_code_per_org')
    )
    op.create_index(op.f('ix_usage_meters_organization_id'), 'usage_meters', ['organization_id'], unique=False)
    op.create_index(op.f('ix_usage_meters_code'), 'usage_meters', ['code'], unique=False)

    # 4. usage_events
    op.create_table(
        'usage_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('meter_id', sa.String(length=36), nullable=False),
        sa.Column('customer_id', sa.String(length=36), nullable=False),
        sa.Column('subscription_id', sa.String(length=36), nullable=True),
        sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('properties', sa.JSON(), nullable=True),
        sa.Column('status', sa.Enum('accepted', 'rejected', 'corrected', name='usage_event_status'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['meter_id'], ['usage_meters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'meter_id', 'idempotency_key', name='uq_usage_event_idempotency')
    )
    op.create_index(op.f('ix_usage_events_organization_id'), 'usage_events', ['organization_id'], unique=False)
    op.create_index(op.f('ix_usage_events_meter_id'), 'usage_events', ['meter_id'], unique=False)
    op.create_index(op.f('ix_usage_events_customer_id'), 'usage_events', ['customer_id'], unique=False)
    op.create_index(op.f('ix_usage_events_subscription_id'), 'usage_events', ['subscription_id'], unique=False)
    op.create_index(op.f('ix_usage_events_idempotency_key'), 'usage_events', ['idempotency_key'], unique=False)

    # 5. usage_aggregates
    op.create_table(
        'usage_aggregates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('meter_id', sa.String(length=36), nullable=False),
        sa.Column('subscription_id', sa.String(length=36), nullable=False),
        sa.Column('billing_cycle_id', sa.String(length=36), nullable=True),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('total_quantity', sa.Numeric(precision=16, scale=4), nullable=False, default=0),
        sa.Column('rated_amount', sa.Numeric(precision=14, scale=2), nullable=False, default=0),
        sa.Column('status', sa.Enum('open', 'calculated', 'finalized', name='usage_aggregate_status'), nullable=False),
        sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('invoice_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['billing_cycle_id'], ['billing_cycles.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['meter_id'], ['usage_meters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'meter_id', 'subscription_id', 'period_start', 'period_end', name='uq_sub_meter_period')
    )
    op.create_index(op.f('ix_usage_aggregates_organization_id'), 'usage_aggregates', ['organization_id'], unique=False)
    op.create_index(op.f('ix_usage_aggregates_meter_id'), 'usage_aggregates', ['meter_id'], unique=False)
    op.create_index(op.f('ix_usage_aggregates_subscription_id'), 'usage_aggregates', ['subscription_id'], unique=False)
    op.create_index(op.f('ix_usage_aggregates_status'), 'usage_aggregates', ['status'], unique=False)


def downgrade() -> None:
    op.drop_table('usage_aggregates')
    op.drop_table('usage_events')
    op.drop_table('usage_meters')
    op.drop_table('proration_adjustments')
    op.drop_table('subscription_changes')
