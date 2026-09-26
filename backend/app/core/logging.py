import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

from backend.app.core.config import settings

import re

correlation_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)

_SENSITIVE_PATTERNS = [
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE), "Bearer [redacted]"),
    (re.compile(r"(['\"]?(?:password|passwd|secret|token)['\"]?\s*[:=]\s*)(?:'[^']+'|\"[^\"]+\"|[^\s,;]+)", re.IGNORECASE), r'\1"[redacted]"'),
    (re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE), "ghp_[redacted]"),
    (re.compile(r"AIza[a-zA-Z0-9_-]{20,}", re.IGNORECASE), "AIza[redacted]"),
    (re.compile(r"rzp_(test|live)_[a-zA-Z0-9]{10,}", re.IGNORECASE), r"rzp_\1_[redacted]"),
]


class SensitiveDataFilter(logging.Filter):
    """Scrubs passwords, tokens, API keys, and Authorization headers from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern, replacement in _SENSITIVE_PATTERNS:
                msg = pattern.sub(replacement, msg)
            record.msg = msg
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
        if record.exc_info:
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
