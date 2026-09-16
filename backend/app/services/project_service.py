"""Project domain service: CRUD, tenant isolation, and financial aggregates."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import EntityNotFoundError, ValidationAppError
from backend.app.models.customers import Customer
from backend.app.models.expenses import Expense
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.projects import Project, ProjectStatus
from backend.app.models.timesheets import TimeEntry, TimeEntryStatus
from backend.app.schemas.projects import (
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    ProjectSummaryKPIs,
    ProjectUpdate,
)


def _compute_project_financials(db: Session, organization_id: str, project_id: str) -> tuple[Decimal, Decimal]:
    """Computes total billed and total expenses for a project."""
    # Expenses total
    exp_total = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), Decimal("0.00"))).where(
            Expense.organization_id == organization_id,
            Expense.project_id == project_id,
        )
    ) or Decimal("0.00")

    # Billed total: sum of billable time entries billed or invoiced
    billed_timesheets = db.scalar(
        select(func.coalesce(func.sum(TimeEntry.billable_amount), Decimal("0.00"))).where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.project_id == project_id,
            TimeEntry.status == TimeEntryStatus.BILLED,
        )
    ) or Decimal("0.00")

    return billed_timesheets, exp_total


def serialize_project(db: Session, project: Project) -> ProjectRead:
    billed, expenses = _compute_project_financials(db, project.organization_id, project.id)
    cust_name = project.customer_name or (project.customer.display_name if project.customer else None)
    return ProjectRead(
        id=project.id,
        organization_id=project.organization_id,
        name=project.name,
        customer_id=project.customer_id,
        customer_name=cust_name,
        customer=cust_name,
        description=project.description,
        status=project.status,
        start_date=project.start_date,
        end_date=project.end_date,
        billing_method=project.billing_method,
        budget=project.budget or Decimal("0.00"),
        billed=billed,
        expenses=expenses,
        project_manager=project.project_manager,
        notes=project.notes,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def list_projects(
    db: Session,
    organization_id: str,
    search: Optional[str] = None,
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> List[ProjectRead]:
    query = select(Project).where(Project.organization_id == organization_id)

    if customer_id:
        query = query.where(Project.customer_id == customer_id)

    if status and status != "all":
        try:
            p_status = ProjectStatus(status)
            query = query.where(Project.status == p_status)
        except ValueError:
            pass

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Project.name.ilike(term),
                Project.customer_name.ilike(term),
                Project.description.ilike(term),
            )
        )

    query = query.order_by(desc(Project.created_at))
    projects = list(db.scalars(query).all())
    return [serialize_project(db, p) for p in projects]


def get_project(db: Session, organization_id: str, project_id: str) -> Project:
    project = db.scalars(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == organization_id,
        )
    ).first()
    if not project:
        raise EntityNotFoundError("Project", project_id)
    return project


def get_project_detail(db: Session, organization_id: str, project_id: str) -> ProjectDetail:
    project = get_project(db, organization_id, project_id)
    base_read = serialize_project(db, project)

    # Fetch linked timesheets
    time_entries = list(
        db.scalars(
            select(TimeEntry)
            .where(
                TimeEntry.organization_id == organization_id,
                TimeEntry.project_id == project_id,
            )
            .order_by(desc(TimeEntry.date))
        ).all()
    )
    timesheet_list = [
        {
            "id": te.id,
            "projectId": te.project_id,
            "employee": te.user.full_name if te.user else "Team Member",
            "date": str(te.date),
            "description": te.description,
            "hours": float(te.duration_hours),
            "billable": te.billable,
            "hourlyRate": float(te.billing_rate),
            "amount": float(te.billable_amount),
        }
        for te in time_entries
    ]

    # Fetch linked expenses
    expenses = list(
        db.scalars(
            select(Expense)
            .where(
                Expense.organization_id == organization_id,
                Expense.project_id == project_id,
            )
            .order_by(desc(Expense.date))
        ).all()
    )
    expense_list = [
        {
            "id": e.id,
            "projectId": e.project_id,
            "date": str(e.date),
            "title": e.name,
            "category": e.category,
            "amount": float(e.amount),
            "billable": e.billable,
            "status": e.status.value,
        }
        for e in expenses
    ]

    return ProjectDetail(
        **base_read.model_dump(),
        timesheets=timesheet_list,
        expense_list=expense_list,
        invoices=[],
        payments=[],
        transactions=[],
    )


def create_project(db: Session, organization_id: str, data: ProjectCreate) -> ProjectRead:
    cust_name = data.customer_name
    if data.customer_id and not cust_name:
        customer = db.scalars(
            select(Customer).where(
                Customer.id == data.customer_id,
                Customer.organization_id == organization_id,
            )
        ).first()
        if customer:
            cust_name = customer.display_name

    project = Project(
        organization_id=organization_id,
        name=data.name.strip(),
        customer_id=data.customer_id,
        customer_name=cust_name,
        description=data.description,
        status=data.status,
        start_date=data.start_date,
        end_date=data.end_date,
        billing_method=data.billing_method,
        budget=data.budget,
        project_manager=data.project_manager,
        notes=data.notes,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return serialize_project(db, project)


def update_project(db: Session, organization_id: str, project_id: str, data: ProjectUpdate) -> ProjectRead:
    project = get_project(db, organization_id, project_id)

    payload = data.model_dump(exclude_unset=True)
    if "customer_id" in payload:
        cust_id = payload["customer_id"]
        project.customer_id = cust_id
        if cust_id:
            customer = db.scalars(
                select(Customer).where(
                    Customer.id == cust_id,
                    Customer.organization_id == organization_id,
                )
            ).first()
            if customer:
                project.customer_name = customer.display_name
        else:
            project.customer_name = payload.get("customer_name")

    for field, val in payload.items():
        if field != "customer_id":
            setattr(project, field, val)

    db.commit()
    db.refresh(project)
    return serialize_project(db, project)


def delete_project(db: Session, organization_id: str, project_id: str) -> None:
    project = get_project(db, organization_id, project_id)
    db.delete(project)
    db.commit()


def get_summary_kpis(db: Session, organization_id: str) -> ProjectSummaryKPIs:
    total_projects = db.scalar(
        select(func.count(Project.id)).where(Project.organization_id == organization_id)
    ) or 0

    active_projects = db.scalar(
        select(func.count(Project.id)).where(
            Project.organization_id == organization_id,
            Project.status == ProjectStatus.ACTIVE,
        )
    ) or 0

    total_budget = db.scalar(
        select(func.coalesce(func.sum(Project.budget), Decimal("0.00"))).where(
            Project.organization_id == organization_id
        )
    ) or Decimal("0.00")

    total_expenses = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), Decimal("0.00"))).where(
            Expense.organization_id == organization_id
        )
    ) or Decimal("0.00")

    total_billed = db.scalar(
        select(func.coalesce(func.sum(TimeEntry.billable_amount), Decimal("0.00"))).where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.status == TimeEntryStatus.BILLED,
        )
    ) or Decimal("0.00")

    return ProjectSummaryKPIs(
        total_projects=total_projects,
        active_projects=active_projects,
        total_budget=total_budget,
        total_billed=total_billed,
        total_expenses=total_expenses,
    )
