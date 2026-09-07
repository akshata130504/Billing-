"""Background billing jobs (contract §7): renewals, trial conversion, overdue marking, dunning.

`run_billing_jobs(db)` is the pure function (also behind POST /admin/jobs/run);
`start_scheduler()` / `stop_scheduler()` run it on an APScheduler interval with a
session of its own. Every subscription/invoice is processed in its own
try/except and committed individually so one bad row never stops the run.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models import Invoice, InvoiceStatus, Plan, Subscription, SubscriptionStatus
from backend.app.services import audit
from backend.app.services.invoice_service import mark_overdue, send_reminder
from backend.app.services.subscription_service import convert_trial, renew_subscription

_scheduler = None


def _load_subscription(db: Session, subscription_id: str) -> Optional[Subscription]:
    return db.scalars(
        select(Subscription)
        .options(selectinload(Subscription.customer), selectinload(Subscription.plan).selectinload(Plan.product))
        .where(Subscription.id == subscription_id)
    ).first()


def _load_invoice(db: Session, invoice_id: str) -> Optional[Invoice]:
    return db.scalars(
        select(Invoice).options(selectinload(Invoice.customer), selectinload(Invoice.items)).where(Invoice.id == invoice_id)
    ).first()


def run_billing_jobs(db: Session, *, today: Optional[date] = None) -> Dict[str, int]:
    """Run all four job steps once. Returns the counts the admin endpoint exposes."""
    today = today or date.today()
    counts = {"renewals": 0, "trials_converted": 0, "marked_overdue": 0, "reminders_sent": 0}
    ended = errors = 0

    # (a) trials that have ended -> active + first invoice
    trial_ids = list(
        db.scalars(
            select(Subscription.id).where(Subscription.status == SubscriptionStatus.TRIALING, Subscription.trial_end <= today)
        ).all()
    )
    for sid in trial_ids:
        try:
            sub = _load_subscription(db, sid)
            if sub is not None and sub.status == SubscriptionStatus.TRIALING:
                convert_trial(db, sub, actor_label=audit.SYSTEM_ACTOR)
                counts["trials_converted"] += 1
            db.commit()
        except Exception:
            errors += 1
            logger.exception("Scheduler: trial conversion failed for subscription %s", sid)
            db.rollback()

    # (b) active subscriptions due for renewal
    renewal_ids = list(
        db.scalars(
            select(Subscription.id).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.next_billing_date.is_not(None),
                Subscription.next_billing_date <= today,
            )
        ).all()
    )
    for sid in renewal_ids:
        try:
            sub = _load_subscription(db, sid)
            outcome = renew_subscription(db, sub, actor_label=audit.SYSTEM_ACTOR) if sub is not None else "skipped"
            db.commit()
            if outcome == "renewed":
                counts["renewals"] += 1
            elif outcome == "ended":
                ended += 1
        except Exception:
            errors += 1
            logger.exception("Scheduler: renewal failed for subscription %s", sid)
            db.rollback()

    # (c) open invoices past due -> overdue (+ owning subscription past_due)
    overdue_ids = list(
        db.scalars(
            select(Invoice.id).where(
                Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]), Invoice.due_date < today
            )
        ).all()
    )
    for iid in overdue_ids:
        try:
            inv = _load_invoice(db, iid)
            if inv is not None and mark_overdue(db, inv, actor_label=audit.SYSTEM_ACTOR):
                counts["marked_overdue"] += 1
            db.commit()
        except Exception:
            errors += 1
            logger.exception("Scheduler: overdue marking failed for invoice %s", iid)
            db.rollback()

    # (d) dunning reminders for overdue invoices
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.DUNNING_REMINDER_INTERVAL_DAYS)
    reminder_ids = list(
        db.scalars(
            select(Invoice.id).where(
                Invoice.status == InvoiceStatus.OVERDUE,
                Invoice.reminder_count < settings.DUNNING_MAX_REMINDERS,
                or_(Invoice.last_reminder_at.is_(None), Invoice.last_reminder_at <= cutoff),
            )
        ).all()
    )
    for iid in reminder_ids:
        try:
            inv = _load_invoice(db, iid)
            if inv is not None:
                send_reminder(db, inv, actor_label=audit.SYSTEM_ACTOR, commit=False)
                counts["reminders_sent"] += 1
            db.commit()
        except Exception:
            errors += 1
            logger.exception("Scheduler: reminder failed for invoice %s", iid)
            db.rollback()

    logger.info(
        "Billing jobs: renewals=%s trials_converted=%s marked_overdue=%s reminders_sent=%s ended=%s errors=%s",
        counts["renewals"],
        counts["trials_converted"],
        counts["marked_overdue"],
        counts["reminders_sent"],
        ended,
        errors,
    )
    return counts


def _job() -> None:
    from backend.app.core.database import SessionLocal

    db = SessionLocal()
    try:
        run_billing_jobs(db)
    except Exception:  # pragma: no cover - defensive; per-row errors are already caught
        logger.exception("Billing job run failed")
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    """Start the in-process APScheduler (idempotent). Returns the scheduler or None when disabled."""
    global _scheduler
    if not settings.SCHEDULER_ENABLED:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return None
    if _scheduler is not None:
        return _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _job,
        trigger="interval",
        minutes=max(1, int(settings.SCHEDULER_INTERVAL_MINUTES)),
        id="billing_jobs",
        name="Renewals, overdue marking and dunning",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30),
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler started; billing jobs every %s minute(s)", settings.SCHEDULER_INTERVAL_MINUTES)
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except Exception:  # pragma: no cover
        logger.exception("Scheduler shutdown failed")
    finally:
        _scheduler = None
        logger.info("Scheduler stopped")


__all__ = ["run_billing_jobs", "start_scheduler", "stop_scheduler"]
