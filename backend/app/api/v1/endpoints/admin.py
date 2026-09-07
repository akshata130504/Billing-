"""/admin — operational endpoints for owners."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_owner
from backend.app.schemas.dashboard import JobsRunResult
from backend.app.services.scheduler import run_billing_jobs

router = APIRouter()


@router.post("/jobs/run", response_model=JobsRunResult, summary="Run the billing jobs (renewals, overdue, dunning) now")
def run_jobs(
    ctx: CurrentContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return run_billing_jobs(db)
