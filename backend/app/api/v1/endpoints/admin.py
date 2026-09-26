"""/admin — operational endpoints for owners.

POST /admin/jobs/run was removed: it ran the billing jobs (renewals, dunning charges,
trial conversions) for EVERY tenant on behalf of any single organization owner and
ignored SCHEDULER_ENABLED. Billing jobs run only in the dedicated scheduler process
(docker-compose.prod.yml service `scheduler`). The router stays mounted (see
api_router.py) so future tenant-scoped admin endpoints have a home.
"""
from fastapi import APIRouter

router = APIRouter()
