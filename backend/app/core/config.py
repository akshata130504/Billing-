import json
import secrets
from pathlib import Path
from typing import Annotated, List, Union

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Resolve .env files relative to the repository layout instead of the current
# working directory so the backend behaves the same regardless of where
# uvicorn/pytest/alembic are launched from.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent

_INSECURE_SECRET_KEYS = {
    "",
    "phase0-development-secret-key-replace-in-production-12345",
    "change-this-insecure-secret-key-to-a-random-32-char-string-in-production",
    "changeme",
    "secret",
    "secretkey",
    "insecure",
    "admin",
    "password",
    "your-secret-key",
    "your-secret-key-here",
    "default-secret-key",
    "insecure-secret-key",
    "development-secret-key",
    "replace-in-production",
}



class Settings(BaseSettings):
    PROJECT_NAME: str = "Rooman Billing"
    ENVIRONMENT: str = "development"  # development | test | staging | production
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # Public URL of the frontend. Used to build links in emails (invites, password
    # resets, hosted invoice payment pages).
    FRONTEND_URL: str = "http://localhost:5173"

    # Local uploads directory
    UPLOAD_DIR: str = "backend/uploads"

    # --- Security -----------------------------------------------------------
    # In production this MUST be a long random string (e.g. `openssl rand -hex 32`).
    # Startup fails in production if it is missing or one of the known defaults.
    SECRET_KEY: str = "phase0-development-secret-key-replace-in-production-12345"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    INVITE_TOKEN_EXPIRE_HOURS: int = 72
    PASSWORD_RESET_EXPIRE_MINUTES: int = 60
    PASSWORD_MIN_LENGTH: int = 10
    # Requests per minute allowed on credential endpoints (login, signup, reset), per client IP.
    AUTH_RATE_LIMIT: str = "10/minute"
    # Unauthenticated hosted pages (/public/invoices, /public/quotes, /checkout/public).
    # The opaque token in the URL is the only credential, so these are enumerable:
    # keep reads generous enough for a real customer refreshing a page, and writes tight.
    PUBLIC_RATE_LIMIT: str = "60/minute"
    PUBLIC_ACTION_RATE_LIMIT: str = "10/minute"
    # Set to true once the app is served over HTTPS so cookies/links assume TLS.
    SECURE_COOKIES: bool = False

    # NoDecode stops pydantic-settings from JSON-decoding the raw env value so the
    # validator below can accept either a JSON array or a comma-separated list.
    ALLOWED_ORIGINS: Annotated[List[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            value = v.strip()
            if value.startswith("["):
                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return v

    # --- PostgreSQL Database -------------------------------------------------
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "rooman_billing"
    DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # --- Payments: Razorpay ----------------------------------------------------
    # Leave empty to run without an online gateway (manual/offline payments only).
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    @property
    def razorpay_enabled(self) -> bool:
        return bool(self.RAZORPAY_KEY_ID and self.RAZORPAY_KEY_SECRET)

    # --- Email (SMTP) -------------------------------------------------------------
    # Leave SMTP_HOST empty to disable outbound email. Invite / reset links are then
    # returned to the administrator in the API response so the flows still work.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    EMAIL_FROM_ADDRESS: str = "billing@example.com"
    EMAIL_FROM_NAME: str = "Rooman Billing"

    @property
    def email_enabled(self) -> bool:
        return bool(self.SMTP_HOST)

    # --- Background scheduler ---------------------------------------------------------
    # Runs renewals, overdue marking and dunning reminders in-process. Enable on exactly
    # one backend instance when running several replicas.
    # Defaults to OFF: dunning retries and trial conversion currently mark payments
    # successful without contacting a real gateway (see Rooman-Billing security audit).
    # Do not flip this to true until those paths are fixed and verified.
    SCHEDULER_ENABLED: bool = False
    SCHEDULER_INTERVAL_MINUTES: int = 15
    DUNNING_REMINDER_INTERVAL_DAYS: int = 3
    DUNNING_MAX_REMINDERS: int = 3

    # --- Observability ------------------------------------------------------------------
    LOG_JSON: bool = False
    # Error tracking. Entirely optional: leave SENTRY_DSN empty and no Sentry code
    # (or import) is executed at all. See backend/app/core/sentry.py for the PII scrubber.
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    @property
    def sentry_enabled(self) -> bool:
        return bool(self.SENTRY_DSN)

    @property
    def is_production(self) -> bool:
        env = (self.ENVIRONMENT or "").strip().lower()
        return env in {"production", "prod", "staging", "stage"}

    @model_validator(mode="after")
    def enforce_production_safety(self) -> "Settings":
        if self.is_production:
            problems = []
            secret = (self.SECRET_KEY or "").strip()
            is_weak_secret = (
                not secret
                or secret in _INSECURE_SECRET_KEYS
                or len(secret) < 32
                or len(set(secret)) < 8
                or any(
                    placeholder in secret.lower()
                    for placeholder in (
                        "replace-in-production",
                        "change-this",
                        "insecure-secret",
                        "your-secret-key",
                        "development-secret",
                    )
                )
            )
            if is_weak_secret:
                problems.append(
                    "SECRET_KEY must be a random string of at least 32 characters and cannot be a default or placeholder"
                )
            if self.DEBUG:
                problems.append("DEBUG must be false")
            if self.sync_database_url.startswith("sqlite"):
                problems.append("DATABASE_URL must point at PostgreSQL, not SQLite")
            if "postgres:postgres@" in self.sync_database_url:
                problems.append("database password must not be the default 'postgres'")
            if any(o.startswith("http://localhost") for o in self.ALLOWED_ORIGINS):
                problems.append("ALLOWED_ORIGINS must not include localhost")
            if problems:
                raise ValueError(
                    "Refusing to start in %s with insecure configuration: %s"
                    % (self.ENVIRONMENT, "; ".join(problems))
                )
        return self

    def __repr__(self) -> str:
        """Mask sensitive secrets so logging or printing Settings never leaks credentials."""
        sensitive_fields = {
            "SECRET_KEY",
            "POSTGRES_PASSWORD",
            "RAZORPAY_KEY_SECRET",
            "RAZORPAY_WEBHOOK_SECRET",
            "SMTP_PASSWORD",
        }
        parts = []
        for key, value in self.__dict__.items():
            if key in sensitive_fields and value:
                parts.append(f"{key}='***'")
            else:
                parts.append(f"{key}={value!r}")
        return f"{self.__class__.__name__}({', '.join(parts)})"

    def __str__(self) -> str:
        return self.__repr__()

    @staticmethod
    def generate_secret_key() -> str:
        return secrets.token_hex(32)

    # Later files take precedence: backend/.env overrides the repo-root .env.
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
