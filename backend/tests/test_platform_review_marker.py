"""Durable review markers on checkout attempts (migration 0041) and the console review queue.

Every finding that must not be applied automatically goes through platform_payment_service._review, which now
stores it on the checkout attempt. Razorpay is never called (Stage 4 / reconciliation fakes).
"""
from datetime import timedelta, timezone

from backend.app.core.tenant_context import system_context
from backend.app.models import PlatformWebhookEvent
from backend.app.models.platform import PlatformRole
from backend.app.services import platform_payment_service as payments, platform_reconciliation_service as recon
from backend.tests.test_platform_console import Staff
from backend.tests.test_platform_payment_verification import _attempt, _pay, _start, _verify, _webhook
from backend.tests.test_platform_reconciliation import isolated, rzp  # noqa: F401  (fixtures)

UTC = timezone.utc


def _paid_checkout(client, db, tenant, rzp, **state):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body, **state)
    rzp.invoices[sid] = pid
    return body, sid, pid


def _code(r):
    return r.json()["error"]["code"]


# --- each review path is persisted ---------------------------------------------------------------------------


def test_a_callback_review_is_stored_on_the_checkout(client, db, tenant, rzp):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp, amount=100)  # captured, wrong amount
    r = _verify(client, tenant, pid, sid)
    assert r.status_code == 409 and _code(r) == "PAYMENT_NEEDS_REVIEW"
    attempt = _attempt(db, body["checkout_attempt_id"])
    assert attempt.review_reason == "mismatch: captured payment amount or currency differs from the checkout"
    assert attempt.review_flagged_at is not None and attempt.status == "created"  # flagged, nothing applied


def test_a_reconciliation_mismatch_is_stored_on_the_checkout(client, db, tenant, rzp):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp, currency="USD")
    assert recon.run_reconciliation(db).get("checkout_mismatch") == 1
    attempt = _attempt(db, body["checkout_attempt_id"])
    assert attempt.review_reason.startswith("mismatch: captured payment amount or currency differs")
    assert attempt.review_flagged_at is not None


def test_a_webhook_review_is_stored_on_the_checkout(client, db, tenant, rzp):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp, notes={"checkout_attempt_id": "someone-else"})
    assert _webhook(client, "subscription.charged", sid, pid).json()["status"] == "needs_review"
    assert _attempt(db, body["checkout_attempt_id"]).review_reason == "mismatch: subscription does not belong to this checkout"


def test_repeated_flagging_keeps_the_first_time_and_the_latest_reason(client, db, tenant, rzp):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp, amount=100)
    recon.run_reconciliation(db)
    first = _attempt(db, body["checkout_attempt_id"])
    flagged_at, reason = first.review_flagged_at, first.review_reason
    recon.run_reconciliation(db)  # the same finding again: nothing moves
    again = _attempt(db, body["checkout_attempt_id"])
    assert (again.review_flagged_at, again.review_reason) == (flagged_at, reason)
    # A different finding later: the reason follows the latest, the first-flag time does not move.
    rzp.subs[sid]["notes"] = {"checkout_attempt_id": "someone-else"}
    recon.run_reconciliation(db)
    later = _attempt(db, body["checkout_attempt_id"])
    assert later.review_reason == "mismatch: subscription does not belong to this checkout"
    assert later.review_flagged_at == flagged_at


def test_a_clean_payment_is_never_flagged(client, db, tenant, rzp):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp)
    assert _verify(client, tenant, pid, sid).json()["status"] == "active"
    attempt = _attempt(db, body["checkout_attempt_id"])
    assert attempt.review_reason is None and attempt.review_flagged_at is None


def test_review_reason_text_is_one_bounded_line():
    text = payments.review_reason_text("needs_review", "activation refused:\nline two\t\x00 " + "x" * 400)
    assert "\n" not in text and "\t" not in text and "\x00" not in text
    assert len(text) <= payments.REVIEW_REASON_MAX and text.startswith("needs_review: activation refused: line two")


def test_stored_reasons_carry_no_secrets(client, db, tenant, rzp):
    from backend.tests.test_platform_checkout import KEY_ID, SECRET
    from backend.tests.test_platform_payment_verification import WEBHOOK_SECRET

    body, sid, pid = _paid_checkout(client, db, tenant, rzp, amount=100)
    _verify(client, tenant, pid, sid)
    reason = _attempt(db, body["checkout_attempt_id"]).review_reason
    for value in (SECRET, WEBHOOK_SECRET, KEY_ID, tenant.owner.email, tenant.owner.full_name, pid, sid):
        assert value not in reason


# --- the console queue ----------------------------------------------------------------------------------------


def test_the_review_queue_lists_stored_reviews_once_with_reason_and_time(client, db, tenant, rzp):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp, notes={"checkout_attempt_id": "someone-else"})
    _webhook(client, "subscription.charged", sid, pid)  # flags the checkout AND writes a needs_review ledger row
    # A ledger review with no flagged checkout (e.g. recorded before 0041) is still listed on its own.
    with system_context():
        from datetime import datetime

        db.add(PlatformWebhookEvent(provider="razorpay", event_id="evt_legacy", event_type="subscription.charged",
                                    mode="test", provider_subscription_id="sub_legacy", status="needs_review",
                                    outcome="mismatch", received_at=datetime.now(UTC) - timedelta(days=1)))
        db.commit()
    queue = Staff(db, PlatformRole.PLATFORM_OPERATIONS).get("/billing/review-queue").json()
    assert queue["untracked_sources"] == []  # nothing is only logged any more
    sources = [(i["source"], i["provider_subscription_id"]) for i in queue["items"]]
    assert sources == [("checkout_review", sid), ("webhook_needs_review", "sub_legacy")]  # no duplicate for sid
    item = queue["items"][0]
    assert item["review_reason"] == "mismatch: subscription does not belong to this checkout"
    assert item["flagged_at"] and item["checkout_attempt_id"] == body["checkout_attempt_id"]
    assert item["checkout_status"] == "created" and item["outcome"] == "mismatch"


def test_flagged_checkouts_show_their_reason_in_the_checkout_list(client, db, tenant, rzp):
    body, sid, pid = _paid_checkout(client, db, tenant, rzp, amount=100)
    _verify(client, tenant, pid, sid)
    [row] = Staff(db, PlatformRole.PLATFORM_OPERATIONS).get("/billing/checkout-attempts").json()["items"]
    assert row["review_reason"].startswith("mismatch:") and row["review_flagged_at"]


def test_the_review_queue_stays_operations_and_administrator_only(db):
    assert Staff(db, PlatformRole.PLATFORM_SUPPORT).get("/billing/review-queue").status_code == 403
