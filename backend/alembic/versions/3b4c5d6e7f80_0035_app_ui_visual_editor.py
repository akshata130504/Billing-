"""0035_app_ui_visual_editor

Platform-managed, GLOBAL configuration of the tenant application's UI (Super Admin visual editor):

- app_ui_versions: draft (at most one per page, partial unique index) and published (immutable,
  numbered per page) snapshots of a page's structured UI configuration.
- app_ui_pages: one row per configured page; points at the live published version and the draft.

New tables only; no tenant table is touched and no data is written. A page without a row renders
the application's built-in defaults, so existing organizations need nothing. Not tenant data (no
organization_id), hence no row level security - the same model as website_pages (0030).

Revision ID: 3b4c5d6e7f80
Revises: 2f3a4b5c6d7e
Create Date: 2026-10-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b4c5d6e7f80'
down_revision: Union[str, None] = '2f3a4b5c6d7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table('app_ui_versions'):
        op.create_table(
            'app_ui_versions',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('page_key', sa.String(length=40), nullable=False),
            sa.Column('state', sa.String(length=16), nullable=False),
            sa.Column('version', sa.Integer(), nullable=True),
            sa.Column('revision', sa.Integer(), nullable=False),
            sa.Column('content', sa.JSON(), nullable=False),
            sa.Column('content_sha256', sa.String(length=64), nullable=False),
            sa.Column('note', sa.String(length=300), nullable=True),
            sa.Column('based_on_version', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_by_staff_id', sa.String(length=36), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_by_staff_id', sa.String(length=36), nullable=True),
            sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('published_by_staff_id', sa.String(length=36), nullable=True),
            sa.ForeignKeyConstraint(['created_by_staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['updated_by_staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['published_by_staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('page_key', 'version', name='uq_app_ui_version'),
            sa.CheckConstraint("state IN ('draft', 'published')", name='ck_app_ui_version_state'),
            sa.CheckConstraint("(state = 'published') = (version IS NOT NULL)", name='ck_app_ui_version_number'),
        )
        op.create_index('ix_app_ui_versions_page_key', 'app_ui_versions', ['page_key'])
        op.create_index(
            'uq_app_ui_one_draft_per_page', 'app_ui_versions', ['page_key'], unique=True,
            postgresql_where=sa.text("state = 'draft'"), sqlite_where=sa.text("state = 'draft'"),
        )
    if not _has_table('app_ui_pages'):
        op.create_table(
            'app_ui_pages',
            sa.Column('key', sa.String(length=40), nullable=False),
            sa.Column('published_version_id', sa.String(length=36), nullable=True),
            sa.Column('draft_version_id', sa.String(length=36), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_by_staff_id', sa.String(length=36), nullable=True),
            sa.ForeignKeyConstraint(['published_version_id'], ['app_ui_versions.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['draft_version_id'], ['app_ui_versions.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['updated_by_staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('key'),
        )


def downgrade() -> None:
    if _has_table('app_ui_pages'):
        op.drop_table('app_ui_pages')
    if _has_table('app_ui_versions'):
        op.drop_index('uq_app_ui_one_draft_per_page', table_name='app_ui_versions')
        op.drop_index('ix_app_ui_versions_page_key', table_name='app_ui_versions')
        op.drop_table('app_ui_versions')
