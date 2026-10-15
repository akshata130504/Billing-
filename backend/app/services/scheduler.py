"""Background billing jobs (contract §7): renewals, trial conversion, overdue marking, dunning.

`run_billing_jobs(db)` is the pure function; `start_scheduler()` / `stop_scheduler()`
run it on an APScheduler interval with a session of its own. It runs only in the
dedicated scheduler process (there is no HTTP trigger). Every subscription/invoice is processed in its own
try/except and committed individually so one bad row never stops the run.

Concurrency: on PostgreSQL a run holds a session-level advisory lock on a dedicated
connection, so overlapping runs (several scheduler processes/replicas) skip instead
of double-processing. Each run records a
heartbeat row (see get_scheduler_heartbeat) for health checks.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, selectinload

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models import Invoice, InvoiceStatus, Organization, Plan, Subscription, SubscriptionStatus
from backend.app.models.billing_cycles import BillingCycle, BillingCycleStatus, SchedulerHeartbeat
from backend.app.services import audit
from backend.app.services.invoice_service import mark_overdue, send_reminder
from backend.app.services.subscription_service import renew_subscription
from backend.app.services import timezones
from backend.app.services.org_access import module_entitled
from backend.app.services.org_lifecycle import AutomationGuard, automation_allowed

_scheduler = None

JOB_NAME = "billing_jobs"
TRIAL_REMINDER_JOB_NAME = "trial_reminders"
PLATFORM_RECONCILE_JOB_NAME = "platform_reconciliation"
PLATFORM_NOTIFY_JOB_NAME = "platform_notifications"
# Arbitrary, stable 64-bit key for pg_try_advisory_lock ("RBILLJOB").
ADVISORY_LOCK_KEY = 0x52_42_49_4C_4C_4A_4F_42
# Its own key, so reconciliation and billing_jobs never block each other ("RPLATREC").
PLATFORM_RECONCILE_LOCK_KEY = 0x52_50_4C_41_54_52_45_43


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


def _org_todays(db: Session, today: Optional[date]) -> Dict[str, date]:
    """Each organization's current local date (its `timezone`), or the forced `today`."""
    return {
        org.id: (today or timezones.org_today(org))
        for org in db.scalars(select(Organization)).all()
    }


def _alert(event: str, summary: str, details: Dict[str, Any], dedup_key: str) -> None:
    """Operational alert (core/alerts: never raises, dedupes). Details carry ids and the
    exception type only - never messages/payloads that could hold secrets or PII."""
    try:
        from backend.app.core import alerts

        alerts.send_alert(event, summary, details, severity="error", dedup_key=dedup_key)
    except Exception:  # pragma: no cover - alerting must never break the scheduler
        logger.warning("Scheduler: could not send alert %s", event)


def _step_failed(step: str, exc: BaseException, **ids: Any) -> None:
    details: Dict[str, Any] = {"job": JOB_NAME, "step": step, "error_type": type(exc).__name__}
    details.update({k: v for k, v in ids.items() if v is not None})
    _alert(
        "scheduler.step_failed",
        f"Scheduler step '{step}' failed",
        details,
        dedup_key=f"scheduler.step_failed:{step}",
    )


def _run_failed(exc: BaseException, phase: str) -> None:
    _alert(
        "scheduler.run_failed",
        "Billing scheduler run failed",
        {"job": JOB_NAME, "phase": phase, "error_type": type(exc).__name__},
        dedup_key="scheduler.run_failed",
    )


def _run_step(db: Session, name: str, fn: Callable[[], Any]) -> tuple[Any, int]:
    """Run one independent job step; a failure is logged and rolled back, never fatal."""
    try:
        result = fn()
        db.commit()
        return result, 0
    except Exception as exc:
        logger.exception("Scheduler: step '%s' failed", name)
        db.rollback()
        _step_failed(name, exc)
        return None, 1


# --- steps owned by other services (imported lazily so an import error there never
# --- breaks scheduler start-up; each is wrapped by _run_step) -------------------------


def _purge_expired_pending_signups(db: Session):
    from backend.app.services import auth_service

    return auth_service.purge_expired_pending_signups(db)


def _process_pending_outbox(db: Session):
    """process_pending_outbox commits per event, so it gets a session of its own
    (bound to the same engine/connection source) instead of sharing the run's session."""
    from sqlalchemy.orm import Session as _Session

    from backend.app.services import outbox_processor

    own = _Session(bind=db.get_bind())
    try:
        return outbox_processor.process_pending_outbox(own)
    finally:
        own.close()


def _process_due_jobs(db: Session):
    from backend.app.services import outbox_processor

    return outbox_processor.process_due_jobs(db)


def _run_due_automation_schedules(db: Session):
    from backend.app.services import customization_service

    return customization_service.run_due_automation_schedules(db)


def _as_count(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple, set)):
        return len(value)
    if isinstance(value, dict):
        for key in ("processed", "count", "purged", "run", "executed", "sent"):
            if isinstance(value.get(key), int):
                return value[key]
    return 0


def _finalize_usage_before_renewal(db: Session, sub: Subscription) -> bool:
    """Rate the usage of the period that is ending (usage is billed in arrears).

    Only subscriptions that actually recorded usage in [current_period_start,
    current_period_end) are finalized; an already-finalized cycle is left alone.
    """
    from backend.app.services import meter_service

    if not meter_service.subscription_has_usage(db, sub.id, sub.current_period_start, sub.current_period_end):
        return False
    cycle = db.scalars(
        select(BillingCycle).where(
            BillingCycle.subscription_id == sub.id,
            BillingCycle.period_start == sub.current_period_start,
        )
    ).first()
    if cycle is None:
        from sqlalchemy import func

        max_cycle = db.scalar(select(func.max(BillingCycle.cycle_number)).where(BillingCycle.subscription_id == sub.id)) or 0
        cycle = BillingCycle(
            organization_id=sub.organization_id,
            subscription_id=sub.id,
            cycle_number=max_cycle + 1,
            period_start=sub.current_period_start,
            period_end=sub.current_period_end,
            status=BillingCycleStatus.OPEN,
        )
        db.add(cycle)
        db.flush()
    if cycle.status == BillingCycleStatus.FINALIZED:
        return False
    meter_service.finalize_usage_for_cycle_system(
        db, organization_id=sub.organization_id, subscription_id=sub.id, billing_cycle_id=cycle.id
    )
    return True


def _run_billing_jobs_unlocked(db: Session, today: Optional[date]) -> tuple[Dict[str, int], int]:
    org_today = _org_todays(db, today)
    # The latest local date across organizations bounds the candidate queries; each
    # row is then checked against its own organization's local date.
    horizon = max(org_today.values()) if org_today else (today or timezones.utc_today())

    def local_today(org_id: str) -> date:
        day = org_today.get(org_id) or today
        if day is None:  # organization created during the run
            day = org_today[org_id] = timezones.org_today_for_id(db, org_id)
        return day

    counts: Dict[str, int] = {"renewals": 0, "trials_converted": 0, "marked_overdue": 0, "reminders_sent": 0}
    ended = errors = 0

    # Organization free trials that have ended: record trial -> trial_expired (access already ended
    # at trial_ends_at; services/org_access.py). Platform metadata only, no billing work.
    try:
        from backend.app.services.org_access import expire_due_trials

        counts["org_trials_expired"] = expire_due_trials(db)
        db.commit()
    except Exception as exc:
        errors += 1
        logger.exception("Scheduler: recording expired organization trials failed")
        db.rollback()
        _step_failed("org_trial_expiry", exc)
    # Work not started because the organization is not ACTIVE or has jobs_paused
    # (services/org_lifecycle.py). The check runs inside each work item's own transaction.
    skipped_inactive = 0

    # (a) scheduled subscription changes due today - BEFORE renewals, so an end-of-term
    # change moves the subscription onto the new plan before its renewal invoice is built.
    scheduled_changes_applied = 0
    for oid, day in org_today.items():
        try:
            from backend.app.services.subscription_change_service import execute_due_scheduled_changes

            guard = AutomationGuard(db, oid, module="subscriptions")
            applied = execute_due_scheduled_changes(db, organization_id=oid, today=day, guard=guard)
            skipped_inactive += guard.refused
            scheduled_changes_applied += len(applied)
            db.commit()
        except Exception as exc:
            errors += 1
            logger.exception("Scheduler: applying scheduled subscription changes failed for organization %s", oid)
            db.rollback()
            _step_failed("scheduled_subscription_changes", exc, organization_id=oid)
    counts["scheduled_changes_applied"] = scheduled_changes_applied

    # (b) trials: conversion/charging, fallback plans, cancel-at-period-end and expiry
    # reminders all go through the trial service (one rule set for API and scheduler).
    trial_stats: Dict[str, int] = {}
    for oid, day in org_today.items():
        try:
            from backend.app.services.trial_service import evaluate_expiring_trials

            guard = AutomationGuard(db, oid, module="subscriptions")
            stats = evaluate_expiring_trials(db, today=day, org_id=oid, commit=True, guard=guard)
            skipped_inactive += guard.refused
            db.commit()
            for key, value in stats.items():
                trial_stats[key] = trial_stats.get(key, 0) + int(value or 0)
        except Exception as exc:
            errors += 1
            logger.exception("Scheduler: trial evaluation failed for organization %s", oid)
            db.rollback()
            _step_failed("trial_evaluation", exc, organization_id=oid)
    counts["trials_converted"] = trial_stats.get("converted", 0)
    counts["trials_fallback"] = trial_stats.get("fallback", 0)
    counts["trials_cancelled"] = trial_stats.get("cancelled", 0)
    counts["trials_past_due"] = trial_stats.get("past_due", 0)
    counts["trial_reminders_sent"] = trial_stats.get("reminders_sent", 0)

    # (c) active subscriptions due for renewal (usage of the ending period is finalized first)
    usage_finalized = 0
    renewal_ids = list(
        db.scalars(
            select(Subscription.id).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.next_billing_date.is_not(None),
                Subscription.next_billing_date <= horizon,
            )
        ).all()
    )
    for sid in renewal_ids:
        try:
            sub = _load_subscription(db, sid)
            if sub is None:
                continue
            day = local_today(sub.organization_id)
            if sub.next_billing_date is None or sub.next_billing_date > day:
                continue
            if not automation_allowed(db, sub.organization_id) or not module_entitled(
                db, sub.organization_id, "subscriptions"
            ):
                skipped_inactive += 1
                db.rollback()
                continue
            try:
                if _finalize_usage_before_renewal(db, sub):
                    usage_finalized += 1
            except Exception as exc:
                errors += 1
                logger.exception("Scheduler: usage finalization failed for subscription %s", sid)
                db.rollback()
                _step_failed("usage_finalization", exc, subscription_id=sid)
                sub = _load_subscription(db, sid)
                if sub is None:
                    continue
            # Usage finalization commits (or rolled back above), which releases the lock:
            # re-check in the transaction that builds and commits the renewal invoice.
            if not automation_allowed(db, sub.organization_id):
                skipped_inactive += 1
                db.rollback()
                continue
            outcome = renew_subscription(db, sub, actor_label=audit.SYSTEM_ACTOR, only_if_due=True, today=day)
            db.commit()
            if outcome == "renewed":
                counts["renewals"] += 1
            elif outcome == "ended":
                ended += 1
        except Exception as exc:
            errors += 1
            logger.exception("Scheduler: renewal failed for subscription %s", sid)
            db.rollback()
            _step_failed("renewal", exc, subscription_id=sid)
    counts["usage_finalized"] = usage_finalized

    # (d) open invoices past due -> overdue (+ owning subscription past_due)
    overdue_ids = list(
        db.scalars(
            select(Invoice.id).where(
                Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]), Invoice.due_date < horizon
            )
        ).all()
    )
    for iid in overdue_ids:
        try:
            inv = _load_invoice(db, iid)
            day = local_today(inv.organization_id) if inv is not None else None
            if inv is not None and inv.due_date < day:
                if not automation_allowed(db, inv.organization_id):
                    skipped_inactive += 1
                    db.rollback()
                    continue
                if mark_overdue(db, inv, actor_label=audit.SYSTEM_ACTOR, today=day):
                    counts["marked_overdue"] += 1
            db.commit()
        except Exception as exc:
            errors += 1
            logger.exception("Scheduler: overdue marking failed for invoice %s", iid)
            db.rollback()
            _step_failed("overdue_marking", exc, invoice_id=iid)

    # (e) dunning reminders for overdue invoices
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
                if not automation_allowed(db, inv.organization_id):
                    skipped_inactive += 1
                    db.rollback()
                    continue
                send_reminder(db, inv, actor_label=audit.SYSTEM_ACTOR, commit=False)
                counts["reminders_sent"] += 1
            db.commit()
        except Exception as exc:
            errors += 1
            logger.exception("Scheduler: reminder failed for invoice %s", iid)
            db.rollback()
            _step_failed("dunning_reminder", exc, invoice_id=iid)

    # (f) dunning recovery retries across organizations
    dunning_recovered = 0
    for oid in org_today:
        try:
            from backend.app.services.dunning_service import execute_dunning_retries

            guard = AutomationGuard(db, oid, module="dunning")
            res = execute_dunning_retries(db, oid, guard=guard)
            skipped_inactive += guard.refused
            dunning_recovered += res.get("recovered_count", 0)
            db.commit()
        except Exception as exc:
            errors += 1
            logger.exception("Scheduler: dunning retry execution failed for organization %s", oid)
            db.rollback()
            _step_failed("dunning_retries", exc, organization_id=oid)
    counts["dunning_recovered"] = dunning_recovered

    # (g) recurring expenses due today
    recurring_expenses_processed = 0
    for oid, day in org_today.items():
        try:
            from backend.app.services.expense_service import process_due_recurring_expenses

            guard = AutomationGuard(db, oid, module="expenses")
            recurring_expenses_processed += process_due_recurring_expenses(
                db, today=day, organization_id=oid, guard=guard
            )
            skipped_inactive += guard.refused
            db.commit()
        except Exception as exc:
            errors += 1
            logger.exception("Scheduler: processing due recurring expenses failed for organization %s", oid)
            db.rollback()
            _step_failed("recurring_expenses", exc, organization_id=oid)
    counts["recurring_expenses_processed"] = recurring_expenses_processed
    counts["skipped_org_inactive"] = skipped_inactive

    # (h) housekeeping owned by other services - independent, failure-isolated steps
    for key, name, fn in (
        ("pending_signups_purged", "purge_expired_pending_signups", _purge_expired_pending_signups),
        ("outbox_processed", "process_pending_outbox", _process_pending_outbox),
        ("durable_jobs_completed", "process_due_jobs", _process_due_jobs),
        ("automation_schedules_run", "run_due_automation_schedules", _run_due_automation_schedules),
    ):
        result, failed = _run_step(db, name, lambda fn=fn: fn(db))
        errors += failed
        counts[key] = _as_count(result)

    logger.info(
        "Billing jobs: renewals=%s trials_converted=%s marked_overdue=%s reminders_sent=%s dunning_recovered=%s scheduled_changes=%s recurring_expenses=%s usage_finalized=%s ended=%s errors=%s",
        counts["renewals"],
        counts["trials_converted"],
        counts["marked_overdue"],
        counts["reminders_sent"],
        counts.get("dunning_recovered", 0),
        counts.get("scheduled_changes_applied", 0),
        counts.get("recurring_expenses_processed", 0),
        counts.get("usage_finalized", 0),
        ended,
        errors,
    )
    return counts, errors


def _record_heartbeat(
    db: Session, *, started_at: datetime, counts: Dict[str, int], errors: int, skipped: bool = False,
    job_name: str = JOB_NAME,
) -> None:
    try:
        row = db.get(SchedulerHeartbeat, job_name)
        if row is None:
            row = SchedulerHeartbeat(job_name=job_name, total_runs=0, last_error_count=0)
            db.add(row)
        if not skipped:
            row.last_started_at = started_at
            row.last_finished_at = datetime.now(timezone.utc)
            row.last_error_count = errors
            row.last_counts = dict(counts)
            row.total_runs = int(row.total_runs or 0) + 1
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        logger.exception("Scheduler: could not record heartbeat")
        db.rollback()


def get_scheduler_heartbeat(db: Session) -> Optional[Dict[str, Any]]:
    """Last scheduler run for health checks: timestamps, error count and per-step counts.

    Returns None when the scheduler has never completed a run (or the table is missing).
    """
    try:
        row = db.get(SchedulerHeartbeat, JOB_NAME)
    except Exception:
        logger.exception("Scheduler: could not read heartbeat")
        db.rollback()
        return None
    if row is None or row.last_finished_at is None:
        return None
    finished = row.last_finished_at
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    return {
        "job_name": row.job_name,
        "last_started_at": row.last_started_at.isoformat() if row.last_started_at else None,
        "last_finished_at": finished.isoformat(),
        "seconds_since_last_run": int((datetime.now(timezone.utc) - finished).total_seconds()),
        "last_error_count": int(row.last_error_count or 0),
        "last_counts": row.last_counts or {},
        "total_runs": int(row.total_runs or 0),
        "interval_minutes": int(settings.SCHEDULER_INTERVAL_MINUTES),
    }


def _acquire_run_lock(db: Session, key: int = ADVISORY_LOCK_KEY):
    """PostgreSQL: take a session-level advisory lock on a dedicated connection.

    Returns (acquired, connection). The ORM session commits per row and may hop
    connections, so the lock lives on its own connection held for the whole run.
    Non-PostgreSQL databases (SQLite in dev/tests) run unlocked. Each job has its own `key`.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return True, None
    engine = getattr(bind, "engine", bind)
    conn = engine.connect()
    try:
        acquired = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar())
        conn.commit()
    except Exception:
        conn.close()
        raise
    if not acquired:
        conn.close()
        return False, None
    return True, conn


def _release_run_lock(conn, key: int = ADVISORY_LOCK_KEY) -> None:
    if conn is None:
        return
    try:
        conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
        conn.commit()
    except Exception:
        logger.exception("Scheduler: failed to release advisory lock")
    finally:
        conn.close()


def run_billing_jobs(db: Session, *, today: Optional[date] = None) -> Dict[str, int]:
    """Run all job steps once. Returns the counts the admin endpoint exposes.

    `today` forces one date for every organization (tests / backfills); by default each
    organization is processed on its own local date (Organization.timezone).
    """
    from backend.app.core.tenant_context import system_context
    with system_context():
        started_at = datetime.now(timezone.utc)
        try:
            acquired, lock_conn = _acquire_run_lock(db)
        except Exception as exc:
            _run_failed(exc, "acquire_lock")
            raise
        if not acquired:
            logger.info("Billing jobs skipped: another run holds the scheduler lock")
            return {
                "renewals": 0,
                "trials_converted": 0,
                "marked_overdue": 0,
                "reminders_sent": 0,
                "skipped_locked": 1,
            }
        try:
            try:
                counts, errors = _run_billing_jobs_unlocked(db, today)
            except Exception as exc:
                _run_failed(exc, "run")
                raise
            counts["errors"] = errors
            _record_heartbeat(db, started_at=started_at, counts=counts, errors=errors)
            return counts
        finally:
            _release_run_lock(lock_conn)


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


def _trial_reminder_job() -> None:
    """Send due free-trial reminder emails and the "trial expired" email. Light and frequent (seconds),
    separate from billing_jobs, because reminders are minutes apart in testing. Expiry itself (the
    read-only mode) never depends on this job."""
    from backend.app.core.database import SessionLocal
    from backend.app.services import platform_trial_service

    db = SessionLocal()
    try:
        for step in (platform_trial_service.send_due_trial_reminders, platform_trial_service.send_trial_expiry_emails):
            try:
                step(db)
            except Exception:  # pragma: no cover - defensive; one step never blocks the other
                logger.exception("Trial email step %s failed", getattr(step, "__name__", "?"))
                db.rollback()
    finally:
        db.close()


def _platform_reconciliation_job() -> None:
    """Re-read Rooman plan checkouts and paid subscriptions from Razorpay (missed / late webhooks) and
    record time-based lifecycle states. Separate from billing_jobs: Rooman's own payments, not tenants'."""
    from backend.app.core.database import SessionLocal
    from backend.app.services import platform_reconciliation_service

    db = SessionLocal()
    try:
        platform_reconciliation_service.run_reconciliation(db)
    except Exception:  # pragma: no cover - defensive; per-item errors are already caught
        logger.exception("Platform reconciliation run failed")
        db.rollback()
    finally:
        db.close()


def _platform_notification_job() -> None:
    """Send queued Rooman subscription lifecycle emails (platform_notifications) after their transactions
    committed, with retry / backoff. Sending only: no payment, subscription or entitlement change happens here."""
    from backend.app.core.database import SessionLocal
    from backend.app.services import platform_notification_service

    db = SessionLocal()
    try:
        platform_notification_service.run_delivery(db)
    except Exception:  # pragma: no cover - defensive; per-row errors are already caught
        logger.exception("Platform notification run failed")
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
        id=JOB_NAME,
        name="Renewals, overdue marking and dunning",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30),
    )
    scheduler.add_job(
        _trial_reminder_job,
        trigger="interval",
        seconds=max(5, int(settings.TRIAL_REMINDER_CHECK_SECONDS)),
        id=TRIAL_REMINDER_JOB_NAME,
        name="Free trial reminder emails",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10),
    )
    scheduler.add_job(
        _platform_reconciliation_job,
        trigger="interval",
        minutes=max(1, int(settings.PLATFORM_RECONCILE_INTERVAL_MINUTES)),
        id=PLATFORM_RECONCILE_JOB_NAME,
        name="Rooman plan checkout / subscription reconciliation with Razorpay",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    scheduler.add_job(
        _platform_notification_job,
        trigger="interval",
        seconds=max(10, int(settings.PLATFORM_NOTIFICATION_CHECK_SECONDS)),
        id=PLATFORM_NOTIFY_JOB_NAME,
        name="Rooman subscription lifecycle emails",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=45),
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


def run_forever() -> None:
    """Run the billing scheduler as a dedicated blocking worker process."""
    import signal
    from threading import Event

    stop_event = Event()

    def _handle_exit(signum, frame):
        logger.info("Received termination signal (%s); shutting down scheduler...", signum)
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, _handle_exit)
        signal.signal(signal.SIGTERM, _handle_exit)
    except (ValueError, AttributeError):
        pass

    from backend.app.core.database import assert_runtime_role_unprivileged

    assert_runtime_role_unprivileged()

    # Ensure scheduler is enabled when running as a dedicated worker
    settings.SCHEDULER_ENABLED = True
    start_scheduler()
    logger.info("Dedicated billing scheduler is running. Press Ctrl+C to terminate.")

    try:
        while not stop_event.is_set():
            stop_event.wait(timeout=1.0)
    finally:
        stop_scheduler()
        logger.info("Dedicated billing scheduler exited cleanly.")


__all__ = ["run_billing_jobs", "get_scheduler_heartbeat", "start_scheduler", "stop_scheduler", "run_forever"]

if __name__ == "__main__":
    run_forever()
