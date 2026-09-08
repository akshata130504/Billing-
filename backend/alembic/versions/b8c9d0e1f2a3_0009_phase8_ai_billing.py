"""0009_phase8_ai_billing

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-08 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
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
    # 1. ai_conversations
    _create_table(
        'ai_conversations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_ai_conversations_organization_id'), 'ai_conversations', ['organization_id'], unique=False)
    _create_index(op.f('ix_ai_conversations_user_id'), 'ai_conversations', ['user_id'], unique=False)

    # 2. ai_requests
    _create_table(
        'ai_requests',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('conversation_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('mode', sa.Enum('query', 'draft', 'writing', name='ai_request_mode'), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('model_provider', sa.String(length=50), nullable=False, server_default='rooman-local'),
        sa.Column('model_name', sa.String(length=50), nullable=False, server_default='deterministic-v1'),
        sa.Column(
            'status',
            sa.Enum('queued', 'running', 'completed', 'failed', name='ai_request_status'),
            nullable=False,
            server_default='queued',
        ),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('result_data', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['ai_conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_ai_requests_organization_id'), 'ai_requests', ['organization_id'], unique=False)
    _create_index(op.f('ix_ai_requests_conversation_id'), 'ai_requests', ['conversation_id'], unique=False)
    _create_index(op.f('ix_ai_requests_user_id'), 'ai_requests', ['user_id'], unique=False)
    _create_index(op.f('ix_ai_requests_mode'), 'ai_requests', ['mode'], unique=False)
    _create_index(op.f('ix_ai_requests_status'), 'ai_requests', ['status'], unique=False)

    # 3. ai_source_references
    _create_table(
        'ai_source_references',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('request_id', sa.String(length=36), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('source_id', sa.String(length=36), nullable=True),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('snippet', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['request_id'], ['ai_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_ai_source_references_organization_id'), 'ai_source_references', ['organization_id'], unique=False)
    _create_index(op.f('ix_ai_source_references_request_id'), 'ai_source_references', ['request_id'], unique=False)

    # 4. ai_tool_invocations
    _create_table(
        'ai_tool_invocations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('request_id', sa.String(length=36), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('arguments', sa.JSON(), nullable=False),
        sa.Column('result_summary', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='success'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['request_id'], ['ai_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_ai_tool_invocations_organization_id'), 'ai_tool_invocations', ['organization_id'], unique=False)
    _create_index(op.f('ix_ai_tool_invocations_request_id'), 'ai_tool_invocations', ['request_id'], unique=False)

    # 5. ai_action_drafts
    _create_table(
        'ai_action_drafts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('request_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('action_type', sa.Enum('credit_note', name='ai_action_type'), nullable=False),
        sa.Column('proposed_payload', sa.JSON(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('proposed', 'validated', 'approved', 'executed', 'rejected', 'expired', name='ai_action_draft_status'),
            nullable=False,
            server_default='proposed',
        ),
        sa.Column('validation_errors', sa.JSON(), nullable=True),
        sa.Column('executed_entity_type', sa.String(length=50), nullable=True),
        sa.Column('executed_entity_id', sa.String(length=36), nullable=True),
        sa.Column('confirmed_by_id', sa.String(length=36), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['request_id'], ['ai_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_ai_action_drafts_organization_id'), 'ai_action_drafts', ['organization_id'], unique=False)
    _create_index(op.f('ix_ai_action_drafts_request_id'), 'ai_action_drafts', ['request_id'], unique=False)
    _create_index(op.f('ix_ai_action_drafts_user_id'), 'ai_action_drafts', ['user_id'], unique=False)
    _create_index(op.f('ix_ai_action_drafts_action_type'), 'ai_action_drafts', ['action_type'], unique=False)
    _create_index(op.f('ix_ai_action_drafts_status'), 'ai_action_drafts', ['status'], unique=False)


def downgrade() -> None:
    _drop_table('ai_action_drafts')
    _drop_table('ai_tool_invocations')
    _drop_table('ai_source_references')
    _drop_table('ai_requests')
    _drop_table('ai_conversations')

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute('DROP TYPE IF EXISTS ai_action_draft_status;')
        op.execute('DROP TYPE IF EXISTS ai_action_type;')
        op.execute('DROP TYPE IF EXISTS ai_request_status;')
        op.execute('DROP TYPE IF EXISTS ai_request_mode;')
