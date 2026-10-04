"""What a tenant access grant may reach (docs/platform-administration-design.md section 7).

An EXPLICIT allow-list of (GET/HEAD, route template) -> scope. Every other tenant route is refused
for grant contexts - including every write (POST/PUT/PATCH/DELETE), exports and bulk downloads,
integration/credential settings, reports, imports, AI, devices, authentication and team
management. New routes are refused by default until someone deliberately adds them here, and
tests/test_access_grants.py fails if a mapped route stops existing or a write sneaks in.

No write scope exists in this release; the design's optional write scopes are not offered.
"""
from typing import Dict, FrozenSet, Optional

from backend.app.models.access_grants import GrantScope

V1 = "/api/v1"

GRANT_READ_ROUTES: Dict[str, GrantScope] = {
    # READ_METADATA: organization profile and team list (names, roles). Always granted.
    "/organization": GrantScope.READ_METADATA,
    "/team": GrantScope.READ_METADATA,
    # READ_CUSTOMERS: customers, contacts, customer lifecycle.
    "/customers": GrantScope.READ_CUSTOMERS,
    "/customers/{customer_id}": GrantScope.READ_CUSTOMERS,
    "/lifecycle": GrantScope.READ_CUSTOMERS,
    "/lifecycle/kpis": GrantScope.READ_CUSTOMERS,
    "/lifecycle/{customer_id}": GrantScope.READ_CUSTOMERS,
    "/lifecycle/{customer_id}/timeline": GrantScope.READ_CUSTOMERS,
    # READ_QUOTES: quotes, quote PDFs, CPQ deals, approvals on quotes.
    "/quotes": GrantScope.READ_QUOTES,
    "/quotes/{quote_id}": GrantScope.READ_QUOTES,
    "/quotes/{quote_id}/pdf": GrantScope.READ_QUOTES,
    "/cpq/deals": GrantScope.READ_QUOTES,
    "/cpq/deals/{deal_id}": GrantScope.READ_QUOTES,
    "/approvals": GrantScope.READ_QUOTES,
    # READ_INVOICES: invoices, invoice PDFs, credit notes.
    "/invoices": GrantScope.READ_INVOICES,
    "/invoices/summary": GrantScope.READ_INVOICES,
    "/invoices/{invoice_id}": GrantScope.READ_INVOICES,
    "/invoices/{invoice_id}/pdf": GrantScope.READ_INVOICES,
    "/customers/{customer_id}/invoices": GrantScope.READ_INVOICES,
    "/credit-notes": GrantScope.READ_INVOICES,
    "/credit-notes/summary": GrantScope.READ_INVOICES,
    "/credit-notes/{credit_note_id}": GrantScope.READ_INVOICES,
    # READ_PAYMENTS: payments, allocations, dunning cases; payment methods are masked (brand/last4).
    "/payments": GrantScope.READ_PAYMENTS,
    "/payments/summary": GrantScope.READ_PAYMENTS,
    "/payments/{payment_id}": GrantScope.READ_PAYMENTS,
    "/invoices/{invoice_id}/payments": GrantScope.READ_PAYMENTS,
    "/invoices/{invoice_id}/payment-attempts": GrantScope.READ_PAYMENTS,
    "/customers/{customer_id}/payments": GrantScope.READ_PAYMENTS,
    "/customers/{customer_id}/payment-methods": GrantScope.READ_PAYMENTS,
    "/dunning/cases": GrantScope.READ_PAYMENTS,
    "/dunning/cases/{case_id}": GrantScope.READ_PAYMENTS,
    "/dunning/metrics": GrantScope.READ_PAYMENTS,
    "/collections/invoices": GrantScope.READ_PAYMENTS,
    "/collections/invoices/{invoice_id}": GrantScope.READ_PAYMENTS,
    "/collections/invoices/{invoice_id}/activities": GrantScope.READ_PAYMENTS,
    # READ_SUBSCRIPTIONS: subscriptions, plans and catalog, trials, usage meters.
    "/subscriptions": GrantScope.READ_SUBSCRIPTIONS,
    "/subscriptions/summary": GrantScope.READ_SUBSCRIPTIONS,
    "/subscriptions/{subscription_id}": GrantScope.READ_SUBSCRIPTIONS,
    "/subscriptions/{subscription_id}/changes": GrantScope.READ_SUBSCRIPTIONS,
    "/subscriptions/{subscription_id}/invoices": GrantScope.READ_SUBSCRIPTIONS,
    "/customers/{customer_id}/subscriptions": GrantScope.READ_SUBSCRIPTIONS,
    "/plans": GrantScope.READ_SUBSCRIPTIONS,
    "/plans/{plan_id}": GrantScope.READ_SUBSCRIPTIONS,
    "/products": GrantScope.READ_SUBSCRIPTIONS,
    "/products/{product_id}": GrantScope.READ_SUBSCRIPTIONS,
    "/trials": GrantScope.READ_SUBSCRIPTIONS,
    "/trials/{subscription_id}": GrantScope.READ_SUBSCRIPTIONS,
    "/meters": GrantScope.READ_SUBSCRIPTIONS,
    "/meters/{meter_id}": GrantScope.READ_SUBSCRIPTIONS,
    # READ_AUDIT: the tenant's own audit log (never its export).
    "/audit-logs": GrantScope.READ_AUDIT,
    # READ_CONFIG: templates, automation rules, number series, dunning policies (never credentials).
    "/templates": GrantScope.READ_CONFIG,
    "/templates/{template_id}": GrantScope.READ_CONFIG,
    "/automation/rules": GrantScope.READ_CONFIG,
    "/automation/rules/{rule_id}": GrantScope.READ_CONFIG,
    "/automation/schedules": GrantScope.READ_CONFIG,
    "/automation/schedules/{schedule_id}": GrantScope.READ_CONFIG,
    "/notifications/templates": GrantScope.READ_CONFIG,
    "/notifications/templates/{template_id}": GrantScope.READ_CONFIG,
    "/settings/number-series": GrantScope.READ_CONFIG,
    "/settings/number-series/{series_id}": GrantScope.READ_CONFIG,
    "/dunning/policies": GrantScope.READ_CONFIG,
}

READ_METHODS: FrozenSet[str] = frozenset({"GET", "HEAD"})

# Human-readable areas (tenant-facing banner and audit summaries).
SCOPE_LABELS: Dict[GrantScope, str] = {
    GrantScope.READ_METADATA: "Organization profile and team",
    GrantScope.READ_CUSTOMERS: "Customers",
    GrantScope.READ_QUOTES: "Quotes and deals",
    GrantScope.READ_INVOICES: "Invoices and credit notes",
    GrantScope.READ_PAYMENTS: "Payments and collections",
    GrantScope.READ_SUBSCRIPTIONS: "Subscriptions, plans and catalog",
    GrantScope.READ_AUDIT: "Audit log",
    GrantScope.READ_CONFIG: "Templates and automation settings",
}


def required_scope(method: str, route_template: Optional[str]) -> Optional[GrantScope]:
    """The scope a grant needs for this request, or None when grants may never make it."""
    if method.upper() not in READ_METHODS or not route_template or not route_template.startswith(V1):
        return None
    return GRANT_READ_ROUTES.get(route_template[len(V1):])
