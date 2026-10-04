"""0034 retire fabricated landing-page examples from an untouched published landing page

The original bundled landing content (seeded into the CMS as version 1 on first use) contained
invented customer names and KPIs presented as real. The bundled default now labels them as example
scenarios, but environments that already seeded the page keep serving the old copy from the
database.

Upgrade: only when the PUBLISHED landing version is byte-identical (content_sha256) to that original
default - i.e. nobody ever edited it - publish the corrected default as a new version. History is
append-only (the old version stays, rollback still works); customised pages are never touched.
Downgrade: nothing (re-publishing fabricated copy is never wanted).

Revision ID: 2f3a4b5c6d7e
Revises: 1e2f3a4b5c6d
Create Date: 2026-10-03
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "2f3a4b5c6d7e"
down_revision = "1e2f3a4b5c6d"
branch_labels = None
depends_on = None

LANDING = "landing"
# sha256 of the canonical, validated original bundled landing_default.json (commit 51a70a0).
ORIGINAL_DEFAULT_SHA256 = "6804bf5bc57e31e09954cfd4c6599b0414c1cdf9517c0fa7bea2ccbd96d975b7"
NOTE = "Corrected default: example customer scenarios labelled as examples (migration 0034)"

pages = sa.table(
    "website_pages",
    sa.column("key", sa.String),
    sa.column("published_version_id", sa.String),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
versions = sa.table(
    "website_content_versions",
    sa.column("id", sa.String),
    sa.column("page_key", sa.String),
    sa.column("state", sa.String),
    sa.column("version", sa.Integer),
    sa.column("revision", sa.Integer),
    sa.column("content", sa.JSON),
    sa.column("content_sha256", sa.String),
    sa.column("note", sa.String),
    sa.column("based_on_version", sa.Integer),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("published_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    bind = op.get_bind()
    published = bind.execute(
        sa.select(versions.c.version, versions.c.content_sha256)
        .select_from(pages.join(versions, versions.c.id == pages.c.published_version_id))
        .where(pages.c.key == LANDING)
    ).first()
    if published is None or published.content_sha256 != ORIGINAL_DEFAULT_SHA256:
        return  # never seeded (first use seeds the corrected default) or customised by staff

    from backend.app.services.website_service import seed_content, sha256

    content = seed_content()
    now = datetime.now(timezone.utc)
    next_version = int(
        bind.execute(sa.select(sa.func.max(versions.c.version)).where(versions.c.page_key == LANDING)).scalar() or 0
    ) + 1
    new_id = str(uuid.uuid4())
    bind.execute(
        versions.insert().values(
            id=new_id, page_key=LANDING, state="published", version=next_version, revision=1, content=content,
            content_sha256=sha256(content), note=NOTE, based_on_version=published.version,
            created_at=now, updated_at=now, published_at=now,
        )
    )
    bind.execute(pages.update().where(pages.c.key == LANDING).values(published_version_id=new_id, updated_at=now))


def downgrade() -> None:
    pass
