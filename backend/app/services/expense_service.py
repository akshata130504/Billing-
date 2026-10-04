"""Expense domain service: CRUD, batch import, recurring profiles, and KPI summaries."""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import EntityNotFoundError, InvalidStateError, ValidationAppError
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
from backend.app.services import timezones
from backend.app.services.money import D, q2
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
        has_receipt=bool(expense.receipt_storage_key),
        receipt_url=f"/expenses/{expense.id}/receipt" if expense.receipt_storage_key else None,
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


def _customer_in_org(db: Session, organization_id: str, customer_id: str) -> Customer:
    customer = db.scalars(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == organization_id)
    ).first()
    if customer is None:
        raise EntityNotFoundError("Customer", customer_id)
    return customer


def _project_in_org(db: Session, organization_id: str, project_id: str) -> Project:
    project = db.scalars(
        select(Project).where(Project.id == project_id, Project.organization_id == organization_id)
    ).first()
    if project is None:
        raise EntityNotFoundError("Project", project_id)
    return project


def create_expense(db: Session, organization_id: str, data: ExpenseCreate) -> ExpenseRead:
    # References must exist in this organization: a stale or foreign id is a 404,
    # never silently stored.
    cust_name = data.customer_name
    if data.customer_id:
        customer = _customer_in_org(db, organization_id, data.customer_id)
        cust_name = cust_name or customer.display_name

    proj_name = data.project_name
    if data.project_id:
        proj = _project_in_org(db, organization_id, data.project_id)
        proj_name = proj_name or proj.name

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
    # Invoice linkage is owned by add_to_invoice / invoice void; never set from a PATCH.
    payload.pop("invoice_id", None)
    if "customer_id" in payload:
        cust_id = payload["customer_id"]
        if cust_id:
            cust = _customer_in_org(db, organization_id, cust_id)
            expense.customer_id = cust.id
            expense.customer_name = cust.display_name
        else:
            expense.customer_id = None
            expense.customer_name = payload.get("customer_name")

    if "project_id" in payload:
        proj_id = payload["project_id"]
        if proj_id:
            proj = _project_in_org(db, organization_id, proj_id)
            expense.project_id = proj.id
            expense.project_name = proj.name
        else:
            expense.project_id = None
            expense.project_name = payload.get("project_name")

    for field, val in payload.items():
        if field not in ("customer_id", "project_id", "customer_name", "project_name"):
            setattr(expense, field, val)

    db.commit()
    db.refresh(expense)
    return serialize_expense(expense)


def delete_expense(db: Session, organization_id: str, expense_id: str) -> None:
    expense = get_expense(db, organization_id, expense_id)
    db.delete(expense)
    db.commit()


def _expense_line(expense: Expense):
    from backend.app.services.money import LineInput

    amount = D(expense.billable_amount) if expense.billable_amount else D(expense.amount)
    desc = f"Expense: {expense.name} ({expense.date.isoformat()})"
    if expense.project_name:
        desc = f"{desc} - {expense.project_name}"
    return LineInput(
        description=desc[:500],
        quantity=Decimal("1"),
        unit_price=q2(amount),
        tax_rate_pct=q2(D(expense.tax_rate or 0)),
    )


def add_to_invoice(db: Session, ctx, expense_id: str, invoice_id: Optional[str] = None) -> ExpenseRead:
    """Bill an expense to its customer as a real invoice line.

    With `invoice_id` the line is appended to that DRAFT invoice (same customer and
    currency); otherwise a new draft invoice is created for the customer. The expense
    row is locked and marked INVOICED in the same transaction as the invoice change.
    """
    from backend.app.models.invoices import Invoice, InvoiceStatus
    from backend.app.schemas.common_refs import LineItemIn
    from backend.app.schemas.invoices import InvoiceUpdate
    from backend.app.services import audit, invoice_service

    organization_id = ctx.organization_id
    get_expense(db, organization_id, expense_id)  # 404 first
    expense = db.scalars(
        select(Expense)
        .where(Expense.id == expense_id, Expense.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if expense.invoice_id or expense.status == ExpenseStatus.INVOICED:
        raise InvalidStateError("This expense has already been added to an invoice.")
    if expense.status == ExpenseStatus.CANCELLED:
        raise InvalidStateError("A cancelled expense cannot be invoiced.")

    customer_id = expense.customer_id
    if not customer_id and expense.project_id:
        project = db.get(Project, expense.project_id)
        customer_id = project.customer_id if project is not None else None
    if not customer_id:
        raise ValidationAppError(
            "Link the expense to a customer (or a project with a customer) before invoicing it.",
            {"fields": {"customer_id": "required to invoice"}},
        )
    customer = _customer_in_org(db, organization_id, customer_id)
    line = _expense_line(expense)

    # Claim the expense first so its state commits together with the invoice change.
    expense.billable = True
    if not expense.billable_amount:
        expense.billable_amount = expense.amount
    expense.customer_id = customer.id
    expense.customer_name = expense.customer_name or customer.display_name
    expense.status = ExpenseStatus.INVOICED

    try:
        if invoice_id:
            invoice = invoice_service.get_invoice(db, organization_id, invoice_id)
            if invoice.status != InvoiceStatus.DRAFT:
                raise InvalidStateError("Expenses can only be added to draft invoices.")
            if invoice.customer_id != customer.id:
                raise ValidationAppError(
                    "The invoice belongs to a different customer than the expense.",
                    {"fields": {"invoice_id": "customer mismatch"}},
                )
            if (invoice.currency or "").upper() != (expense.currency or "").upper():
                raise ValidationAppError(
                    "The invoice currency differs from the expense currency.",
                    {"fields": {"invoice_id": "currency mismatch"}},
                )
            expense.invoice_id = invoice.id
            items = [
                LineItemIn(
                    offering_id=getattr(i, "offering_id", None),
                    product_id=i.product_id,
                    plan_id=i.plan_id,
                    description=i.description,
                    quantity=i.quantity,
                    unit_price=i.unit_price,
                    tax_rate_pct=i.tax_rate_pct,
                    pricing_explanation=getattr(i, "pricing_explanation", None),
                )
                for i in sorted(invoice.items, key=lambda x: x.position or 0)
            ]
            items.append(
                LineItemIn(
                    description=line.description,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    tax_rate_pct=line.tax_rate_pct,
                )
            )
            # Public invoice API: recomputes totals/GST, audits and commits (with the expense).
            invoice_service.update_invoice(db, ctx, invoice, InvoiceUpdate(items=items))
        else:
            invoice = invoice_service.create_invoice_record(
                db,
                organization_id=organization_id,
                customer=customer,
                lines=[line],
                currency=expense.currency,
                notes=f"Billable expense: {expense.name}",
                created_by_id=ctx.user.id,
            )
            expense.invoice_id = invoice.id
            db.flush()
            audit.record(
                db,
                action="INVOICE_CREATED",
                entity_type="invoice",
                entity_id=invoice.id,
                entity_label=invoice.invoice_number,
                ctx=ctx,
                after=invoice_service.snapshot(invoice),
            )
            audit.record(
                db,
                action="EXPENSE_INVOICED",
                entity_type="expense",
                entity_id=expense.id,
                entity_label=expense.name,
                ctx=ctx,
                after={"invoice_id": invoice.id, "invoice_number": invoice.invoice_number},
            )
            db.commit()
    except Exception:
        db.rollback()
        raise
    expense = get_expense(db, organization_id, expense_id)
    db.refresh(expense)
    return serialize_expense(expense)


def release_expenses_for_invoice(db: Session, invoice_id: str, organization_id: Optional[str] = None) -> int:
    """Detach expenses from a voided/deleted invoice so they can be billed again (no commit).

    Called by invoice_service.void_invoice / delete_invoice. Returns the count released.
    """
    stmt = select(Expense).where(Expense.invoice_id == invoice_id).with_for_update()
    if organization_id:
        stmt = stmt.where(Expense.organization_id == organization_id)
    released = 0
    for expense in db.scalars(stmt).all():
        expense.invoice_id = None
        if expense.status == ExpenseStatus.INVOICED:
            expense.status = ExpenseStatus.BILLABLE
        released += 1
    if released:
        db.flush()
    return released


# --- receipts ------------------------------------------------------------------------------

MAX_RECEIPT_SIZE = 10 * 1024 * 1024  # 10 MB
RECEIPT_TYPES = {
    # extension -> (mime type, magic-bytes check)
    ".pdf": ("application/pdf", lambda c: c.startswith(b"%PDF-")),
    ".png": ("image/png", lambda c: c.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda c: c.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda c: c.startswith(b"\xff\xd8\xff")),
    ".webp": ("image/webp", lambda c: c.startswith(b"RIFF") and b"WEBP" in c[:16]),
}


def receipts_dir(organization_id: str) -> str:
    """Private receipt store: a sibling of UPLOAD_DIR, which is served statically and
    must therefore never hold financial documents. Files are only reachable through
    the authenticated, org-scoped download endpoint."""
    from backend.app.core.config import settings

    root = os.path.join(os.path.dirname(os.path.abspath(settings.UPLOAD_DIR)), "private_uploads", "receipts")
    path = os.path.join(root, organization_id)
    os.makedirs(path, exist_ok=True)
    return path


def _receipt_path(expense: Expense) -> Optional[str]:
    if not expense.receipt_storage_key:
        return None
    base = os.path.realpath(receipts_dir(expense.organization_id))
    full = os.path.realpath(os.path.join(base, expense.receipt_storage_key))
    if os.path.commonpath([full, base]) != base:
        return None
    return full


def _validate_receipt(content: bytes, filename: str, content_type: Optional[str]) -> str:
    if not content:
        raise ValidationAppError("Uploaded receipt is empty.")
    if len(content) > MAX_RECEIPT_SIZE:
        raise ValidationAppError("Receipt exceeds the 10 MB limit.")
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in RECEIPT_TYPES:
        raise ValidationAppError("Receipts must be PDF, PNG, JPG or WEBP files.")
    mime, magic_ok = RECEIPT_TYPES[ext]
    if content_type and content_type.lower() not in (mime, "application/octet-stream"):
        raise ValidationAppError(f"File type '{content_type}' does not match a {ext} receipt.")
    if not magic_ok(content):
        raise ValidationAppError("File contents do not match the declared receipt type.")
    return ext


def save_receipt(db: Session, organization_id: str, expense_id: str, filename: str, content_type: Optional[str], content: bytes) -> ExpenseRead:
    expense = get_expense(db, organization_id, expense_id)
    ext = _validate_receipt(content, filename, content_type)
    storage_key = f"receipt_{expense.id}_{uuid.uuid4().hex}{ext}"
    dest = os.path.join(receipts_dir(organization_id), storage_key)
    with open(dest, "wb") as fh:
        fh.write(content)
    old_path = _receipt_path(expense)
    expense.receipt_storage_key = storage_key
    # Display metadata only; the client-supplied name is never used as a path.
    expense.receipt_file_name = os.path.basename(filename or f"receipt{ext}")[:255]
    expense.receipt_file_size = str(len(content))
    expense.receipt_file_type = RECEIPT_TYPES[ext][0]
    db.commit()
    if old_path and os.path.isfile(old_path) and old_path != os.path.realpath(dest):
        try:
            os.remove(old_path)
        except OSError as exc:
            logger.warning("Could not delete replaced receipt '%s': %s", old_path, exc)
    db.refresh(expense)
    return serialize_expense(expense)


def get_receipt_file(db: Session, organization_id: str, expense_id: str):
    """Return (path, media_type, download_name) for an expense's receipt, or 404."""
    expense = get_expense(db, organization_id, expense_id)
    path = _receipt_path(expense)
    if not path or not os.path.isfile(path):
        raise EntityNotFoundError("Receipt", expense_id)
    return path, expense.receipt_file_type or "application/octet-stream", expense.receipt_file_name or os.path.basename(path)


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
    if data.customer_id:
        cust_name = cust_name or _customer_in_org(db, organization_id, data.customer_id).display_name

    proj_name = data.project_name
    if data.project_id:
        proj_name = proj_name or _project_in_org(db, organization_id, data.project_id).name

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
    if payload.get("customer_id"):
        cust = _customer_in_org(db, organization_id, payload["customer_id"])
        payload.setdefault("customer_name", cust.display_name)
    if payload.get("project_id"):
        proj = _project_in_org(db, organization_id, payload["project_id"])
        payload.setdefault("project_name", proj.name)

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
    # The organization's business day, not the server's (date.today() is UTC in production).
    today = today or timezones.org_today_for_id(db, rec.organization_id)
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


def process_due_recurring_expenses(
    db: Session,
    *,
    today: Optional[date] = None,
    organization_id: Optional[str] = None,
    guard: Optional[Callable[[], bool]] = None,
) -> int:
    """Process active recurring expenses due on or before `today`.

    `today` defaults to each profile's organization-local date. `organization_id` limits the
    run to one organization (the scheduler calls this per organization with its local date).
    `guard` (scheduler only, see org_lifecycle.AutomationGuard) is re-checked before every
    expense, inside the transaction that commits it.
    """
    if today is not None:
        horizon = today
    elif organization_id:
        horizon = timezones.org_today_for_id(db, organization_id)
    else:
        # Latest date on Earth bounds the query; each row is re-checked on its org's date.
        horizon = timezones.utc_today() + timedelta(days=1)
    stmt = select(RecurringExpense).where(
        RecurringExpense.status == RecurringExpenseStatus.ACTIVE,
        RecurringExpense.next_run.is_not(None),
        RecurringExpense.next_run <= horizon,
    )
    if organization_id:
        stmt = stmt.where(RecurringExpense.organization_id == organization_id)
    due_recs = list(db.scalars(stmt).all())

    processed = 0
    for rec in due_recs:
        # Organization lifecycle: each expense commits on its own, so re-check per expense.
        if guard is not None and not guard():
            break
        try:
            run_day = today or (horizon if organization_id else timezones.org_today_for_id(db, rec.organization_id))
            exp = execute_recurring_expense(db, rec, today=run_day)
            db.commit()
            if exp is not None:
                processed += 1
        except Exception:
            logger.exception("Scheduler: recurring expense execution failed for %s", rec.id)
            db.rollback()

    return processed

