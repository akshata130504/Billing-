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
        "services/pricing_engine.py",
        "services/catalog_cpq_service.py",
        "api/v1/endpoints/pricing.py",
        "api/v1/endpoints/catalog.py",
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
    # quote_service is in the lazy service cycle; its old path is a forwarding alias, so the
    # cycle's imports keep resolving. Offerings and price books (/catalog) are in products.
    "quotes": {
        "api/v1/endpoints/quotes.py",
        "api/v1/endpoints/cpq.py",
        "services/quote_service.py",
        "services/quote_pdf.py",
        "api/v1/endpoints/public_quotes.py",
    },
    # invoice_service is in the lazy service cycle (timesheets, subscriptions, payments import it);
    # its old path is a forwarding alias, so those imports keep resolving.
    "invoices": {
        "api/v1/endpoints/invoices.py",
        "api/v1/endpoints/credit_notes.py",
        "services/invoice_service.py",
        "services/credit_service.py",
        "services/invoice_pdf.py",
        "api/v1/endpoints/public_invoices.py",
    },
    # Subscriptions & Usage: subscriptions, changes/proration, meters and trials. /plans is in products.
    "subscriptions": {
        "api/v1/endpoints/subscriptions.py",
        "services/subscription_service.py",
        "services/subscription_change_service.py",
        "services/meter_service.py",
        "services/trial_service.py",
        "services/proration_calculator.py",
        "services/offering_subscription_service.py",
        "api/v1/endpoints/subscription_changes.py",
        "api/v1/endpoints/meters.py",
        "api/v1/endpoints/trials.py",
    },
    # Collections and dunning (modules.json lists dunning separately; its code lives here).
    "collections": {
        "api/v1/endpoints/collections.py",
        "api/v1/endpoints/dunning.py",
        "services/collection_service.py",
        "services/dunning_service.py",
    },
    # payment_service is in the lazy 21-service cycle; its imports stay where they are.
    "payments": {
        "api/v1/endpoints/payments.py",
        "services/payment_service.py",
        "services/payment_method_service.py",
        "services/razorpay_gateway.py",
        "api/v1/endpoints/payment_methods.py",
        "api/v1/endpoints/webhooks.py",
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
        "services/outbox_processor.py",
    },
    "reports": {
        "api/v1/endpoints/reports.py",
        "services/reports_service.py",
    },
    "customer_lifecycle": {
        "api/v1/endpoints/lifecycle.py",
        "services/lifecycle_service.py",
    },
}
