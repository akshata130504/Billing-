"""Projects API endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import (
    CurrentContext,
    get_db,
    require_admin,
    require_finance,
    require_viewer,
)
from backend.app.schemas.projects import (
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    ProjectSummaryKPIs,
    ProjectUpdate,
)
from backend.app.services import project_service

router = APIRouter()


@router.get("", response_model=List[ProjectRead], summary="List projects")
def list_projects(
    search: Optional[str] = Query(None, description="Search by name, customer, or description"),
    status: Optional[str] = Query(None, description="Filter by project status"),
    customer_id: Optional[str] = Query(None, description="Filter by customer ID"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return project_service.list_projects(
        db,
        ctx.organization_id,
        search=search,
        status=status,
        customer_id=customer_id,
    )


@router.get("/summary", response_model=ProjectSummaryKPIs, summary="Get project summary KPIs")
def get_project_summary(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return project_service.get_summary_kpis(db, ctx.organization_id)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED, summary="Create a project")
def create_project(
    data: ProjectCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    return project_service.create_project(db, ctx.organization_id, data)


@router.get("/{project_id}", response_model=ProjectDetail, summary="Get project details")
def get_project(
    project_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return project_service.get_project_detail(db, ctx.organization_id, project_id)


@router.patch("/{project_id}", response_model=ProjectRead, summary="Update a project")
def update_project(
    project_id: str,
    data: ProjectUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    return project_service.update_project(db, ctx.organization_id, project_id, data)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a project")
def delete_project(
    project_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project_service.delete_project(db, ctx.organization_id, project_id)
