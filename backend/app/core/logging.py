import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

from backend.app.core.config import settings
from backend.app.core.redaction import redact_text

correlation_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)


class SensitiveDataFilter(logging.Filter):
    """Scrubs passwords, tokens, OTPs, API keys, card numbers and Authorization headers.

    The message is rendered first (msg % args) so secrets passed as %-format arguments are
    scrubbed too, and exception tracebacks are pre-formatted and scrubbed as well.
    Patterns live in core/redaction.py (shared with core/alerts.py).
    """

    _formatter = logging.Formatter()

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # malformed format args: keep the raw template
            message = str(record.msg)
        record.msg = redact_text(message)
        record.args = None
        if record.exc_info and not record.exc_text:
            try:
                record.exc_text = self._formatter.formatException(record.exc_info)
            except Exception:  # pragma: no cover
                record.exc_text = None
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)
        return True


class CorrelationIdFilter(logging.Filter):
    """Injects current correlation/request ID from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = correlation_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, friendly to log shippers (Loki, CloudWatch, Datadog)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_text:  # pre-formatted and redacted by SensitiveDataFilter
            payload["exception"] = record.exc_text
        elif record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key in ("request_id", "path", "method", "status_code", "duration_ms"):
            if hasattr(record, key) and getattr(record, key) is not None:
                payload[key] = getattr(record, key)
        return json.dumps(payload, default=str)


def setup_logging() -> logging.Logger:
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(CorrelationIdFilter())
    handler.addFilter(SensitiveDataFilter())
    if settings.LOG_JSON:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    app_logger = logging.getLogger("rooman_billing")
    app_logger.info(
        "Structured logging initialized for %s in %s environment", settings.PROJECT_NAME, settings.ENVIRONMENT
    )
    return app_logger


logger = setup_logging()
