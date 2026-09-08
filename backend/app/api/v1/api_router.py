"""Aggregates every versioned router.

Each entry is (module name, prefix, tags). Modules live in
backend/app/api/v1/endpoints/<module>.py and expose `router`.
"""
import importlib

from fastapi import APIRouter

from backend.app.core.logging import logger

api_router = APIRouter()

ROUTERS = [
    ("health", "", ["Health"]),
    ("meta", "/meta", ["Meta"]),
    ("auth", "/auth", ["Auth"]),
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
    ("collections", "/collections", ["Collections"]),
    ("approvals", "/approvals", ["Control Center"]),
    ("dashboard", "", ["Control Center"]),
    ("audit_logs", "/audit-logs", ["Control Center"]),
    ("search", "/search", ["Control Center"]),
    ("imports", "/imports", ["Control Center"]),
    ("admin", "/admin", ["Admin"]),
    ("public_invoices", "/public/invoices", ["Public"]),
    ("public_quotes", "/public/quotes", ["Public"]),
    ("webhooks", "/webhooks", ["Webhooks"]),
]

# STRICT is flipped to True once every module exists; during the build a missing
# module is logged instead of crashing the app so partial work stays testable.
STRICT = False

for module_name, prefix, tags in ROUTERS:
    try:
        module = importlib.import_module(f"backend.app.api.v1.endpoints.{module_name}")
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.endswith(module_name) and not STRICT:
            logger.warning("Router module '%s' not present yet; skipping", module_name)
            continue
        raise
    api_router.include_router(module.router, prefix=prefix, tags=tags)
