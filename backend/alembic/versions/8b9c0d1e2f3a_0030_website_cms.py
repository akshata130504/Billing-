"""0030_website_cms

Platform-managed public website content (landing page CMS), docs/platform-console.md:

- website_content_versions: draft (at most one per page, editable) and published (immutable,
  numbered per page) snapshots of the structured landing-page content.
- website_pages: one row per page; points at the live published version and the current draft.

New tables only; no tenant table is touched and no data is written. The first published version
is seeded on first use from the bundled original page content (backend/app/website/).

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
Create Date: 2026-10-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b9c0d1e2f3a'
down_revision: Union[str, None] = '7a8b9c0d1e2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table('website_content_versions'):
        op.create_table(
            'website_content_versions',
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
            sa.UniqueConstraint('page_key', 'version', name='uq_website_content_version'),
        )
        op.create_index('ix_website_content_versions_page_key', 'website_content_versions', ['page_key'])
    if not _has_table('website_pages'):
        op.create_table(
            'website_pages',
            sa.Column('key', sa.String(length=40), nullable=False),
            sa.Column('published_version_id', sa.String(length=36), nullable=True),
            sa.Column('draft_version_id', sa.String(length=36), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_by_staff_id', sa.String(length=36), nullable=True),
            sa.ForeignKeyConstraint(['published_version_id'], ['website_content_versions.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['draft_version_id'], ['website_content_versions.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['updated_by_staff_id'], ['platform_staff.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('key'),
        )


def downgrade() -> None:
    if _has_table('website_pages'):
        op.drop_table('website_pages')
    if _has_table('website_content_versions'):
        op.drop_index('ix_website_content_versions_page_key', table_name='website_content_versions')
        op.drop_table('website_content_versions')
