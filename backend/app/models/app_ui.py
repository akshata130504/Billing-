"""Platform-managed configuration of the TENANT APPLICATION's user interface (visual editor).

GLOBAL scope: one configuration per application page key (e.g. "overview", "navigation", "theme"),
applied to every organization. Not tenant data: no TenantMixin, no organization reference, so it
is outside the ORM tenant filter and PostgreSQL row level security, like website_pages. A
per-organization scope is a separate, later milestone (it needs its own tenant-scoped table under
RLS) and is deliberately NOT modelled here.

Each page key may have no row at all: the tenant application then renders its built-in defaults.
`app_ui_versions` holds:

- state "draft": at most one per page (partial unique index), editable, never served to tenants;
- state "published": immutable snapshots, numbered 1, 2, 3 ... per page. Rolling back publishes a
  NEW version with an old version's content, so history is never rewritten.

Content is a structured document validated by schemas/app_ui.py (a typed registry of pages,
components and allowed properties) before it is stored - never code, HTML or CSS.
"""
from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text

from backend.app.core.database import Base
from backend.app.models.base import UUIDPrimaryKeyMixin, utcnow


class AppUiPage(Base):
    __tablename__ = "app_ui_pages"

    key = Column(String(40), primary_key=True)
    published_version_id = Column(String(36), ForeignKey("app_ui_versions.id", ondelete="RESTRICT"), nullable=True)
    draft_version_id = Column(String(36), ForeignKey("app_ui_versions.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)


class AppUiVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "app_ui_versions"
    __table_args__ = (
        UniqueConstraint("page_key", "version", name="uq_app_ui_version"),
        CheckConstraint("state IN ('draft', 'published')", name="ck_app_ui_version_state"),
        CheckConstraint("(state = 'published') = (version IS NOT NULL)", name="ck_app_ui_version_number"),
        Index("uq_app_ui_one_draft_per_page", "page_key", unique=True,
              postgresql_where=text("state = 'draft'"), sqlite_where=text("state = 'draft'")),
    )

    page_key = Column(String(40), nullable=False, index=True)
    state = Column(String(16), nullable=False)  # draft | published
    version = Column(Integer, nullable=True)  # published: 1, 2, 3 ... per page; drafts: NULL
    revision = Column(Integer, nullable=False, default=1)  # drafts: +1 per save (optimistic concurrency)
    content = Column(JSON, nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    note = Column(String(300), nullable=True)  # change summary / reason
    based_on_version = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)
