"""Customer accounts and their contacts."""
import enum

from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CustomerStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Customer(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("organization_id", "customer_number", name="uq_customer_number_per_org"),)

    customer_number = Column(String(24), nullable=False)
    display_name = Column(String(200), nullable=False, index=True)
    company_name = Column(String(200), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(40), nullable=True)
    website = Column(String(255), nullable=True)
    gstin = Column(String(15), nullable=True)
    pan = Column(String(10), nullable=True)
    tax_exempt = Column(Boolean, nullable=False, default=False)
    currency = Column(String(3), nullable=False, default="INR")
    payment_terms_days = Column(Integer, nullable=False, default=30)
    status = Column(Enum(CustomerStatus, name="customer_status"), nullable=False, default=CustomerStatus.ACTIVE)

    billing_address_line1 = Column(String(255), nullable=True)
    billing_address_line2 = Column(String(255), nullable=True)
    billing_city = Column(String(120), nullable=True)
    billing_state = Column(String(120), nullable=True)
    billing_postal_code = Column(String(20), nullable=True)
    billing_country = Column(String(2), nullable=False, default="IN")

    notes = Column(Text, nullable=True)
    # Opaque token that lets the customer open their own statement page.
    portal_token = Column(String(64), nullable=True, unique=True, index=True)

    contacts = relationship("CustomerContact", back_populates="customer", cascade="all, delete-orphan")


class CustomerContact(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "customer_contacts"

    customer_id = Column(String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(40), nullable=True)
    designation = Column(String(120), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)

    customer = relationship("Customer", back_populates="contacts")
