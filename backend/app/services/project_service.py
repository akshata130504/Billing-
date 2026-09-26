"""Project domain service: CRUD, tenant isolation, and financial aggregates."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import EntityNotFoundError, ValidationAppError
from backend.app.models.customers import Customer
from backend.app.models.expenses import Expense, ExpenseStatus
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.payments import Payment, PaymentAllocation
from backend.app.models.projects import BillingMethod, Project, ProjectInvoice, ProjectStatus
from backend.app.models.timesheets import TimeEntry, TimeEntryStatus
from backend.app.services.money import D
from backend.app.schemas.projects import (
    ProjectCreate,
    ProjectDetail,
    ProjectInvoiceCreate,
    ProjectRead,
    ProjectSummaryKPIs,
    ProjectUpdate,
)


def _direct_invoice_total(db: Session, organization_id: str, project_id: str) -> Decimal:
    """Pre-tax value of non-void invoices raised directly against the project."""
    return db.scalar(
        select(func.coalesce(func.sum(Invoice.subtotal - Invoice.discount_amount), Decimal("0.00")))
        .select_from(ProjectInvoice)
        .join(Invoice, Invoice.id == ProjectInvoice.invoice_id)
        .where(
            ProjectInvoice.organization_id == organization_id,
            ProjectInvoice.project_id == project_id,
            Invoice.status != InvoiceStatus.VOID,
        )
    ) or Decimal("0.00")


def _compute_project_financials(db: Session, organization_id: str, project_id: str) -> tuple[Decimal, Decimal]:
    """Computes total billed and total expenses for a project.

    billed = billed time entries + invoiced expenses + direct project invoices
    (each source counted once; timesheet/expense invoices can mix projects, so their
    project share is taken from the entries, not the invoice total).
    """
    exp_total = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), Decimal("0.00"))).where(
            Expense.organization_id == organization_id,
            Expense.project_id == project_id,
        )
    ) or Decimal("0.00")

    billed_timesheets = db.scalar(
        select(func.coalesce(func.sum(TimeEntry.billable_amount), Decimal("0.00"))).where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.project_id == project_id,
            TimeEntry.status == TimeEntryStatus.BILLED,
        )
    ) or Decimal("0.00")

    billed_expenses = db.scalar(
        select(func.coalesce(func.sum(func.coalesce(Expense.billable_amount, Expense.amount)), Decimal("0.00"))).where(
            Expense.organization_id == organization_id,
            Expense.project_id == project_id,
            Expense.invoice_id.is_not(None),
            Expense.status == ExpenseStatus.INVOICED,
        )
    ) or Decimal("0.00")

    billed = D(billed_timesheets) + D(billed_expenses) + D(_direct_invoice_total(db, organization_id, project_id))
    return billed, exp_total


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


def _invoice_status_for_ui(invoice: Invoice) -> str:
    status = invoice.status.value if hasattr(invoice.status, "value") else str(invoice.status)
    if status in ("paid", "draft", "overdue"):
        return status
    return "pending"


def _project_invoice_ids(db: Session, organization_id: str, project_id: str) -> List[str]:
    """Invoices tied to the project: raised directly, or billing its hours or expenses."""
    direct = db.scalars(
        select(ProjectInvoice.invoice_id).where(
            ProjectInvoice.organization_id == organization_id, ProjectInvoice.project_id == project_id
        )
    ).all()
    from_time = db.scalars(
        select(TimeEntry.invoice_id).where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.project_id == project_id,
            TimeEntry.invoice_id.is_not(None),
        )
    ).all()
    from_expenses = db.scalars(
        select(Expense.invoice_id).where(
            Expense.organization_id == organization_id,
            Expense.project_id == project_id,
            Expense.invoice_id.is_not(None),
        )
    ).all()
    seen: Dict[str, None] = {}
    for inv_id in [*direct, *from_time, *from_expenses]:
        if inv_id:
            seen[inv_id] = None
    return list(seen)


def _invoices_payments_transactions(
    db: Session, organization_id: str, project_id: str
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    invoice_ids = _project_invoice_ids(db, organization_id, project_id)
    if not invoice_ids:
        return [], [], []
    invoices = list(
        db.scalars(
            select(Invoice)
            .where(Invoice.organization_id == organization_id, Invoice.id.in_(invoice_ids))
            .order_by(desc(Invoice.issue_date), desc(Invoice.created_at))
        ).all()
    )
    invoice_rows = [
        {
            "id": inv.id,
            "projectId": project_id,
            "invoiceNumber": inv.invoice_number,
            "date": str(inv.issue_date),
            "dueDate": str(inv.due_date),
            "amount": float(inv.total or 0),
            "amountDue": float(inv.amount_due or 0),
            "currency": inv.currency,
            "status": _invoice_status_for_ui(inv),
            "rawStatus": inv.status.value if hasattr(inv.status, "value") else str(inv.status),
        }
        for inv in invoices
        if inv.status != InvoiceStatus.VOID
    ]
    numbers = {inv.id: inv.invoice_number for inv in invoices}
    allocations = db.execute(
        select(PaymentAllocation, Payment)
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(Payment.organization_id == organization_id, PaymentAllocation.invoice_id.in_(invoice_ids))
        .order_by(desc(Payment.paid_at), desc(Payment.created_at))
    ).all()
    payment_rows: List[Dict[str, Any]] = []
    for alloc, pay in allocations:
        pay_status = pay.status.value if hasattr(pay.status, "value") else str(pay.status)
        paid_on = pay.paid_at or pay.created_at
        payment_rows.append(
            {
                "id": alloc.id,
                "paymentId": pay.id,
                "projectId": project_id,
                "paymentDate": paid_on.date().isoformat() if paid_on else "",
                "reference": pay.reference or pay.payment_number,
                "invoiceNumber": numbers.get(alloc.invoice_id, ""),
                "method": pay.method.value if hasattr(pay.method, "value") else str(pay.method),
                "amount": float(alloc.amount or 0),
                "status": "completed" if pay_status in ("succeeded", "partially_refunded", "refunded") else "pending",
            }
        )
    transactions: List[Dict[str, Any]] = [
        {
            "id": f"inv-{row['id']}",
            "projectId": project_id,
            "type": "Invoice",
            "reference": row["invoiceNumber"],
            "date": row["date"],
            "amount": row["amount"],
            "status": row["rawStatus"],
        }
        for row in invoice_rows
    ] + [
        {
            "id": f"pay-{row['id']}",
            "projectId": project_id,
            "type": "Payment",
            "reference": row["reference"],
            "date": row["paymentDate"],
            "amount": row["amount"],
            "status": row["status"],
        }
        for row in payment_rows
    ]
    transactions.sort(key=lambda t: t["date"] or "", reverse=True)
    return invoice_rows, payment_rows, transactions


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

    invoices, payments, transactions = _invoices_payments_transactions(db, organization_id, project_id)
    return ProjectDetail(
        **base_read.model_dump(),
        timesheets=timesheet_list,
        expense_list=expense_list,
        invoices=invoices,
        payments=payments,
        transactions=transactions,
    )


def _customer_in_org(db: Session, organization_id: str, customer_id: str) -> Customer:
    customer = db.scalars(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == organization_id)
    ).first()
    if customer is None:
        raise EntityNotFoundError("Customer", customer_id)
    return customer


def create_project(db: Session, organization_id: str, data: ProjectCreate) -> ProjectRead:
    cust_name = data.customer_name
    if data.customer_id:
        # The linked customer is who the project bills; it must exist in this org.
        cust_name = _customer_in_org(db, organization_id, data.customer_id).display_name

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
        if cust_id:
            customer = _customer_in_org(db, organization_id, cust_id)
            project.customer_id = customer.id
            project.customer_name = customer.display_name
        else:
            project.customer_id = None
            project.customer_name = payload.get("customer_name")

    elif "customer_name" in payload and not project.customer_id:
        # Free-text name is only kept for legacy projects without a linked customer.
        project.customer_name = payload["customer_name"]

    for field, val in payload.items():
        if field not in ("customer_id", "customer_name"):
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


def create_project_invoice(db: Session, ctx, project_id: str, data: ProjectInvoiceCreate) -> Dict[str, Any]:
    """Raise a real draft invoice for the project's customer and link it to the project."""
    from backend.app.services import audit, invoice_service
    from backend.app.services.money import LineInput
    from backend.app.services.timesheet_service import default_tax_rate_pct

    organization_id = ctx.organization_id
    project = get_project(db, organization_id, project_id)
    if project.billing_method == BillingMethod.NON_BILLABLE:
        raise ValidationAppError("This project is non-billable.", {"fields": {"billing_method": "non_billable"}})
    if not project.customer_id:
        raise ValidationAppError(
            "Link the project to a customer before invoicing it.",
            {"fields": {"customer_id": "required to invoice"}},
        )
    customer = _customer_in_org(db, organization_id, project.customer_id)
    tax_rate = data.tax_rate_pct if data.tax_rate_pct is not None else default_tax_rate_pct(ctx.organization)
    description = (data.description or f"Project billing: {project.name}").strip()[:500]
    try:
        invoice = invoice_service.create_invoice_record(
            db,
            organization_id=organization_id,
            customer=customer,
            lines=[
                LineInput(
                    description=description,
                    quantity=Decimal("1"),
                    unit_price=D(data.amount),
                    tax_rate_pct=D(tax_rate),
                )
            ],
            issue_date=data.issue_date,
            due_date=data.due_date,
            notes=data.notes,
            created_by_id=ctx.user.id,
        )
        db.add(ProjectInvoice(organization_id=organization_id, project_id=project.id, invoice_id=invoice.id))
        db.flush()
        audit.record(
            db,
            action="INVOICE_CREATED",
            entity_type="invoice",
            entity_id=invoice.id,
            entity_label=invoice.invoice_number,
            ctx=ctx,
            after={**invoice_service.snapshot(invoice), "project_id": project.id},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(invoice)
    return {
        "id": invoice.id,
        "projectId": project.id,
        "invoiceNumber": invoice.invoice_number,
        "date": str(invoice.issue_date),
        "dueDate": str(invoice.due_date),
        "amount": float(invoice.total or 0),
        "amountDue": float(invoice.amount_due or 0),
        "currency": invoice.currency,
        "status": _invoice_status_for_ui(invoice),
        "rawStatus": invoice.status.value if hasattr(invoice.status, "value") else str(invoice.status),
    }
