"""Platform-managed public website content (landing page CMS).

Not tenant data: no TenantMixin, no organization reference. One `website_pages` row per page
("landing"). Content lives in `website_content_versions`:

- state "draft": at most one per page, editable, never served publicly;
- state "published": immutable snapshots, numbered 1, 2, 3 ... per page; the page points at the
  one that is live (published_version_id). Rolling back publishes a NEW version with the old
  content, so history is never rewritten.
"""
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from backend.app.core.database import Base
from backend.app.models.base import UUIDPrimaryKeyMixin, utcnow


class WebsitePage(Base):
    __tablename__ = "website_pages"

    key = Column(String(40), primary_key=True)
    published_version_id = Column(
        String(36), ForeignKey("website_content_versions.id", ondelete="RESTRICT"), nullable=True
    )
    draft_version_id = Column(
        String(36), ForeignKey("website_content_versions.id", ondelete="SET NULL"), nullable=True
    )
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)


class WebsiteContentVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "website_content_versions"
    __table_args__ = (UniqueConstraint("page_key", "version", name="uq_website_content_version"),)

    page_key = Column(String(40), nullable=False, index=True)
    state = Column(String(16), nullable=False)  # draft | published
    # Published versions: 1, 2, 3 ... per page. Drafts: NULL.
    version = Column(Integer, nullable=True)
    # Drafts: incremented on every save (optimistic concurrency). Published: final revision.
    revision = Column(Integer, nullable=False, default=1)
    content = Column(JSON, nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    note = Column(String(300), nullable=True)
    based_on_version = Column(Integer, nullable=True)  # the published version a draft/rollback came from
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_by_staff_id = Column(String(36), ForeignKey("platform_staff.id", ondelete="RESTRICT"), nullable=True)
