"""Aggregates every versioned router.

Each entry is (module name, prefix, tags). Modules live in
backend/app/api/v1/endpoints/<module>.py and expose `router`.
"""
import importlib

from fastapi import APIRouter

from backend.app.core.config import settings
from backend.app.core.logging import logger

api_router = APIRouter()

ROUTERS = [
    ("health", "", ["Health"]),
    ("meta", "/meta", ["Meta"]),
    ("auth", "/auth", ["Auth"]),
    ("platform_auth", "/platform/auth", ["Platform Auth"]),
    ("platform_overview", "/platform", ["Platform Console"]),
    ("platform_organizations", "/platform/organizations", ["Platform Console"]),
    ("platform_staff", "/platform/staff", ["Platform Console"]),
    ("users", "/users", ["Users"]),
    ("organization", "", ["Organization & Team"]),
    ("customers", "/customers", ["Customers"]),
    ("products", "/products", ["Catalog"]),
    ("plans", "/plans", ["Catalog"]),
    ("pricing", "/pricing", ["Pricing Engine"]),
    ("catalog", "/catalog", ["Catalog"]),
    ("cpq", "/cpq", ["CPQ"]),
    ("quotes", "/quotes", ["Quotes"]),
    ("subscriptions", "/subscriptions", ["Subscriptions"]),
    ("invoices", "/invoices", ["Invoices"]),
    ("payments", "/payments", ["Payments"]),
    ("credit_notes", "/credit-notes", ["Credit Notes"]),
    ("payment_methods", "", ["Payment Methods"]),
    ("subscription_changes", "", ["Subscriptions & Proration"]),
    ("meters", "/meters", ["Metered Billing"]),
    ("trials", "/trials", ["Trial Management"]),
    ("collections", "/collections", ["Collections"]),
    ("approvals", "/approvals", ["Control Center"]),
    ("dashboard", "", ["Control Center"]),
    ("audit_logs", "/audit-logs", ["Control Center"]),
    ("search", "/search", ["Control Center"]),
    ("imports", "/imports", ["Control Center"]),
    ("admin", "/admin", ["Admin"]),
    ("public_invoices", "/public/invoices", ["Public"]),
    ("public_quotes", "/public/quotes", ["Public"]),
    ("hosted_checkout", "/checkout", ["Hosted Checkout"]),
    ("portal", "/portal", ["Customer Portal"]),
    ("dunning", "", ["Dunning Management"]),
    ("customization", "", ["Customization & Automation"]),
    ("devices", "", ["Client Platforms"]),
    ("ai", "", ["AI in Billing"]),
    ("chat", "/chat", ["Roomi AI Assistant"]),
    ("reports", "/reports", ["Reports"]),
    ("lifecycle", "/lifecycle", ["Customer Lifecycle"]),
    ("timesheets", "/timesheets", ["Timesheets"]),
    ("projects", "/projects", ["Projects"]),
    ("expenses", "/expenses", ["Expenses"]),
    ("webhooks", "/webhooks", ["Webhooks"]),
    ("integrations", "", ["Settings - Integrations"]),
    ("notifications", "", ["Notifications & Email Templates"]),
]

# In test, staging, and production environments, missing endpoints MUST fail fast.
STRICT = settings.ENVIRONMENT in ("test", "staging", "production")


for module_name, prefix, tags in ROUTERS:
    try:
        module = importlib.import_module(f"backend.app.api.v1.endpoints.{module_name}")
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.endswith(module_name) and not STRICT:
            logger.warning("Router module '%s' not present yet; skipping", module_name)
            continue
        raise
    api_router.include_router(module.router, prefix=prefix, tags=tags)
