"""Operational alerts to an incoming webhook (Slack / Mattermost / Teams / Discord+/slack).

    from backend.app.core.alerts import send_alert
    send_alert("payment.webhook_failed", "Razorpay webhook processing failed",
               {"event_id": evt_id, "error": str(exc)}, severity="error")

Guarantees:

* **Never raises** into the caller and **never blocks** it: the HTTP POST runs on a daemon
  worker thread with a short timeout (ALERT_TIMEOUT_SECONDS); if the queue is full the alert
  is dropped (and logged).
* **Deduplicated** per key (``dedup_key`` or ``event``): at most one alert per
  ALERT_DEDUP_SECONDS per process; the next alert reports how many were suppressed.
* **Redacted**: summary and details go through core/redaction.py (passwords, OTPs, tokens,
  API keys, Authorization headers, Razorpay secrets, card numbers, URL credentials). Callers
  should still pass masked identifiers (``mask_email``) rather than raw PII.
* Payload shape matches deploy/alert.sh and deploy/backup.sh: ``{"text": "..."}``.
* With ALERT_WEBHOOK_URL empty the alert is only logged (WARNING/ERROR).
"""
from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
from typing import Any, Dict, Mapping, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.redaction import mask_email, redact_data, redact_text

SEVERITIES = ("info", "warning", "error", "critical")
_MAX_TEXT = 3500
_QUEUE_MAX = 100

_lock = threading.Lock()
_last_sent: Dict[str, float] = {}
_suppressed: Dict[str, int] = {}
_queue: "queue.Queue[tuple[str, str]]" = queue.Queue(maxsize=_QUEUE_MAX)
_worker: Optional[threading.Thread] = None
_worker_pid: Optional[int] = None


def _post(url: str, payload: Dict[str, Any], timeout: float) -> None:
    """Deliver one alert (replaced in tests). Raises on HTTP/network errors."""
    import httpx

    response = httpx.post(url, json=payload, timeout=timeout)
    response.raise_for_status()


def _run_worker() -> None:
    while True:
        url, text = _queue.get()
        try:
            _post(url, {"text": text}, float(settings.ALERT_TIMEOUT_SECONDS or 5.0))
        except Exception as exc:  # never propagate; the URL itself is secret, so don't log it
            logger.warning("Alert webhook delivery failed (%s)", type(exc).__name__)
        finally:
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker, _worker_pid
    pid = os.getpid()
    if _worker is not None and _worker.is_alive() and _worker_pid == pid:
        return
    # (Re)start after a fork (gunicorn workers) or if the thread died.
    _worker = threading.Thread(target=_run_worker, name="alert-webhook", daemon=True)
    _worker_pid = pid
    _worker.start()


def _format(event: str, summary: str, details: Optional[Mapping[str, Any]], severity: str, suppressed: int) -> str:
    env = settings.ENVIRONMENT or "unknown"
    host = socket.gethostname()
    lines = [f"[{settings.PROJECT_NAME} {env} @ {host}] {severity.upper()} {event}: {redact_text(summary)}"]
    if details:
        safe = redact_data(dict(details))
        try:
            rendered = json.dumps(safe, default=str, sort_keys=True)
        except Exception:
            rendered = redact_text(str(safe))
        lines.append(f"details: {rendered}")
    if suppressed:
        lines.append(f"({suppressed} similar alert(s) suppressed since the last one)")
    text = "\n".join(lines)
    return text if len(text) <= _MAX_TEXT else text[: _MAX_TEXT - 3] + "..."


def send_alert(
    event: str,
    summary: str,
    details: Optional[Mapping[str, Any]] = None,
    severity: str = "error",
    *,
    dedup_key: Optional[str] = None,
) -> bool:
    """Queue an alert. Returns True if it was queued for delivery, False if suppressed by
    deduplication, not configured (logged only) or dropped. Never raises."""
    try:
        severity = severity if severity in SEVERITIES else "error"
        key = dedup_key or event
        window = max(0, int(settings.ALERT_DEDUP_SECONDS or 0))
        now = time.monotonic()
        with _lock:
            last = _last_sent.get(key)
            if last is not None and window and now - last < window:
                _suppressed[key] = _suppressed.get(key, 0) + 1
                return False
            _last_sent[key] = now
            suppressed = _suppressed.pop(key, 0)
            if len(_last_sent) > 5000:  # bound memory for high-cardinality keys
                cutoff = now - window
                for k in [k for k, t in _last_sent.items() if t < cutoff]:
                    _last_sent.pop(k, None)
        text = _format(event, summary, details, severity, suppressed)
        log = logger.error if severity in ("error", "critical") else logger.warning
        log("ALERT %s", text)
        url = (settings.ALERT_WEBHOOK_URL or "").strip()
        if not url:
            return False
        _ensure_worker()
        try:
            _queue.put_nowait((url, text))
        except queue.Full:
            logger.warning("Alert queue full; dropped alert %s", event)
            return False
        return True
    except Exception as exc:  # pragma: no cover - alerts must never break the caller
        try:
            logger.warning("send_alert failed internally (%s)", type(exc).__name__)
        except Exception:
            pass
        return False


def flush(timeout: float = 5.0) -> bool:
    """Wait until queued alerts are delivered (tests, graceful shutdown). True if drained."""
    deadline = time.monotonic() + timeout
    while _queue.unfinished_tasks and time.monotonic() < deadline:
        time.sleep(0.01)
    return not _queue.unfinished_tasks


def reset_alert_state() -> None:
    """Forget dedup history (tests)."""
    with _lock:
        _last_sent.clear()
        _suppressed.clear()


__all__ = ["SEVERITIES", "flush", "mask_email", "reset_alert_state", "send_alert"]
