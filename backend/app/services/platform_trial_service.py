"""The organization's own free trial (platform level; unrelated to tenant `trial_service`, which is
about a tenant's customers).

- `start_trial` is called when signup creates the organization (same transaction).
- Expiry is derived from `trial_ends_at` and the current time on every request
  (`trial_info` / `is_trial_expired`); the scheduler is only needed for the reminder emails.
- `send_due_trial_reminders` is run by a small scheduler job. Every reminder offset is handled at
  most once and never sent late (see TRIAL_REMINDER_TOLERANCE_SECONDS).

Durations and offsets come from settings (minutes), never from constants here.
"""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models import (
    Membership,
    MemberRole,
    MembershipStatus,
    Organization,
    OrganizationStatus,
    PlatformSubscription,
    PlatformSubscriptionState,
    User,
)
from backend.app.services.email import frontend_url, send_email

# The in-app plans page (display only for now). Emails link to it; it needs a normal sign-in.
PLANS_PATH = "settings/subscription"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def trial_duration() -> timedelta:
    return timedelta(minutes=max(0, int(settings.TRIAL_DURATION_MINUTES)))


def reminder_offsets() -> List[int]:
    """Configured "minutes remaining" offsets, largest first. Junk entries are ignored."""
    offsets = set()
    for part in str(settings.TRIAL_REMINDER_OFFSETS_MINUTES or "").split(","):
        part = part.strip()
        if part.isdigit() and int(part) > 0:
            offsets.add(int(part))
    return sorted(offsets, reverse=True)


def format_minutes(minutes: int) -> str:
    """'15 minutes', '1 hour', '14 days' - whole units only, for email copy."""
    for unit_minutes, singular in ((1440, "day"), (60, "hour")):
        if minutes >= unit_minutes and minutes % unit_minutes == 0:
            count = minutes // unit_minutes
            return f"{count} {singular}{'' if count == 1 else 's'}"
    return f"{minutes} minute{'' if minutes == 1 else 's'}"


# --- state ---------------------------------------------------------------------------------------------


def start_trial(db: Session, organization_id: str, now: Optional[datetime] = None) -> Optional[PlatformSubscription]:
    """Create the organization's trial row (flush only; the caller commits). None when trials are off."""
    duration = trial_duration()
    if duration <= timedelta(0):
        return None
    now = now or _utcnow()
    sub = PlatformSubscription(
        organization_id=organization_id,
        state=PlatformSubscriptionState.TRIALING.value,
        trial_started_at=now,
        trial_ends_at=now + duration,
        reminders_sent=[],
    )
    db.add(sub)
    db.flush()
    return sub


def get_subscription(db: Session, organization_id: str) -> Optional[PlatformSubscription]:
    return db.scalars(
        select(PlatformSubscription).where(PlatformSubscription.organization_id == organization_id)
    ).first()


def effective_state(sub: PlatformSubscription, now: Optional[datetime] = None) -> str:
    now = now or _utcnow()
    if sub.state == PlatformSubscriptionState.TRIALING.value and _aware(sub.trial_ends_at) <= now:
        return PlatformSubscriptionState.TRIAL_EXPIRED.value
    return sub.state


def trial_info(db: Session, organization_id: str, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """What the SPA needs for the banner, or None for organizations without a trial - including those
    whose row has moved on to a paid plan (platform_subscription_service.summary describes those).

    `server_time` lets the browser correct for its own clock being off.
    """
    sub = get_subscription(db, organization_id)
    if sub is None or sub.state != PlatformSubscriptionState.TRIALING.value:
        return None
    now = now or _utcnow()
    ends = _aware(sub.trial_ends_at)
    return {
        "state": effective_state(sub, now),
        "trial_started_at": _aware(sub.trial_started_at),
        "trial_ends_at": ends,
        "server_time": now,
        "seconds_remaining": max(0, int((ends - now).total_seconds())),
    }


def is_trial_expired(db: Session, organization_id: str, now: Optional[datetime] = None) -> bool:
    sub = get_subscription(db, organization_id)
    return sub is not None and effective_state(sub, now) == PlatformSubscriptionState.TRIAL_EXPIRED.value


# --- emails --------------------------------------------------------------------------------------------


def _card(title: str, subtitle: str, paragraphs: List[str], button_label: str, button_url: str) -> str:
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
    .card {{ max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 32px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
    .header {{ text-align: center; margin-bottom: 24px; }}
    .title {{ font-size: 20px; font-weight: 700; color: #0f172a; margin: 0 0 8px 0; }}
    .subtitle {{ font-size: 14px; color: #64748b; margin: 0; }}
    .cta {{ text-align: center; margin: 32px 0; }}
    .button {{ display: inline-block; background: #4f46e5; color: #ffffff !important; text-decoration: none; font-weight: 600; padding: 12px 28px; border-radius: 8px; }}
    .footer {{ font-size: 12px; color: #94a3b8; text-align: center; margin-top: 32px; border-top: 1px solid #f1f5f9; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1 class="title">{html.escape(title)}</h1>
      <p class="subtitle">{html.escape(subtitle)}</p>
    </div>
    {body}
    <div class="cta">
      <a class="button" href="{html.escape(button_url, quote=True)}">{html.escape(button_label)}</a>
    </div>
    <div class="footer">
      &copy; Rooman Billing. All rights reserved.
    </div>
  </div>
</body>
</html>"""


def welcome_email(full_name: str, organization_name: str) -> tuple[str, str, str]:
    """(subject, text, html) for the trial-start email. A plain app link only: no secrets."""
    length = format_minutes(max(0, int(settings.TRIAL_DURATION_MINUTES)))
    link = frontend_url("dashboard")
    subject = "Welcome to Rooman Billing - your free trial has started"
    text = (
        f"Hello {full_name},\n\n"
        f"Welcome to Rooman Billing! Your organization \"{organization_name}\" is ready and your free trial "
        f"has started. It runs for {length} and includes every feature.\n\n"
        f"Open Rooman Billing: {link}\n\n"
        "We'll email you before the trial ends. When it ends your data stays safe and viewable; "
        "you'll just need to choose a plan to keep making changes.\n\n"
        "— Rooman Billing"
    )
    page = _card(
        "Your free trial has started",
        f"Welcome to Rooman Billing, {full_name}!",
        [
            f"Your organization <strong>{html.escape(organization_name)}</strong> is ready. "
            f"Your free trial runs for <strong>{html.escape(length)}</strong> and includes every feature.",
            "We'll email you before it ends. When it does, your data stays safe and viewable; "
            "you'll just need to choose a plan to keep making changes.",
        ],
        "Open Rooman Billing",
        link,
    )
    return subject, text, page


def reminder_email(full_name: str, organization_name: str, offset_minutes: int) -> tuple[str, str, str]:
    """(subject, text, html) for a "trial ends soon" reminder. A plain link to the plans page."""
    left = format_minutes(offset_minutes)
    link = frontend_url(PLANS_PATH)
    subject = f"Your Rooman Billing free trial ends in {left}"
    text = (
        f"Hello {full_name},\n\n"
        f"Your free trial for \"{organization_name}\" ends in {left}.\n"
        "When it ends your data stays safe and viewable, but changes are paused until you choose a plan.\n\n"
        f"View plans: {link}\n\n"
        "— Rooman Billing"
    )
    page = _card(
        f"Your free trial ends in {left}",
        f"Hello {full_name},",
        [
            f"The free trial for <strong>{html.escape(organization_name)}</strong> ends in "
            f"<strong>{html.escape(left)}</strong>.",
            "When it ends your data stays safe and viewable, but changes are paused until you choose a plan.",
        ],
        "View Plans",
        link,
    )
    return subject, text, page


def expiry_email(full_name: str, organization_name: str) -> tuple[str, str, str]:
    """(subject, text, html) for the "your trial has expired" email. A plain link to the plans page."""
    link = frontend_url(PLANS_PATH)
    subject = "Your Rooman Billing free trial has expired"
    text = (
        f"Hello {full_name},\n\n"
        f"Your free trial of Rooman Billing for \"{organization_name}\" has expired.\n"
        "Your existing data is safe. To continue making changes, please choose a plan.\n\n"
        f"View Plans: {link}\n\n"
        "Thank you for trying Rooman Billing.\n\n"
        "— The Rooman Billing Team"
    )
    page = _card(
        "Your free trial has expired",
        f"Hello {full_name},",
        [
            f"Your free trial of Rooman Billing for <strong>{html.escape(organization_name)}</strong> has expired.",
            "Your existing data is safe. To continue making changes, please choose a plan.",
            "Thank you for trying Rooman Billing.",
        ],
        "View Plans",
        link,
    )
    return subject, text, page


def send_welcome_email(email: str, full_name: str, organization_name: str) -> bool:
    subject, text, page = welcome_email(full_name, organization_name)
    return send_email(to=email, subject=subject, text_body=text, html_body=page)


def _owners(db: Session, organization_id: str) -> List[tuple[str, str]]:
    rows = db.execute(
        select(User.full_name, User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == organization_id,
            Membership.status == MembershipStatus.ACTIVE,
            Membership.role == MemberRole.OWNER,
        )
        .order_by(User.email)
    ).all()
    return [(name or email, email) for name, email in rows if email]


# --- reminder job --------------------------------------------------------------------------------------


def send_due_trial_reminders(db: Session, now: Optional[datetime] = None) -> Dict[str, int]:
    """Send each trial's due reminder (best effort) and record it as handled first.

    An offset counts as due once the remaining time is at or below it. When several are due at once
    (the scheduler was away) only the most imminent one can be sent, and only if it is still timely:
    the larger offsets are recorded as skipped. Offsets are recorded BEFORE sending, so a reminder is
    never sent twice, even if the email then fails.
    """
    now = now or _utcnow()
    offsets = reminder_offsets()
    summary = {"sent": 0, "skipped_stale": 0, "failed": 0}
    if not offsets:
        return summary
    tolerance = max(0, int(settings.TRIAL_REMINDER_TOLERANCE_SECONDS))

    rows = db.execute(
        select(PlatformSubscription, Organization)
        .join(Organization, Organization.id == PlatformSubscription.organization_id)
        .where(
            PlatformSubscription.state == PlatformSubscriptionState.TRIALING.value,
            PlatformSubscription.trial_ends_at > now,
            Organization.status == OrganizationStatus.ACTIVE,
        )
    ).all()
    for listed, org in rows:
        try:
            # Claim the row (PostgreSQL: skip it if another scheduler process holds it) and read the
            # handled offsets fresh, so two processes can never both send the same reminder.
            sub = db.execute(
                select(PlatformSubscription)
                .where(PlatformSubscription.id == listed.id)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
            if sub is None:
                continue
            remaining = (_aware(sub.trial_ends_at) - now).total_seconds()
            handled = {int(o) for o in (sub.reminders_sent or [])}
            due = [o for o in offsets if o not in handled and remaining <= o * 60]
            if not due:
                db.rollback()  # release the claim
                continue
            imminent = min(due)
            timely = (imminent * 60 - remaining) <= tolerance
            sub.reminders_sent = sorted(handled | set(due), reverse=True)
            org_id, org_name = org.id, org.name
            db.commit()
            summary["skipped_stale"] += len(due) - (1 if timely else 0)
            if not timely:
                logger.info("Trial reminder (%s min) for organization %s skipped as stale", imminent, org_id)
                continue
            for full_name, email in _owners(db, org_id):
                try:
                    subject, text, page = reminder_email(full_name, org_name, imminent)
                    if send_email(to=email, subject=subject, text_body=text, html_body=page):
                        summary["sent"] += 1
                except Exception as exc:  # noqa: BLE001 - best effort: never raise out of the job
                    summary["failed"] += 1
                    logger.error("Trial reminder to %s for organization %s failed: %s", email, org_id, exc)
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Trial reminder processing failed")
    return summary


# --- expiry email --------------------------------------------------------------------------------------

# Recorded in `reminders_sent` once the "trial expired" email has been delivered. Offsets there mean
# "minutes remaining", so 0 is the moment of expiry; real offsets are always > 0 (reminder_offsets),
# so the marker can never collide with a reminder.
EXPIRY_EMAIL_SENT = 0


def _handled(sub: PlatformSubscription) -> set[int]:
    return {int(o) for o in (sub.reminders_sent or [])}


def send_trial_expiry_emails(db: Session, now: Optional[datetime] = None) -> Dict[str, int]:
    """Email each organization's owners once when its trial has expired.

    Unlike the pre-expiry reminders (recorded BEFORE sending, so at most once), delivery is recorded
    only AFTER the email helper confirmed it, so a failed send is retried on the next run. Duplicate
    scheduler processes are kept apart by claiming the row (`FOR UPDATE SKIP LOCKED`) for the whole
    send-and-record step. Only trials that ended within TRIAL_EXPIRY_EMAIL_WINDOW_MINUTES qualify.

    Several owners: delivery to at least one of them counts as delivered (retrying would mail the
    others twice). No owner, or every send failed: nothing is recorded and the next run tries again.
    """
    now = now or _utcnow()
    summary = {"sent": 0, "failed": 0}
    window = timedelta(minutes=max(0, int(settings.TRIAL_EXPIRY_EMAIL_WINDOW_MINUTES)))
    rows = db.execute(
        select(PlatformSubscription, Organization)
        .join(Organization, Organization.id == PlatformSubscription.organization_id)
        .where(
            PlatformSubscription.state == PlatformSubscriptionState.TRIALING.value,
            PlatformSubscription.trial_ends_at <= now,
            PlatformSubscription.trial_ends_at > now - window,
            Organization.status == OrganizationStatus.ACTIVE,
        )
    ).all()
    # Plain values: the session expires its objects at every commit/rollback below.
    candidates = [
        (sub.id, org.id, org.name) for sub, org in rows if EXPIRY_EMAIL_SENT not in _handled(sub)
    ]
    for sub_id, org_id, org_name in candidates:
        try:
            sub = db.execute(
                select(PlatformSubscription)
                .where(PlatformSubscription.id == sub_id)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
            if (
                sub is None  # another process holds it
                or sub.state != PlatformSubscriptionState.TRIALING.value
                or _aware(sub.trial_ends_at) > now
                or EXPIRY_EMAIL_SENT in _handled(sub)
            ):
                db.rollback()
                continue
            delivered = False
            for full_name, email in _owners(db, org_id):
                try:
                    subject, text, page = expiry_email(full_name, org_name)
                    if send_email(to=email, subject=subject, text_body=text, html_body=page):
                        delivered = True
                        summary["sent"] += 1
                    else:
                        summary["failed"] += 1
                except Exception as exc:  # noqa: BLE001 - best effort: never raise out of the job
                    summary["failed"] += 1
                    logger.error(
                        "Trial expiry email for organization %s failed (%s); will retry", org_id, type(exc).__name__
                    )
            if delivered:
                sub.reminders_sent = sorted(_handled(sub) | {EXPIRY_EMAIL_SENT}, reverse=True)
                db.commit()  # also releases the claim
            else:
                db.rollback()  # leave it retryable
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Trial expiry email processing failed")
    return summary
