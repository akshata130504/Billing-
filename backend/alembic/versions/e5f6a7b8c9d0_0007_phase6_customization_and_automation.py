"""0007_phase6_customization_and_automation

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-08 13:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. transaction_number_series
    op.create_table(
        'transaction_number_series',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('module', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('prefix', sa.String(length=20), nullable=False, server_default=''),
        sa.Column('starting_number', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('current_number', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('padding', sa.Integer(), nullable=False, server_default=sa.text('6')),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('suffix', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'module', 'name', name='uq_number_series_name_per_module'),
    )
    op.create_index(op.f('ix_transaction_number_series_organization_id'), 'transaction_number_series', ['organization_id'], unique=False)
    op.create_index(op.f('ix_transaction_number_series_module'), 'transaction_number_series', ['module'], unique=False)

    # 2. document_templates
    op.create_table(
        'document_templates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column(
            'document_type',
            sa.Enum('invoice', 'quote', 'credit_note', 'payment_receipt', 'customer_statement', 'delivery_challan', name='document_type'),
            nullable=False,
            server_default='invoice',
        ),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column(
            'layout_type',
            sa.Enum('spreadsheet', 'standard', 'modern', name='template_layout_type'),
            nullable=False,
            server_default='standard',
        ),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('primary_color', sa.String(length=20), nullable=False, server_default='#1F2937'),
        sa.Column('accent_color', sa.String(length=20), nullable=False, server_default='#3B82F6'),
        sa.Column('font_family', sa.String(length=50), nullable=False, server_default='Helvetica'),
        sa.Column('logo_url', sa.String(length=500), nullable=True),
        sa.Column('header_text', sa.String(length=255), nullable=True),
        sa.Column('footer_text', sa.String(length=255), nullable=True),
        sa.Column('terms_and_conditions', sa.Text(), nullable=True),
        sa.Column('custom_css', sa.Text(), nullable=True),
        sa.Column('show_company_address', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('show_tax_summary', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'document_type', 'name', name='uq_document_template_name'),
    )
    op.create_index(op.f('ix_document_templates_organization_id'), 'document_templates', ['organization_id'], unique=False)

    # 3. reporting_tags
    op.create_table(
        'reporting_tags',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'name', name='uq_reporting_tag_name'),
    )
    op.create_index(op.f('ix_reporting_tags_organization_id'), 'reporting_tags', ['organization_id'], unique=False)

    # 4. web_tabs
    op.create_table(
        'web_tabs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('tab_name', sa.String(length=100), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('allowed_roles', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'tab_name', name='uq_web_tab_name'),
    )
    op.create_index(op.f('ix_web_tabs_organization_id'), 'web_tabs', ['organization_id'], unique=False)

    # 5. automation_rules
    op.create_table(
        'automation_rules',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('module', sa.String(length=50), nullable=False),
        sa.Column(
            'trigger_event',
            sa.Enum('created', 'updated', 'status_changed', 'payment_failed', 'payment_succeeded', 'invoice_overdue', name='automation_trigger_event'),
            nullable=False,
            server_default='created',
        ),
        sa.Column('conditions', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'name', name='uq_automation_rule_name'),
    )
    op.create_index(op.f('ix_automation_rules_organization_id'), 'automation_rules', ['organization_id'], unique=False)

    # 6. automation_actions
    op.create_table(
        'automation_actions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('rule_id', sa.String(length=36), nullable=False),
        sa.Column(
            'action_type',
            sa.Enum('email_alert', 'webhook', 'field_update', name='automation_action_type'),
            nullable=False,
            server_default='email_alert',
        ),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('configuration', sa.JSON(), nullable=False),
        sa.Column('execution_order', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rule_id'], ['automation_rules.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_automation_actions_organization_id'), 'automation_actions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_automation_actions_rule_id'), 'automation_actions', ['rule_id'], unique=False)

    # 7. outbound_webhook_deliveries
    op.create_table(
        'outbound_webhook_deliveries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('rule_id', sa.String(length=36), nullable=True),
        sa.Column('destination_url', sa.String(length=500), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('response_status_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rule_id'], ['automation_rules.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_outbound_webhook_deliveries_organization_id'), 'outbound_webhook_deliveries', ['organization_id'], unique=False)

    # 8. automation_logs
    op.create_table(
        'automation_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('action_type', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.String(length=36), nullable=True),
        sa.Column(
            'status',
            sa.Enum('success', 'failed', 'skipped', name='automation_log_status'),
            nullable=False,
            server_default='success',
        ),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_automation_logs_organization_id'), 'automation_logs', ['organization_id'], unique=False)
    op.create_index(op.f('ix_automation_logs_action_type'), 'automation_logs', ['action_type'], unique=False)
    op.create_index(op.f('ix_automation_logs_status'), 'automation_logs', ['status'], unique=False)
    op.create_index(op.f('ix_automation_logs_occurred_at'), 'automation_logs', ['occurred_at'], unique=False)

    # 9. automation_schedules
    op.create_table(
        'automation_schedules',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column(
            'frequency',
            sa.Enum('hourly', 'daily', 'weekly', 'monthly', name='schedule_frequency'),
            nullable=False,
            server_default='daily',
        ),
        sa.Column('cron_expression', sa.String(length=50), nullable=True),
        sa.Column('target_action', sa.String(length=100), nullable=False),
        sa.Column('last_executed_on', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'name', name='uq_automation_schedule_name'),
    )
    op.create_index(op.f('ix_automation_schedules_organization_id'), 'automation_schedules', ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_table('automation_schedules')
    op.drop_table('automation_logs')
    op.drop_table('outbound_webhook_deliveries')
    op.drop_table('automation_actions')
    op.drop_table('automation_rules')
    op.drop_table('web_tabs')
    op.drop_table('reporting_tags')
    op.drop_table('document_templates')
    op.drop_table('transaction_number_series')

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute('DROP TYPE IF EXISTS schedule_frequency;')
        op.execute('DROP TYPE IF EXISTS automation_log_status;')
        op.execute('DROP TYPE IF EXISTS automation_action_type;')
        op.execute('DROP TYPE IF EXISTS automation_trigger_event;')
        op.execute('DROP TYPE IF EXISTS template_layout_type;')
        op.execute('DROP TYPE IF EXISTS document_type;')
