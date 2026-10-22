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
}
