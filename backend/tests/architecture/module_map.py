"""Which backend files belong to which product module (modularization).

Module keys follow backend/app/core/modules.json. Only the pilot module is mapped so far;
every other file stays unassigned until its own phase. Paths are relative to backend/app.
"""

MODULES: dict[str, set[str]] = {
    "projects": {
        "api/v1/endpoints/projects.py",
        "services/project_service.py",
        "schemas/projects.py",
        "models/projects.py",
    },
}
