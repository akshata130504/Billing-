"""Which backend files belong to which product module (modularization).

Module keys follow backend/app/core/modules.json. Only modules that have reached their P0 phase
are mapped; every other file stays unassigned until its own phase. Paths are relative to backend/app.
"""

MODULES: dict[str, set[str]] = {
    "projects": {
        "api/v1/endpoints/projects.py",
        "services/project_service.py",
        "schemas/projects.py",
        "models/projects.py",
    },
    # Products and plans only. Offerings and price books (/catalog, catalog_cpq_service) stay with CPQ.
    "products": {
        "api/v1/endpoints/products.py",
        "api/v1/endpoints/plans.py",
        "services/catalog_service.py",
        "schemas/catalog.py",
        "models/catalog.py",
    },
    # The portal-access routes live in the customers router; their logic stays in customer_portal_service.
    "customers": {
        "api/v1/endpoints/customers.py",
        "services/customer_service.py",
        "schemas/customers.py",
        "models/customers.py",
    },
    # timesheet_service imports invoice_service at module level and invoice_service imports it back
    # inside a function; a move must keep both imports where they are.
    "timesheets": {
        "api/v1/endpoints/timesheets.py",
        "services/timesheet_service.py",
        "schemas/timesheets.py",
        "models/timesheets.py",
    },
    # expense_service is in the lazy 21-service cycle; its imports stay where they are.
    "expenses": {
        "api/v1/endpoints/expenses.py",
        "services/expense_service.py",
    },
    # Routers only; quote_service and the CPQ services stay in services/ until issue #12 is decided.
    "quotes": {
        "api/v1/endpoints/quotes.py",
        "api/v1/endpoints/cpq.py",
    },
    # Routers only; invoice_service and credit_service stay in services/ until issue #12 is decided.
    "invoices": {
        "api/v1/endpoints/invoices.py",
        "api/v1/endpoints/credit_notes.py",
    },
    # Router only; subscription_service stays in services/ until issue #12 is decided. /plans is in products.
    "subscriptions": {
        "api/v1/endpoints/subscriptions.py",
    },
    # Routers only; collection_service and dunning_service stay in services/ until issue #12 is decided.
    "collections": {
        "api/v1/endpoints/collections.py",
        "api/v1/endpoints/dunning.py",
    },
    # payment_service is in the lazy 21-service cycle; its imports stay where they are.
    "payments": {
        "api/v1/endpoints/payments.py",
        "services/payment_service.py",
    },
    "platforms": {
        "api/v1/endpoints/devices.py",
        "services/device_service.py",
    },
    "integrations": {
        "api/v1/endpoints/integrations.py",
        "services/integrations_service.py",
    },
    "ai_billing": {
        "api/v1/endpoints/ai.py",
        "api/v1/endpoints/chat.py",
        "services/ai_service.py",
        "services/roomi_service.py",
    },
    "customer_portal": {
        "api/v1/endpoints/portal.py",
        "api/v1/endpoints/hosted_checkout.py",
        "services/customer_portal_service.py",
        "services/checkout_service.py",
    },
    "automation": {
        "api/v1/endpoints/customization.py",
        "services/customization_service.py",
    },
}
