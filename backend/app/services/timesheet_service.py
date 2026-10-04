"""Timesheets and time tracking domain logic."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import EntityNotFoundError, ForbiddenError, InvalidStateError, ValidationAppError
from backend.app.models import (
    Customer,
    Invoice,
    MemberRole,
    ROLE_RANK,
    TimeEntry,
    TimeEntryStatus,
    User,
    utcnow,
)
from backend.app.schemas.timesheets import (
    _MAX_FUTURE_DAYS,
    TimeEntryCreate,
    TimeEntryRead,
    TimeEntrySummaryKPIs,
    TimeEntryUpdate,
    TimesheetInvoiceCreate,
    WeeklyMatrixRow,
    WeeklyTimesheetResponse,
)
from backend.app.services import audit
from backend.app.services import invoice_service
from backend.app.services import timezones
from backend.app.services.money import D, LineInput, q2


def _can_manage_all_entries(ctx: CurrentContext) -> bool:
    """Returns True if the current user has FINANCE role or above."""
    role = ctx.membership.role
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(MemberRole.FINANCE, 0)


def _check_entry_date(value: Optional[date], ctx: CurrentContext) -> None:
    """Business-day check against the organization's local date (the schema only applies a
    lenient, timezone-agnostic backstop). One day of slack for users in other timezones."""
    if value is None:
        return
    if (value - timezones.org_today(ctx.organization)).days > _MAX_FUTURE_DAYS:
        raise ValidationAppError(
            "Time entry date cannot be in the future.", {"fields": {"date": "in the future"}}
        )


def serialize_time_entry(entry: TimeEntry) -> TimeEntryRead:
    """Converts a TimeEntry model instance to a TimeEntryRead schema."""
    user_name = entry.user.full_name if entry.user else None
    user_email = entry.user.email if entry.user else None
    customer_name = entry.customer.display_name if entry.customer else None
    customer_number = entry.customer.customer_number if entry.customer else None
    invoice_number = entry.invoice.invoice_number if entry.invoice else None
    approved_by_name = entry.approver.full_name if entry.approver else None

    return TimeEntryRead(
        id=entry.id,
        organization_id=entry.organization_id,
        user_id=entry.user_id,
        user_name=user_name,
        user_email=user_email,
        customer_id=entry.customer_id,
        customer_name=customer_name,
        customer_number=customer_number,
        project_id=entry.project_id,
        project_name=entry.project_name,
        date=entry.date,
        start_time=entry.start_time,
        end_time=entry.end_time,
        duration_hours=q2(D(entry.duration_hours)),
        description=entry.description,
        billable=entry.billable,
        billing_rate=q2(D(entry.billing_rate)),
        billable_amount=q2(D(entry.billable_amount)),
        status=entry.status,
        invoice_id=entry.invoice_id,
        invoice_number=invoice_number,
        rejection_reason=entry.rejection_reason,
        approved_by_id=entry.approved_by_id,
        approved_by_name=approved_by_name,
        approved_at=entry.approved_at,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def create_time_entry(db: Session, data: TimeEntryCreate, ctx: CurrentContext) -> TimeEntryRead:
    """Creates a new time entry with tenant isolation and rate/amount calculation."""
    org_id = ctx.organization.id
    _check_entry_date(data.date, ctx)

    customer_id = data.customer_id
    project_name = data.project_name
    if data.project_id:
        from backend.app.models.projects import Project

        project = db.scalar(select(Project).where(Project.organization_id == org_id, Project.id == data.project_id))
        if project is not None:
            # Hours logged against a project bill to the project's customer.
            customer_id = customer_id or project.customer_id
            project_name = project_name or project.name

    if customer_id:
        cust = db.scalar(select(Customer).where(Customer.organization_id == org_id, Customer.id == customer_id))
        if not cust:
            raise EntityNotFoundError("Customer", customer_id)

    duration = q2(D(data.duration_hours))
    if duration <= Decimal("0.00"):
        raise ValidationAppError("duration_hours must be greater than 0")

    rate = q2(D(data.billing_rate)) if data.billable else Decimal("0.00")
    billable_amount = q2(duration * rate) if data.billable else Decimal("0.00")

    entry = TimeEntry(
        organization_id=org_id,
        user_id=ctx.user.id,
        customer_id=customer_id,
        project_id=data.project_id,
        project_name=project_name,
        date=data.date,
        start_time=data.start_time,
        end_time=data.end_time,
        duration_hours=duration,
        description=data.description,
        billable=data.billable,
        billing_rate=rate,
        billable_amount=billable_amount,
        status=TimeEntryStatus.DRAFT,
    )

    db.add(entry)
    db.flush()

    audit.record(
        db,
        action="TIME_ENTRY_CREATED",
        entity_type="time_entry",
        entity_id=entry.id,
        ctx=ctx,
        after={
            "date": entry.date.isoformat(),
            "duration_hours": str(entry.duration_hours),
            "billable": entry.billable,
            "billable_amount": str(entry.billable_amount),
            "project_name": entry.project_name,
        },
    )

    db.commit()
    db.refresh(entry)
    return serialize_time_entry(entry)


def get_time_entry(db: Session, entry_id: str, ctx: CurrentContext) -> TimeEntryRead:
    """Retrieves a single time entry ensuring tenant isolation."""
    entry = db.scalar(
        select(TimeEntry)
        .options(selectinload(TimeEntry.user), selectinload(TimeEntry.customer), selectinload(TimeEntry.invoice), selectinload(TimeEntry.approver))
        .where(TimeEntry.organization_id == ctx.organization.id, TimeEntry.id == entry_id)
    )
    if not entry:
        raise EntityNotFoundError("TimeEntry", entry_id)
    return serialize_time_entry(entry)


def update_time_entry(db: Session, entry_id: str, data: TimeEntryUpdate, ctx: CurrentContext) -> TimeEntryRead:
    """Updates an existing time entry respecting role-based access control."""
    org_id = ctx.organization.id
    entry = db.scalar(
        select(TimeEntry).where(TimeEntry.organization_id == org_id, TimeEntry.id == entry_id)
    )
    if not entry:
        raise EntityNotFoundError("TimeEntry", entry_id)

    # Permission check
    if not _can_manage_all_entries(ctx) and entry.user_id != ctx.user.id:
        raise ForbiddenError("You can only modify your own time entries")

    if entry.status == TimeEntryStatus.BILLED:
        raise InvalidStateError("Billed time entries cannot be edited")

    if not _can_manage_all_entries(ctx) and entry.status in (TimeEntryStatus.APPROVED, TimeEntryStatus.SUBMITTED):
        raise InvalidStateError(f"Cannot edit time entry in '{entry.status.value}' status")

    if data.customer_id is not None:
        if data.customer_id != "":
            cust = db.scalar(select(Customer).where(Customer.organization_id == org_id, Customer.id == data.customer_id))
            if not cust:
                raise EntityNotFoundError("Customer", data.customer_id)
            entry.customer_id = data.customer_id
        else:
            entry.customer_id = None

    if data.project_id is not None:
        entry.project_id = data.project_id or None
    if data.project_name is not None:
        entry.project_name = data.project_name or None
    if data.date is not None:
        _check_entry_date(data.date, ctx)
        entry.date = data.date
    if data.start_time is not None:
        entry.start_time = data.start_time
    if data.end_time is not None:
        entry.end_time = data.end_time
    if data.description is not None:
        entry.description = data.description
    if data.billable is not None:
        entry.billable = data.billable
    if data.duration_hours is not None:
        entry.duration_hours = q2(D(data.duration_hours))
    if data.billing_rate is not None:
        entry.billing_rate = q2(D(data.billing_rate))

    # Recalculate billable amount
    if entry.billable:
        entry.billable_amount = q2(D(entry.duration_hours) * D(entry.billing_rate))
    else:
        entry.billable_amount = Decimal("0.00")

    audit.record(
        db,
        action="TIME_ENTRY_UPDATED",
        entity_type="time_entry",
        entity_id=entry.id,
        ctx=ctx,
        after={
            "duration_hours": str(entry.duration_hours),
            "billable": entry.billable,
            "billable_amount": str(entry.billable_amount),
            "status": entry.status.value,
        },
    )

    db.commit()
    db.refresh(entry)
    return serialize_time_entry(entry)


def delete_time_entry(db: Session, entry_id: str, ctx: CurrentContext) -> None:
    """Deletes a time entry if not yet billed."""
    org_id = ctx.organization.id
    entry = db.scalar(
        select(TimeEntry).where(TimeEntry.organization_id == org_id, TimeEntry.id == entry_id)
    )
    if not entry:
        raise EntityNotFoundError("TimeEntry", entry_id)

    if not _can_manage_all_entries(ctx) and entry.user_id != ctx.user.id:
        raise ForbiddenError("You can only delete your own time entries")

    if entry.status == TimeEntryStatus.BILLED:
        raise InvalidStateError("Billed time entries cannot be deleted")

    db.delete(entry)
    audit.record(
        db,
        action="TIME_ENTRY_DELETED",
        entity_type="time_entry",
        entity_id=entry_id,
        ctx=ctx,
    )
    db.commit()


def list_time_entries(
    db: Session,
    ctx: CurrentContext,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    customer_id: Optional[str] = None,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    billable: Optional[bool] = None,
    status: Optional[TimeEntryStatus] = None,
    search: Optional[str] = None,
) -> List[TimeEntryRead]:
    """Lists time entries with flexible filtering and tenant isolation."""
    org_id = ctx.organization.id
    query = (
        select(TimeEntry)
        .options(
            selectinload(TimeEntry.user),
            selectinload(TimeEntry.customer),
            selectinload(TimeEntry.invoice),
            selectinload(TimeEntry.approver),
        )
        .where(TimeEntry.organization_id == org_id)
    )

    if start_date:
        query = query.where(TimeEntry.date >= start_date)
    if end_date:
        query = query.where(TimeEntry.date <= end_date)
    if customer_id:
        query = query.where(TimeEntry.customer_id == customer_id)
    if project_id:
        query = query.where(TimeEntry.project_id == project_id)
    if user_id:
        query = query.where(TimeEntry.user_id == user_id)
    if billable is not None:
        query = query.where(TimeEntry.billable == billable)
    if status:
        query = query.where(TimeEntry.status == status)
    if search:
        s = f"%{search.strip()}%"
        query = query.where(
            or_(
                TimeEntry.description.ilike(s),
                TimeEntry.project_name.ilike(s),
            )
        )

    entries = db.scalars(query.order_by(TimeEntry.date.desc(), TimeEntry.created_at.desc())).all()
    return [serialize_time_entry(e) for e in entries]


def get_timesheet_summary_kpis(
    db: Session,
    ctx: CurrentContext,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> TimeEntrySummaryKPIs:
    """Aggregates real KPI metrics across time entries in the organization."""
    org_id = ctx.organization.id
    query = select(TimeEntry).where(TimeEntry.organization_id == org_id)

    if start_date:
        query = query.where(TimeEntry.date >= start_date)
    if end_date:
        query = query.where(TimeEntry.date <= end_date)

    entries = db.scalars(query).all()

    total_hours = sum((D(e.duration_hours) for e in entries), Decimal("0.00"))
    billable_hours = sum((D(e.duration_hours) for e in entries if e.billable), Decimal("0.00"))
    non_billable_hours = total_hours - billable_hours
    billable_amount = sum((D(e.billable_amount) for e in entries if e.billable), Decimal("0.00"))
    unbilled_amount = sum((D(e.billable_amount) for e in entries if e.billable and e.status != TimeEntryStatus.BILLED), Decimal("0.00"))
    billed_amount = sum((D(e.billable_amount) for e in entries if e.status == TimeEntryStatus.BILLED), Decimal("0.00"))
    pending_approval_count = sum(1 for e in entries if e.status == TimeEntryStatus.SUBMITTED)

    return TimeEntrySummaryKPIs(
        total_hours=q2(total_hours),
        billable_hours=q2(billable_hours),
        non_billable_hours=q2(non_billable_hours),
        billable_amount=q2(billable_amount),
        unbilled_amount=q2(unbilled_amount),
        billed_amount=q2(billed_amount),
        pending_approval_count=pending_approval_count,
    )


def get_weekly_matrix(db: Session, ctx: CurrentContext, week_start: date) -> WeeklyTimesheetResponse:
    """Builds a weekly matrix response for Mon-Sun starting at week_start."""
    org_id = ctx.organization.id
    # Align to Monday if not already
    start = week_start - timedelta(days=week_start.weekday())
    end = start + timedelta(days=6)

    days_list = [(start + timedelta(days=i)).isoformat() for i in range(7)]

    entries = db.scalars(
        select(TimeEntry)
        .options(selectinload(TimeEntry.user), selectinload(TimeEntry.customer))
        .where(
            TimeEntry.organization_id == org_id,
            TimeEntry.date >= start,
            TimeEntry.date <= end,
        )
    ).all()

    # Group entries by (user_id, project_id, project_name, customer_id)
    groups: Dict[str, Dict[str, Any]] = {}
    day_totals: Dict[str, Decimal] = {d: Decimal("0.00") for d in days_list}

    for e in entries:
        d_str = e.date.isoformat()
        hours = D(e.duration_hours)
        day_totals[d_str] = day_totals.get(d_str, Decimal("0.00")) + hours

        group_key = f"{e.user_id}:{e.project_id or 'none'}:{e.customer_id or 'none'}"
        if group_key not in groups:
            groups[group_key] = {
                "key": group_key,
                "user_id": e.user_id,
                "user_name": e.user.full_name if e.user else "Team Member",
                "customer_id": e.customer_id,
                "customer_name": e.customer.display_name if e.customer else None,
                "project_id": e.project_id,
                "project_name": e.project_name or "General / Non-project",
                "daily_hours": {d: Decimal("0.00") for d in days_list},
                "total_hours": Decimal("0.00"),
                "billable_hours": Decimal("0.00"),
                "billable_amount": Decimal("0.00"),
            }

        grp = groups[group_key]
        grp["daily_hours"][d_str] = grp["daily_hours"].get(d_str, Decimal("0.00")) + hours
        grp["total_hours"] += hours
        if e.billable:
            grp["billable_hours"] += hours
            grp["billable_amount"] += D(e.billable_amount)

    rows = [
        WeeklyMatrixRow(
            key=g["key"],
            user_id=g["user_id"],
            user_name=g["user_name"],
            customer_id=g["customer_id"],
            customer_name=g["customer_name"],
            project_id=g["project_id"],
            project_name=g["project_name"],
            daily_hours={d: q2(h) for d, h in g["daily_hours"].items()},
            total_hours=q2(g["total_hours"]),
            billable_hours=q2(g["billable_hours"]),
            billable_amount=q2(g["billable_amount"]),
        )
        for g in groups.values()
    ]

    total_hours = sum((r.total_hours for r in rows), Decimal("0.00"))
    billable_hours = sum((r.billable_hours for r in rows), Decimal("0.00"))

    return WeeklyTimesheetResponse(
        week_start=start,
        week_end=end,
        total_hours=q2(total_hours),
        billable_hours=q2(billable_hours),
        non_billable_hours=q2(total_hours - billable_hours),
        rows=rows,
        day_totals={d: q2(h) for d, h in day_totals.items()},
    )


def submit_time_entry(db: Session, entry_id: str, ctx: CurrentContext) -> TimeEntryRead:
    """Submits a draft or rejected time entry for approval."""
    org_id = ctx.organization.id
    entry = db.scalar(select(TimeEntry).where(TimeEntry.organization_id == org_id, TimeEntry.id == entry_id))
    if not entry:
        raise EntityNotFoundError("TimeEntry", entry_id)

    if not _can_manage_all_entries(ctx) and entry.user_id != ctx.user.id:
        raise ForbiddenError("You can only submit your own time entries")

    if entry.status not in (TimeEntryStatus.DRAFT, TimeEntryStatus.REJECTED):
        raise InvalidStateError(f"Cannot submit time entry from '{entry.status.value}' state")

    entry.status = TimeEntryStatus.SUBMITTED
    entry.rejection_reason = None

    audit.record(
        db,
        action="TIMESHEET_SUBMITTED",
        entity_type="time_entry",
        entity_id=entry.id,
        ctx=ctx,
    )
    db.commit()
    db.refresh(entry)
    return serialize_time_entry(entry)


def approve_time_entry(db: Session, entry_id: str, ctx: CurrentContext) -> TimeEntryRead:
    """Approves a submitted time entry (requires Finance/Admin role)."""
    if not _can_manage_all_entries(ctx):
        raise ForbiddenError("Only finance or admin members can approve time entries")

    org_id = ctx.organization.id
    entry = db.scalar(select(TimeEntry).where(TimeEntry.organization_id == org_id, TimeEntry.id == entry_id))
    if not entry:
        raise EntityNotFoundError("TimeEntry", entry_id)

    if entry.user_id == ctx.user.id:
        raise ForbiddenError("You cannot approve your own time entries; ask another finance or admin member.")

    if entry.status not in (TimeEntryStatus.SUBMITTED, TimeEntryStatus.DRAFT):
        raise InvalidStateError(f"Cannot approve entry with status '{entry.status.value}'")

    entry.status = TimeEntryStatus.APPROVED
    entry.approved_by_id = ctx.user.id
    entry.approved_at = utcnow()
    entry.rejection_reason = None

    audit.record(
        db,
        action="TIMESHEET_APPROVED",
        entity_type="time_entry",
        entity_id=entry.id,
        ctx=ctx,
    )
    db.commit()
    db.refresh(entry)
    return serialize_time_entry(entry)


def reject_time_entry(db: Session, entry_id: str, reason: Optional[str], ctx: CurrentContext) -> TimeEntryRead:
    """Rejects a submitted time entry with an optional explanation."""
    if not _can_manage_all_entries(ctx):
        raise ForbiddenError("Only finance or admin members can reject time entries")

    org_id = ctx.organization.id
    entry = db.scalar(select(TimeEntry).where(TimeEntry.organization_id == org_id, TimeEntry.id == entry_id))
    if not entry:
        raise EntityNotFoundError("TimeEntry", entry_id)

    if entry.status not in (TimeEntryStatus.SUBMITTED, TimeEntryStatus.DRAFT):
        raise InvalidStateError(f"Cannot reject entry with status '{entry.status.value}'")

    entry.status = TimeEntryStatus.REJECTED
    entry.rejection_reason = reason or "Timesheet entry rejected by reviewer"

    audit.record(
        db,
        action="TIMESHEET_REJECTED",
        entity_type="time_entry",
        entity_id=entry.id,
        ctx=ctx,
        after={"reason": entry.rejection_reason},
    )
    db.commit()
    db.refresh(entry)
    return serialize_time_entry(entry)


def generate_invoice_from_timesheets(
    db: Session,
    payload: TimesheetInvoiceCreate,
    ctx: CurrentContext,
) -> Dict[str, Any]:
    """Converts billable time entries into an actual invoice using existing invoice_service."""
    if not _can_manage_all_entries(ctx):
        raise ForbiddenError("Only finance or admin members can generate invoices from timesheets")

    org_id = ctx.organization.id
    customer = db.scalar(select(Customer).where(Customer.organization_id == org_id, Customer.id == payload.customer_id))
    if not customer:
        raise EntityNotFoundError("Customer", payload.customer_id)

    # Lock the rows for the whole transaction so two concurrent "generate invoice"
    # requests cannot both bill the same entries (FOR UPDATE; a no-op on SQLite).
    entries = db.scalars(
        select(TimeEntry)
        .where(
            TimeEntry.organization_id == org_id,
            TimeEntry.customer_id == payload.customer_id,
            TimeEntry.id.in_(payload.time_entry_ids),
        )
        .order_by(TimeEntry.date, TimeEntry.created_at)
        .with_for_update()
    ).all()

    if not entries:
        raise ValidationAppError("No valid time entries found for invoice generation")

    # Every requested entry must exist, belong to this organization and to this
    # customer. Silently invoicing only the subset that matched would under-bill
    # without telling anyone.
    found_ids = {e.id for e in entries}
    missing = [eid for eid in payload.time_entry_ids if eid not in found_ids]
    if missing:
        raise ValidationAppError(
            "Some time entries do not exist or do not belong to this customer.",
            {"fields": {"time_entry_ids": missing}},
        )

    for e in entries:
        if not e.billable:
            raise ValidationAppError(f"Time entry {e.id} is marked non-billable and cannot be invoiced")
        if e.status == TimeEntryStatus.BILLED or e.invoice_id:
            raise InvalidStateError(f"Time entry {e.id} is already billed on invoice {e.invoice_id}")
        if e.status == TimeEntryStatus.REJECTED:
            raise InvalidStateError(f"Time entry {e.id} was rejected by a reviewer and cannot be invoiced")
        if e.status != TimeEntryStatus.APPROVED:
            raise InvalidStateError(
                f"Time entry {e.id} must be approved before invoicing (current status: '{e.status.value}')"
            )

    tax_rate = default_tax_rate_pct(ctx.organization)
    lines: List[LineInput] = []
    for e in entries:
        desc = f"Time Tracking: {e.project_name or 'General Services'} - {e.description} ({e.date.isoformat()})"
        lines.append(
            LineInput(
                description=desc[:500],
                quantity=q2(D(e.duration_hours)),
                unit_price=q2(D(e.billing_rate)),
                tax_rate_pct=tax_rate,
            )
        )

    issue_date = payload.issue_date or timezones.org_today(ctx.organization)
    due_date = payload.due_date or (issue_date + timedelta(days=customer.payment_terms_days or 30))

    # One transaction: the invoice is built with the non-committing builder, the entries
    # are marked BILLED against it, and a single commit makes both visible together.
    try:
        created_invoice = invoice_service.create_invoice_record(
            db,
            organization_id=org_id,
            customer=customer,
            lines=lines,
            issue_date=issue_date,
            due_date=due_date,
            currency=customer.currency or ctx.organization.default_currency or "INR",
            notes=payload.notes or "Generated from approved timesheet entries.",
            created_by_id=ctx.user.id,
        )
        for e in entries:
            e.status = TimeEntryStatus.BILLED
            e.invoice_id = created_invoice.id
        db.flush()
        audit.record(
            db,
            action="INVOICE_CREATED",
            entity_type="invoice",
            entity_id=created_invoice.id,
            entity_label=created_invoice.invoice_number,
            ctx=ctx,
            after=invoice_service.snapshot(created_invoice),
        )
        audit.record(
            db,
            action="TIMESHEETS_BILLED_TO_INVOICE",
            entity_type="invoice",
            entity_id=created_invoice.id,
            ctx=ctx,
            after={
                "invoice_number": created_invoice.invoice_number,
                "entries_count": len(entries),
                "total_amount": str(created_invoice.total),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "id": created_invoice.id,
        "invoice_number": created_invoice.invoice_number,
        "status": created_invoice.status.value if hasattr(created_invoice.status, "value") else str(created_invoice.status),
        "customer_id": created_invoice.customer_id,
        "total": str(created_invoice.total),
        "subtotal": str(created_invoice.subtotal),
        "issue_date": created_invoice.issue_date.isoformat() if created_invoice.issue_date else None,
        "due_date": created_invoice.due_date.isoformat() if created_invoice.due_date else None,
    }


def default_tax_rate_pct(organization) -> Decimal:
    """GST rate for service lines that carry no product: the org default, else 18%."""
    raw = getattr(organization, "default_tax_rate_pct", None) if organization is not None else None
    if raw is None:
        return Decimal("18.00")
    return q2(D(raw))


def release_time_entries_for_invoice(db: Session, invoice_id: str, organization_id: Optional[str] = None) -> int:
    """Return BILLED entries to APPROVED when their invoice is voided or deleted.

    Called by invoice_service.void_invoice / delete_invoice (in their transaction; no
    commit here) so the hours can be billed again. Returns the number of entries released.
    """
    stmt = select(TimeEntry).where(TimeEntry.invoice_id == invoice_id).with_for_update()
    if organization_id:
        stmt = stmt.where(TimeEntry.organization_id == organization_id)
    released = 0
    for entry in db.scalars(stmt).all():
        entry.invoice_id = None
        if entry.status == TimeEntryStatus.BILLED:
            entry.status = TimeEntryStatus.APPROVED
        released += 1
    if released:
        db.flush()
    return released
