"""0005_phase4_hosted_checkout_and_portal

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-08 13:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
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
    # 1. checkout_templates
    _create_table(
        'checkout_templates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column(
            'template_type',
            sa.Enum('single_page', 'multi_page', name='checkout_template_type'),
            nullable=False,
            server_default='single_page',
        ),
        sa.Column('primary_color', sa.String(length=20), nullable=False, server_default='#2563eb'),
        sa.Column('accent_color', sa.String(length=20), nullable=False, server_default='#1e40af'),
        sa.Column('logo_url', sa.String(length=500), nullable=True),
        sa.Column('button_text', sa.String(length=50), nullable=False, server_default='Pay Now'),
        sa.Column('allow_quantity_edit', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('show_order_summary', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('redirect_url', sa.String(length=500), nullable=True),
        sa.Column('thank_you_message', sa.Text(), nullable=True),
        sa.Column('error_message_template', sa.String(length=255), nullable=True),
        sa.Column('custom_fields', sa.JSON(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_checkout_templates_organization_id'), 'checkout_templates', ['organization_id'], unique=False)

    # 2. checkout_sessions
    _create_table(
        'checkout_sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('template_id', sa.String(length=36), nullable=True),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column(
            'purpose',
            sa.Enum(
                'invoice_payment',
                'new_subscription',
                'update_subscription',
                'update_card',
                'one_time_addon',
                'add_payment_method',
                name='checkout_session_purpose',
            ),
            nullable=False,
            server_default='invoice_payment',
        ),
        sa.Column(
            'status',
            sa.Enum(
                'created',
                'pending',
                'processing',
                'successful',
                'failed',
                'cancelled',
                'expired',
                name='checkout_session_status',
            ),
            nullable=False,
            server_default='created',
        ),
        sa.Column('customer_id', sa.String(length=36), nullable=True),
        sa.Column('invoice_id', sa.String(length=36), nullable=True),
        sa.Column('subscription_id', sa.String(length=36), nullable=True),
        sa.Column('plan_id', sa.String(length=36), nullable=True),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='INR'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payment_attempt_id', sa.String(length=36), nullable=True),
        sa.Column('payment_id', sa.String(length=36), nullable=True),
        sa.Column('save_payment_method', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('metadata_snapshot', sa.JSON(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['payment_attempt_id'], ['payment_attempts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['template_id'], ['checkout_templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_checkout_sessions_organization_id'), 'checkout_sessions', ['organization_id'], unique=False)
    _create_index(op.f('ix_checkout_sessions_token'), 'checkout_sessions', ['token'], unique=True)
    _create_index(op.f('ix_checkout_sessions_status'), 'checkout_sessions', ['status'], unique=False)
    _create_index(op.f('ix_checkout_sessions_customer_id'), 'checkout_sessions', ['customer_id'], unique=False)
    _create_index(op.f('ix_checkout_sessions_invoice_id'), 'checkout_sessions', ['invoice_id'], unique=False)
    _create_index(op.f('ix_checkout_sessions_subscription_id'), 'checkout_sessions', ['subscription_id'], unique=False)
    _create_index(op.f('ix_checkout_sessions_expires_at'), 'checkout_sessions', ['expires_at'], unique=False)

    # 3. customer_portal_settings
    _create_table(
        'customer_portal_settings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('portal_name', sa.String(length=100), nullable=False, server_default='Billing Portal'),
        sa.Column('portal_url_slug', sa.String(length=64), nullable=True),
        sa.Column('banner_message', sa.Text(), nullable=True),
        sa.Column('auto_invite_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('prevent_duplicate_payments', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('allow_self_signup', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('allow_document_upload', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('allow_document_forwarding', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('allow_save_payment_methods', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('save_payment_method_default', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('prevent_deselecting_save_payment', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('enable_identity_verification_public_links', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('trials_allow_customer_extension', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('trials_max_extensions', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('trials_activate_immediately', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', name='uq_portal_settings_organization'),
    )
    _create_index(op.f('ix_customer_portal_settings_portal_url_slug'), 'customer_portal_settings', ['portal_url_slug'], unique=False)

    # 4. customer_portal_users
    _create_table(
        'customer_portal_users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('customer_id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=200), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('mfa_secret', sa.String(length=64), nullable=True),
        sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'email', name='uq_portal_user_email_per_org'),
    )
    _create_index(op.f('ix_customer_portal_users_organization_id'), 'customer_portal_users', ['organization_id'], unique=False)
    _create_index(op.f('ix_customer_portal_users_customer_id'), 'customer_portal_users', ['customer_id'], unique=False)
    _create_index(op.f('ix_customer_portal_users_email'), 'customer_portal_users', ['email'], unique=False)

    # 5. customer_portal_sessions
    _create_table(
        'customer_portal_sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('portal_user_id', sa.String(length=36), nullable=False),
        sa.Column('token', sa.String(length=128), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['portal_user_id'], ['customer_portal_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_customer_portal_sessions_portal_user_id'), 'customer_portal_sessions', ['portal_user_id'], unique=False)
    _create_index(op.f('ix_customer_portal_sessions_token'), 'customer_portal_sessions', ['token'], unique=True)
    _create_index(op.f('ix_customer_portal_sessions_expires_at'), 'customer_portal_sessions', ['expires_at'], unique=False)


def downgrade() -> None:
    _drop_index(op.f('ix_customer_portal_sessions_expires_at'), table_name='customer_portal_sessions')
    _drop_index(op.f('ix_customer_portal_sessions_token'), table_name='customer_portal_sessions')
    _drop_index(op.f('ix_customer_portal_sessions_portal_user_id'), table_name='customer_portal_sessions')
    _drop_table('customer_portal_sessions')

    _drop_index(op.f('ix_customer_portal_users_email'), table_name='customer_portal_users')
    _drop_index(op.f('ix_customer_portal_users_customer_id'), table_name='customer_portal_users')
    _drop_index(op.f('ix_customer_portal_users_organization_id'), table_name='customer_portal_users')
    _drop_table('customer_portal_users')

    _drop_index(op.f('ix_customer_portal_settings_portal_url_slug'), table_name='customer_portal_settings')
    _drop_table('customer_portal_settings')

    _drop_index(op.f('ix_checkout_sessions_expires_at'), table_name='checkout_sessions')
    _drop_index(op.f('ix_checkout_sessions_subscription_id'), table_name='checkout_sessions')
    _drop_index(op.f('ix_checkout_sessions_invoice_id'), table_name='checkout_sessions')
    _drop_index(op.f('ix_checkout_sessions_customer_id'), table_name='checkout_sessions')
    _drop_index(op.f('ix_checkout_sessions_status'), table_name='checkout_sessions')
    _drop_index(op.f('ix_checkout_sessions_token'), table_name='checkout_sessions')
    _drop_index(op.f('ix_checkout_sessions_organization_id'), table_name='checkout_sessions')
    _drop_table('checkout_sessions')

    _drop_index(op.f('ix_checkout_templates_organization_id'), table_name='checkout_templates')
    _drop_table('checkout_templates')
