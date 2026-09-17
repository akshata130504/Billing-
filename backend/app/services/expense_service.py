"""Expense domain service: CRUD, batch import, recurring profiles, and KPI summaries."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import EntityNotFoundError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.models.customers import Customer
from backend.app.models.expenses import (
    Expense,
    ExpenseStatus,
    RecurringExpense,
    RecurringExpenseFrequency,
    RecurringExpenseStatus,
)
from backend.app.models.projects import Project
from backend.app.schemas.expenses import (
    ExpenseCreate,
    ExpenseRead,
    ExpenseSummaryKPIs,
    ExpenseUpdate,
    RecurringExpenseCreate,
    RecurringExpenseRead,
    RecurringExpenseSummaryKPIs,
    RecurringExpenseUpdate,
)


def serialize_expense(expense: Expense) -> ExpenseRead:
    cust = expense.customer_name or (expense.customer.display_name if expense.customer else None)
    proj = expense.project_name or (expense.project.name if expense.project else None)
    return ExpenseRead(
        id=expense.id,
        organization_id=expense.organization_id,
        name=expense.name,
        description=expense.description,
        date=expense.date,
        category=expense.category,
        amount=expense.amount,
        currency=expense.currency,
        billable=expense.billable,
        customer_id=expense.customer_id,
        customer_name=cust,
        customer=cust,
        project_id=expense.project_id,
        project_name=proj,
        project=proj,
        billable_amount=expense.billable_amount,
        tax_rate=expense.tax_rate,
        invoice_treatment=expense.invoice_treatment,
        invoice_id=expense.invoice_id,
        payment_method=expense.payment_method,
        paid_by=expense.paid_by,
        status=expense.status,
        receipt_file_name=expense.receipt_file_name,
        receipt_file_size=expense.receipt_file_size,
        receipt_file_type=expense.receipt_file_type,
        notes=expense.notes,
        created_at=expense.created_at,
        updated_at=expense.updated_at,
    )


def serialize_recurring(rec: RecurringExpense) -> RecurringExpenseRead:
    cust = rec.customer_name or (rec.customer.display_name if rec.customer else None)
    proj = rec.project_name or (rec.project.name if rec.project else None)
    return RecurringExpenseRead(
        id=rec.id,
        organization_id=rec.organization_id,
        name=rec.name,
        category=rec.category,
        description=rec.description,
        amount=rec.amount,
        currency=rec.currency,
        frequency=rec.frequency,
        start_date=rec.start_date,
        end_date=rec.end_date,
        never_ends=rec.never_ends,
        next_run=rec.next_run,
        last_run=rec.last_run,
        billable=rec.billable,
        customer_id=rec.customer_id,
        customer_name=cust,
        customer=cust,
        project_id=rec.project_id,
        project_name=proj,
        project=proj,
        billable_amount=rec.billable_amount,
        invoice_treatment=rec.invoice_treatment,
        payment_method=rec.payment_method,
        paid_by=rec.paid_by,
        status=rec.status,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def list_expenses(
    db: Session,
    organization_id: str,
    search: Optional[str] = None,
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
    project_id: Optional[str] = None,
    category: Optional[str] = None,
    billable: Optional[bool] = None,
    sort_by: Optional[str] = "newest",
) -> List[ExpenseRead]:
    query = select(Expense).where(Expense.organization_id == organization_id)

    if customer_id:
        query = query.where(Expense.customer_id == customer_id)
    if project_id:
        query = query.where(Expense.project_id == project_id)
    if category and category != "all":
        query = query.where(Expense.category == category)
    if billable is not None:
        query = query.where(Expense.billable.is_(billable))
    if status and status != "all":
        try:
            e_status = ExpenseStatus(status)
            query = query.where(Expense.status == e_status)
        except ValueError:
            pass

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Expense.name.ilike(term),
                Expense.customer_name.ilike(term),
                Expense.project_name.ilike(term),
                Expense.category.ilike(term),
            )
        )

    if sort_by == "oldest":
        query = query.order_by(Expense.date.asc(), Expense.created_at.asc())
    elif sort_by == "amount_high":
        query = query.order_by(desc(Expense.amount))
    elif sort_by == "amount_low":
        query = query.order_by(Expense.amount.asc())
    else:  # newest
        query = query.order_by(desc(Expense.date), desc(Expense.created_at))

    expenses = list(db.scalars(query).all())
    return [serialize_expense(e) for e in expenses]


def get_expense(db: Session, organization_id: str, expense_id: str) -> Expense:
    expense = db.scalars(
        select(Expense).where(
            Expense.id == expense_id,
            Expense.organization_id == organization_id,
        )
    ).first()
    if not expense:
        raise EntityNotFoundError("Expense", expense_id)
    return expense


def create_expense(db: Session, organization_id: str, data: ExpenseCreate) -> ExpenseRead:
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

    proj_name = data.project_name
    if data.project_id and not proj_name:
        proj = db.scalars(
            select(Project).where(
                Project.id == data.project_id,
                Project.organization_id == organization_id,
            )
        ).first()
        if proj:
            proj_name = proj.name

    expense = Expense(
        organization_id=organization_id,
        name=data.name.strip(),
        description=data.description,
        date=data.date,
        category=data.category,
        amount=data.amount,
        currency=data.currency,
        billable=data.billable,
        customer_id=data.customer_id,
        customer_name=cust_name,
        project_id=data.project_id,
        project_name=proj_name,
        billable_amount=data.billable_amount if data.billable else None,
        tax_rate=data.tax_rate,
        invoice_treatment=data.invoice_treatment,
        invoice_id=data.invoice_id,
        payment_method=data.payment_method,
        paid_by=data.paid_by,
        status=data.status,
        receipt_file_name=data.receipt_file_name,
        receipt_file_size=data.receipt_file_size,
        receipt_file_type=data.receipt_file_type,
        notes=data.notes,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return serialize_expense(expense)


def batch_import_expenses(db: Session, organization_id: str, items: List[ExpenseCreate]) -> int:
    count = 0
    for item in items:
        create_expense(db, organization_id, item)
        count += 1
    return count


def update_expense(db: Session, organization_id: str, expense_id: str, data: ExpenseUpdate) -> ExpenseRead:
    expense = get_expense(db, organization_id, expense_id)

    payload = data.model_dump(exclude_unset=True)
    if "customer_id" in payload:
        cust_id = payload["customer_id"]
        expense.customer_id = cust_id
        if cust_id:
            cust = db.scalars(
                select(Customer).where(Customer.id == cust_id, Customer.organization_id == organization_id)
            ).first()
            if cust:
                expense.customer_name = cust.display_name
        else:
            expense.customer_name = payload.get("customer_name")

    if "project_id" in payload:
        proj_id = payload["project_id"]
        expense.project_id = proj_id
        if proj_id:
            proj = db.scalars(
                select(Project).where(Project.id == proj_id, Project.organization_id == organization_id)
            ).first()
            if proj:
                expense.project_name = proj.name
        else:
            expense.project_name = payload.get("project_name")

    for field, val in payload.items():
        if field not in ("customer_id", "project_id"):
            setattr(expense, field, val)

    db.commit()
    db.refresh(expense)
    return serialize_expense(expense)


def delete_expense(db: Session, organization_id: str, expense_id: str) -> None:
    expense = get_expense(db, organization_id, expense_id)
    db.delete(expense)
    db.commit()


def add_to_invoice(db: Session, organization_id: str, expense_id: str) -> ExpenseRead:
    expense = get_expense(db, organization_id, expense_id)
    expense.status = ExpenseStatus.INVOICED
    expense.billable = True
    if not expense.billable_amount:
        expense.billable_amount = expense.amount
    db.commit()
    db.refresh(expense)
    return serialize_expense(expense)


def get_summary_kpis(db: Session, organization_id: str) -> ExpenseSummaryKPIs:
    total = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), Decimal("0.00"))).where(
            Expense.organization_id == organization_id
        )
    ) or Decimal("0.00")

    billable = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), Decimal("0.00"))).where(
            Expense.organization_id == organization_id,
            Expense.billable.is_(True),
        )
    ) or Decimal("0.00")

    non_billable = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), Decimal("0.00"))).where(
            Expense.organization_id == organization_id,
            Expense.billable.is_(False),
        )
    ) or Decimal("0.00")

    pending = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), Decimal("0.00"))).where(
            Expense.organization_id == organization_id,
            Expense.status.in_([ExpenseStatus.RECORDED, ExpenseStatus.BILLABLE]),
        )
    ) or Decimal("0.00")

    return ExpenseSummaryKPIs(
        total=total,
        billable=billable,
        non_billable=non_billable,
        pending=pending,
    )


# --- Recurring Expenses ---


def list_recurring_expenses(db: Session, organization_id: str) -> List[RecurringExpenseRead]:
    recs = list(
        db.scalars(
            select(RecurringExpense)
            .where(RecurringExpense.organization_id == organization_id)
            .order_by(desc(RecurringExpense.created_at))
        ).all()
    )
    return [serialize_recurring(r) for r in recs]


def get_recurring_expense(db: Session, organization_id: str, rec_id: str) -> RecurringExpense:
    rec = db.scalars(
        select(RecurringExpense).where(
            RecurringExpense.id == rec_id,
            RecurringExpense.organization_id == organization_id,
        )
    ).first()
    if not rec:
        raise EntityNotFoundError("RecurringExpense", rec_id)
    return rec


def create_recurring_expense(
    db: Session, organization_id: str, data: RecurringExpenseCreate
) -> RecurringExpenseRead:
    cust_name = data.customer_name
    if data.customer_id and not cust_name:
        customer = db.scalars(
            select(Customer).where(Customer.id == data.customer_id, Customer.organization_id == organization_id)
        ).first()
        if customer:
            cust_name = customer.display_name

    proj_name = data.project_name
    if data.project_id and not proj_name:
        proj = db.scalars(
            select(Project).where(Project.id == data.project_id, Project.organization_id == organization_id)
        ).first()
        if proj:
            proj_name = proj.name

    rec = RecurringExpense(
        organization_id=organization_id,
        name=data.name.strip(),
        category=data.category,
        description=data.description,
        amount=data.amount,
        currency=data.currency,
        frequency=data.frequency,
        start_date=data.start_date,
        end_date=data.end_date,
        never_ends=data.never_ends,
        next_run=data.next_run or data.start_date,
        last_run=data.last_run,
        billable=data.billable,
        customer_id=data.customer_id,
        customer_name=cust_name,
        project_id=data.project_id,
        project_name=proj_name,
        billable_amount=data.billable_amount,
        invoice_treatment=data.invoice_treatment,
        payment_method=data.payment_method,
        paid_by=data.paid_by,
        status=data.status,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return serialize_recurring(rec)


def update_recurring_expense(
    db: Session, organization_id: str, rec_id: str, data: RecurringExpenseUpdate
) -> RecurringExpenseRead:
    rec = get_recurring_expense(db, organization_id, rec_id)
    payload = data.model_dump(exclude_unset=True)

    for field, val in payload.items():
        setattr(rec, field, val)

    db.commit()
    db.refresh(rec)
    return serialize_recurring(rec)


def delete_recurring_expense(db: Session, organization_id: str, rec_id: str) -> None:
    rec = get_recurring_expense(db, organization_id, rec_id)
    db.delete(rec)
    db.commit()


def toggle_recurring_status(db: Session, organization_id: str, rec_id: str) -> RecurringExpenseRead:
    rec = get_recurring_expense(db, organization_id, rec_id)
    if rec.status == RecurringExpenseStatus.ACTIVE:
        rec.status = RecurringExpenseStatus.PAUSED
    else:
        rec.status = RecurringExpenseStatus.ACTIVE
    db.commit()
    db.refresh(rec)
    return serialize_recurring(rec)


def get_recurring_summary_kpis(db: Session, organization_id: str) -> RecurringExpenseSummaryKPIs:
    active_profiles = db.scalar(
        select(func.count(RecurringExpense.id)).where(
            RecurringExpense.organization_id == organization_id,
            RecurringExpense.status == RecurringExpenseStatus.ACTIVE,
        )
    ) or 0

    monthly_recurring = db.scalar(
        select(func.coalesce(func.sum(RecurringExpense.amount), Decimal("0.00"))).where(
            RecurringExpense.organization_id == organization_id,
            RecurringExpense.status == RecurringExpenseStatus.ACTIVE,
        )
    ) or Decimal("0.00")

    billable_recurring = db.scalar(
        select(func.coalesce(func.sum(RecurringExpense.amount), Decimal("0.00"))).where(
            RecurringExpense.organization_id == organization_id,
            RecurringExpense.status == RecurringExpenseStatus.ACTIVE,
            RecurringExpense.billable.is_(True),
        )
    ) or Decimal("0.00")

    next_date = db.scalar(
        select(RecurringExpense.next_run)
        .where(
            RecurringExpense.organization_id == organization_id,
            RecurringExpense.status == RecurringExpenseStatus.ACTIVE,
            RecurringExpense.next_run.is_not(None),
        )
        .order_by(RecurringExpense.next_run.asc())
        .limit(1)
    )

    return RecurringExpenseSummaryKPIs(
        active_profiles=active_profiles,
        monthly_recurring=monthly_recurring,
        billable_recurring=billable_recurring,
        next_run=str(next_date) if next_date else None,
    )


def calculate_next_run(
    current_run: date,
    frequency: RecurringExpenseFrequency,
    anchor_day: Optional[int] = None,
) -> date:
    """Advance a recurring expense run date by one recurrence period."""
    from backend.app.services.subscription_service import add_months

    if frequency == RecurringExpenseFrequency.WEEKLY:
        return current_run + timedelta(days=7)
    elif frequency == RecurringExpenseFrequency.MONTHLY:
        return add_months(current_run, 1, anchor_day=anchor_day)
    elif frequency == RecurringExpenseFrequency.QUARTERLY:
        return add_months(current_run, 3, anchor_day=anchor_day)
    elif frequency == RecurringExpenseFrequency.YEARLY:
        return add_months(current_run, 12, anchor_day=anchor_day)
    return add_months(current_run, 1, anchor_day=anchor_day)


def execute_recurring_expense(
    db: Session,
    rec: RecurringExpense,
    *,
    today: Optional[date] = None,
) -> Optional[Expense]:
    """Execute a single due recurring expense.

    Creates exactly one Expense record for the due occurrence, updates last_run and next_run,
    and handles end_date / status. Fully idempotent: if already executed for this occurrence date,
    does not create duplicate Expense records.
    """
    today = today or date.today()
    if rec.status != RecurringExpenseStatus.ACTIVE:
        return None
    if not rec.next_run or rec.next_run > today:
        return None

    due_date = rec.next_run
    anchor_day = rec.start_date.day if rec.start_date else due_date.day

    # Check for existing expense for this recurring profile on this due occurrence date (idempotency)
    marker = f"[recurring_expense_id:{rec.id}]"
    existing = db.scalars(
        select(Expense).where(
            Expense.organization_id == rec.organization_id,
            Expense.date == due_date,
            Expense.notes.contains(marker),
        )
    ).first()

    next_date = calculate_next_run(due_date, rec.frequency, anchor_day=anchor_day)

    if existing or (rec.last_run and rec.last_run >= due_date):
        # Already executed for this occurrence; advance pointers safely
        rec.last_run = due_date
        if not rec.never_ends and rec.end_date and next_date > rec.end_date:
            rec.status = RecurringExpenseStatus.ENDED
            rec.next_run = None
        else:
            rec.next_run = next_date
        return None

    notes_content = f"{rec.description}\n{marker}".strip() if rec.description else marker

    expense = Expense(
        organization_id=rec.organization_id,
        name=rec.name,
        description=rec.description,
        date=due_date,
        category=rec.category,
        amount=rec.amount,
        currency=rec.currency,
        billable=rec.billable,
        customer_id=rec.customer_id,
        customer_name=rec.customer_name,
        project_id=rec.project_id,
        project_name=rec.project_name,
        billable_amount=rec.billable_amount if rec.billable else None,
        tax_rate=getattr(rec, "tax_rate", None),
        invoice_treatment=rec.invoice_treatment,
        payment_method=rec.payment_method or "Cash",
        paid_by=rec.paid_by or "Self",
        status=ExpenseStatus.RECORDED,
        notes=notes_content,
    )
    db.add(expense)

    rec.last_run = due_date
    if not rec.never_ends and rec.end_date and next_date > rec.end_date:
        rec.status = RecurringExpenseStatus.ENDED
        rec.next_run = None
    else:
        rec.next_run = next_date

    return expense


def process_due_recurring_expenses(db: Session, *, today: Optional[date] = None) -> int:
    """Process all active recurring expenses due on or before `today`."""
    today = today or date.today()
    due_recs = list(
        db.scalars(
            select(RecurringExpense).where(
                RecurringExpense.status == RecurringExpenseStatus.ACTIVE,
                RecurringExpense.next_run.is_not(None),
                RecurringExpense.next_run <= today,
            )
        ).all()
    )

    processed = 0
    for rec in due_recs:
        try:
            exp = execute_recurring_expense(db, rec, today=today)
            db.commit()
            if exp is not None:
                processed += 1
        except Exception:
            logger.exception("Scheduler: recurring expense execution failed for %s", rec.id)
            db.rollback()

    return processed

