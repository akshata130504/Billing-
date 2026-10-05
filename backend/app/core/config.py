import ipaddress
import json
import secrets
import warnings
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Union
from urllib.parse import parse_qs, quote, urlsplit

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

# sslmode values that authenticate the server certificate (libpq semantics).
VERIFIED_SSLMODES = {"verify-full", "verify-ca"}
_VALID_SSLMODES = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
# Default reverse-proxy ranges allowed to set X-Real-IP (RFC 1918, loopback, IPv6 ULA).
DEFAULT_TRUSTED_PROXIES = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "::1/128",
    "fc00::/7",
]
# Host headers always accepted so in-container / on-host probes keep working
# (compose healthcheck -> 127.0.0.1:8000, deploy-poll readiness -> 127.0.0.1:<port>).
INTERNAL_HOSTS = ["localhost", "127.0.0.1"]


def _split_list(v: Any) -> Any:
    """Accept a JSON array or a comma-separated string for list settings."""
    if isinstance(v, str):
        value = v.strip()
        if not value:
            return []
        if value.startswith("["):
            return json.loads(value)
        return [item.strip() for item in value.split(",") if item.strip()]
    return v


def is_private_db_host(host: Optional[str]) -> bool:
    """True for hosts only reachable on a private network: unix sockets, loopback, RFC 1918 /
    ULA addresses and single-label names (docker compose service names such as `db`)."""
    host = (host or "").strip().strip("[]").lower()
    if not host or host.startswith("/"):
        return True
    if host == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host
    return addr.is_private or addr.is_loopback


def normalize_origin(url: Optional[str]) -> Optional[str]:
    """"scheme://host[:port]" in lower case (default ports dropped), or None if `url` is not a bare
    http(s) origin (a path other than "/", a query, a fragment or credentials make it invalid)."""
    if not url or not url.strip():
        return None
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.path not in ("", "/") or parts.query or parts.fragment or parts.username or parts.password:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname.lower()
    if port is None or (parts.scheme == "https" and port == 443) or (parts.scheme == "http" and port == 80):
        return f"{parts.scheme}://{host}"
    return f"{parts.scheme}://{host}:{port}"


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

    # --- Platform administration (Rooman staff; separate from tenant auth) ------------------
    # Signing key for platform access tokens (core/platform_security.py). MUST differ from
    # SECRET_KEY. Empty = platform sign-in is disabled (the /platform/auth endpoints answer 503)
    # and nothing else changes. Generate one with `openssl rand -hex 32`; never commit it.
    PLATFORM_JWT_SECRET: str = ""
    PLATFORM_ACCESS_TOKEN_EXPIRE_MINUTES: int = 10
    PLATFORM_SESSION_IDLE_MINUTES: int = 30
    PLATFORM_SESSION_MAX_HOURS: int = 8
    PLATFORM_LOGIN_CHALLENGE_MINUTES: int = 5
    # Secure flag on platform cookies. None = on in production-like environments only.
    PLATFORM_COOKIE_SECURE: Optional[bool] = None
    # There is no separate platform origin: the platform console is served at /superadmin on the
    # one official application origin (the origin of FRONTEND_URL), next to the tenant app at
    # /admin. Platform API requests are accepted only from that origin (core/platform_boundary.py).
    # How long a step-up (fresh TOTP) authorises sensitive platform actions. Capped at 15.
    PLATFORM_STEP_UP_MINUTES: int = 15
    # Waiting period between scheduling an organization's deletion and the earliest (future,
    # separately approved) purge; cancellable by a Platform Administrator meanwhile.
    PLATFORM_DELETION_WAITING_DAYS: int = 30
    PASSWORD_MIN_LENGTH: int = 10
    # Requests per minute allowed on credential endpoints (login, signup, reset), per client IP.
    AUTH_RATE_LIMIT: str = "10/minute"
    # Unauthenticated hosted pages (/public/invoices, /public/quotes, /checkout/public).
    # The opaque token in the URL is the only credential, so these are enumerable:
    # keep reads generous enough for a real customer refreshing a page, and writes tight.
    PUBLIC_RATE_LIMIT: str = "60/minute"
    PUBLIC_ACTION_RATE_LIMIT: str = "10/minute"
    # Razorpay webhook receiver, per source IP. Generous enough for Razorpay's own bursts and
    # retries; caps how fast an unauthenticated sender can fill webhook_events/audit_logs with
    # rejected-signature rows.
    WEBHOOK_RATE_LIMIT: str = "300/minute"
    # Distributed rate limiting storage URI (e.g. redis://redis:6379/0).
    # When empty or omitted, SlowAPI gracefully falls back to in-memory storage.
    REDIS_URL: str | None = None
    # Set to true once the app is served over HTTPS so cookies/links assume TLS.
    SECURE_COOKIES: bool = False

    # NoDecode stops pydantic-settings from JSON-decoding the raw env value so the
    # validator below can accept either a JSON array or a comma-separated list.
    ALLOWED_ORIGINS: Annotated[List[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # Host headers the API answers to (TrustedHostMiddleware). Empty = derive: "*" outside
    # production; in production the hostnames of FRONTEND_URL and ALLOWED_ORIGINS. localhost
    # and 127.0.0.1 are always accepted for internal health probes. "*" is refused in production.
    ALLOWED_HOSTS: Annotated[List[str], NoDecode] = []
    # CIDRs of reverse proxies whose X-Real-IP header is trusted (see api/deps.client_ip).
    # Default: private + loopback ranges (our nginx container on the compose network).
    TRUSTED_PROXIES: Annotated[List[str], NoDecode] = list(DEFAULT_TRUSTED_PROXIES)

    @field_validator("ALLOWED_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        return _split_list(v)

    @field_validator("TRUSTED_PROXIES", mode="before")
    @classmethod
    def assemble_trusted_proxies(cls, v: Union[str, List[str]]) -> List[str]:
        items = _split_list(v)
        for item in items:
            ipaddress.ip_network(item, strict=False)  # ValueError on garbage -> startup fails
        return items

    @property
    def trusted_proxy_networks(self) -> List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]:
        return [ipaddress.ip_network(item, strict=False) for item in self.TRUSTED_PROXIES]

    @property
    def effective_allowed_hosts(self) -> List[str]:
        hosts = [h.strip().lower() for h in self.ALLOWED_HOSTS if h.strip()]
        if not hosts:
            if not self.is_production:
                return ["*"]
            for url in [self.FRONTEND_URL, *self.ALLOWED_ORIGINS]:
                host = urlsplit(url).hostname if url else None
                if host and host not in hosts:
                    hosts.append(host.lower())
        if "*" in hosts:
            return ["*"]
        for internal in INTERNAL_HOSTS:
            if internal not in hosts:
                hosts.append(internal)
        return hosts

    # --- Encryption of secrets at rest ------------------------------------------------
    # Keyring for integration credentials / TOTP seeds (see core/encryption.py). Comma or
    # JSON list of "<key_id>:<urlsafe-base64 32-byte Fernet key>"; the FIRST entry encrypts,
    # every entry (plus the legacy SECRET_KEY-derived key) decrypts. Empty = legacy
    # behaviour (single key derived from SECRET_KEY). Generate a key with
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEYS: Annotated[List[str], NoDecode] = []
    # Keep decrypting ciphertext written with the SECRET_KEY-derived key. Turn off only
    # after `python -m backend.app.core.encryption rotate` has re-encrypted everything.
    ENCRYPTION_LEGACY_SECRET_KEY_FALLBACK: bool = True

    @field_validator("ENCRYPTION_KEYS", mode="before")
    @classmethod
    def assemble_encryption_keys(cls, v: Union[str, List[str]]) -> List[str]:
        items = _split_list(v)
        if items:
            # Fail fast on malformed keys (message never echoes key material).
            from cryptography.fernet import Fernet

            seen = set()
            for index, entry in enumerate(items):
                key_id, _, key = entry.partition(":") if ":" in entry else (f"k{index + 1}", "", entry)
                key_id = key_id.strip()
                if not key_id or key_id in seen:
                    raise ValueError(f"ENCRYPTION_KEYS: missing or duplicate key id at position {index + 1}")
                seen.add(key_id)
                try:
                    Fernet(key.strip().encode("utf-8"))
                except Exception:
                    raise ValueError(
                        f"ENCRYPTION_KEYS: key {key_id!r} is not a valid Fernet key (32 url-safe base64 bytes)"
                    ) from None
        return items

    # --- Alerting -------------------------------------------------------------------------
    # Incoming-webhook URL (Slack / Mattermost / Teams / Discord+/slack) receiving
    # {"text": "..."} alerts from the app (core/alerts.py) and from deploy/*.sh. Empty = off.
    ALERT_WEBHOOK_URL: str = ""
    # The same event key alerts at most once per this many seconds per process.
    ALERT_DEDUP_SECONDS: int = 900
    ALERT_TIMEOUT_SECONDS: float = 5.0

    # --- PostgreSQL Database -------------------------------------------------
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "rooman_billing"
    # Least-privilege runtime role (APP_POSTGRES_USER / APP_POSTGRES_PASSWORD).
    # When set, the runtime application connects as this role. Unset = connects as POSTGRES_USER.
    APP_POSTGRES_USER: str | None = None
    APP_POSTGRES_PASSWORD: str | None = None
    DATABASE_URL: str | None = None
    # Optional separate owner/migration credentials (least privilege, docs/database-security.md).
    # Alembic and the container entrypoint's migration step use these; the running app uses
    # the runtime POSTGRES_USER / DATABASE_URL. Unset = migrations use the runtime credentials.
    MIGRATION_DATABASE_URL: str | None = None
    MIGRATION_POSTGRES_USER: str | None = None
    MIGRATION_POSTGRES_PASSWORD: str | None = None
    # TLS to PostgreSQL (libpq semantics). Unset = libpq default ("prefer"). Use verify-full
    # (with POSTGRES_SSLROOTCERT) for any database reached over a network you do not control.
    # Production refuses a non-private DB host without verify-full/verify-ca unless
    # POSTGRES_REQUIRE_VERIFIED_TLS=false (then it only warns).
    POSTGRES_SSLMODE: str | None = None
    POSTGRES_SSLROOTCERT: str | None = None
    POSTGRES_SSLCERT: str | None = None
    POSTGRES_SSLKEY: str | None = None
    POSTGRES_REQUIRE_VERIFIED_TLS: bool = True
    # Per process. The prod stack runs the API (several gunicorn workers), the scheduler and
    # migrations against one PostgreSQL with max_connections=100, so keep
    # (workers x (pool + overflow)) + scheduler comfortably below that.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5

    def _assemble_url(self, user: str, password: str) -> str:
        return (
            f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        """Runtime (application) connection URL."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        runtime_user = self.APP_POSTGRES_USER or self.POSTGRES_USER
        runtime_password = self.APP_POSTGRES_PASSWORD if self.APP_POSTGRES_USER else self.POSTGRES_PASSWORD
        return self._assemble_url(runtime_user, runtime_password)

    @property
    def migration_database_url(self) -> str:
        """Owner connection URL used by Alembic; falls back to the runtime URL when unset."""
        if self.MIGRATION_DATABASE_URL:
            return self.MIGRATION_DATABASE_URL
        if self.MIGRATION_POSTGRES_USER:
            if self.DATABASE_URL:
                # Same host/db/options as the runtime DATABASE_URL, owner credentials.
                from sqlalchemy.engine import make_url

                return (
                    make_url(self.DATABASE_URL)
                    .set(username=self.MIGRATION_POSTGRES_USER, password=self.MIGRATION_POSTGRES_PASSWORD or "")
                    .render_as_string(hide_password=False)
                )
            return self._assemble_url(self.MIGRATION_POSTGRES_USER, self.MIGRATION_POSTGRES_PASSWORD or "")
        # When APP_POSTGRES_USER is set and differs from POSTGRES_USER, POSTGRES_USER is the migration/owner role
        if self.APP_POSTGRES_USER and self.POSTGRES_USER and self.POSTGRES_USER != self.APP_POSTGRES_USER:
            return self._assemble_url(self.POSTGRES_USER, self.POSTGRES_PASSWORD)
        return self.sync_database_url

    def db_connect_args(self, url: Optional[str] = None) -> Dict[str, Any]:
        """DBAPI connect() keyword arguments for `url` (default: the runtime URL).

        PostgreSQL: pins the session to UTC and adds the POSTGRES_SSL* options when set.
        Options already present in the URL query string (?sslmode=...) still apply.
        """
        url = url or self.sync_database_url
        if url.startswith("sqlite"):
            return {"check_same_thread": False}
        # Pin the session to UTC so timestamptz values come back in UTC (API renders "...Z")
        # and SQL-side date/time comparisons don't depend on the database server's timezone.
        args: Dict[str, Any] = {"options": "-c timezone=UTC"}
        for key, value in (
            ("sslmode", self.POSTGRES_SSLMODE),
            ("sslrootcert", self.POSTGRES_SSLROOTCERT),
            ("sslcert", self.POSTGRES_SSLCERT),
            ("sslkey", self.POSTGRES_SSLKEY),
        ):
            if value and value.strip():
                args[key] = value.strip()
        return args

    def effective_sslmode(self, url: Optional[str] = None) -> Optional[str]:
        url = url or self.sync_database_url
        if self.POSTGRES_SSLMODE and self.POSTGRES_SSLMODE.strip():
            return self.POSTGRES_SSLMODE.strip().lower()
        values = parse_qs(urlsplit(url).query).get("sslmode")
        return values[-1].strip().lower() if values else None

    @staticmethod
    def db_host(url: str) -> Optional[str]:
        parts = urlsplit(url)
        if parts.hostname:
            return parts.hostname
        hosts = parse_qs(parts.query).get("host")
        return hosts[-1] if hosts else None

    # --- Payments: Razorpay ----------------------------------------------------
    # Leave empty to run without an online gateway (manual/offline payments only).
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    @property
    def razorpay_enabled(self) -> bool:
        return bool(self.RAZORPAY_KEY_ID and self.RAZORPAY_KEY_SECRET)

    # --- Email (SMTP) -------------------------------------------------------------
    # Leave SMTP_HOST empty to disable outbound email (development only: production refuses
    # to start without it). Password-reset links are never returned in API responses; in
    # development an invitation link for a brand-new user is shown to the inviting admin.
    # These platform settings are used for every authentication email (signup codes, resets,
    # team invitations) - never an organization's own SMTP integration.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    # Per-step (connect/STARTTLS/login/send) and whole-conversation SMTP time limits. The total
    # must stay well under the gunicorn worker timeout (60s) and the proxy read timeout (65s),
    # otherwise an unreachable mail server turns into a 502 from nginx instead of a clear error.
    SMTP_TIMEOUT_SECONDS: float = 10.0
    SMTP_TOTAL_TIMEOUT_SECONDS: float = 25.0
    EMAIL_FROM_ADDRESS: str = "billing@example.com"
    EMAIL_FROM_NAME: str = "Rooman Billing"

    @property
    def email_enabled(self) -> bool:
        return bool(self.SMTP_HOST)

    # --- Background scheduler ---------------------------------------------------------
    # Runs renewals, overdue marking and dunning reminders in-process. Enable on exactly
    # one backend instance when running several replicas.
    # Defaults to OFF so that only the dedicated `scheduler` service in
    # docker-compose.prod.yml runs jobs. Dunning retries and trial conversions charge through
    # the payment gateway adapter (they no longer mark payments paid on their own).
    SCHEDULER_ENABLED: bool = False
    SCHEDULER_INTERVAL_MINUTES: int = 15
    DUNNING_REMINDER_INTERVAL_DAYS: int = 3
    DUNNING_MAX_REMINDERS: int = 3

    # --- AI / Roomi Assistant -----------------------------------------------------------
    # Optional external LLM integration (Google Gemini). When omitted, Roomi operates
    # purely in deterministic in-house knowledge mode.
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TIMEOUT_SECONDS: float = 10.0

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

    @property
    def platform_auth_enabled(self) -> bool:
        return bool((self.PLATFORM_JWT_SECRET or "").strip()) and bool(self.platform_origin)

    @property
    def platform_origin(self) -> Optional[str]:
        """The one browser origin the platform console (/superadmin) is served from: the official
        application origin, i.e. the normalised origin of FRONTEND_URL - the same origin as the
        tenant app (/admin). None when FRONTEND_URL is not a bare origin."""
        return normalize_origin(self.FRONTEND_URL)

    @property
    def platform_cookie_secure(self) -> bool:
        if self.PLATFORM_COOKIE_SECURE is not None:
            return self.PLATFORM_COOKIE_SECURE
        return self.is_production

    @model_validator(mode="after")
    def validate_platform_settings(self) -> "Settings":
        """A configured platform key must be strong and distinct from the tenant key (any env).

        Unset is allowed everywhere: platform sign-in is simply disabled.
        """
        secret = (self.PLATFORM_JWT_SECRET or "").strip()
        if secret:
            origin = self.platform_origin
            if origin is None:
                raise ValueError(
                    "FRONTEND_URL must be a bare origin like https://billing.example.com (no path) when "
                    "PLATFORM_JWT_SECRET is set: the platform console is served at /superadmin on that origin"
                )
            if self.is_production and not origin.startswith("https://"):
                raise ValueError("FRONTEND_URL must be an https:// origin in production when PLATFORM_JWT_SECRET is set")
            if self.is_production and self.PLATFORM_COOKIE_SECURE is False:
                raise ValueError("PLATFORM_COOKIE_SECURE cannot be disabled in production")
            if origin.startswith("https://") and self.PLATFORM_COOKIE_SECURE is False:
                raise ValueError("PLATFORM_COOKIE_SECURE cannot be disabled for an https:// application origin")
            weak = (
                len(secret) < 32
                or len(set(secret)) < 8
                or secret in _INSECURE_SECRET_KEYS
                or any(p in secret.lower() for p in ("replace", "change-this", "example", "your-", "secret-key"))
            )
            if weak:
                raise ValueError(
                    "PLATFORM_JWT_SECRET must be a random string of at least 32 characters, not a placeholder"
                )
            if secret == (self.SECRET_KEY or "").strip():
                raise ValueError("PLATFORM_JWT_SECRET must differ from SECRET_KEY")
        for name, low, high in (
            ("PLATFORM_ACCESS_TOKEN_EXPIRE_MINUTES", 1, 60),
            ("PLATFORM_SESSION_IDLE_MINUTES", 5, 240),
            ("PLATFORM_SESSION_MAX_HOURS", 1, 24),
            ("PLATFORM_LOGIN_CHALLENGE_MINUTES", 1, 15),
            ("PLATFORM_STEP_UP_MINUTES", 1, 15),
            ("PLATFORM_DELETION_WAITING_DAYS", 7, 365),
        ):
            value = getattr(self, name)
            if not low <= value <= high:
                raise ValueError(f"{name} must be between {low} and {high}")
        return self

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
            if not self.DATABASE_URL:
                if not self.APP_POSTGRES_USER:
                    problems.append(
                        "APP_POSTGRES_USER must be set in production to enforce least privilege (deploy/db-least-privilege.sh)"
                    )
                elif self.APP_POSTGRES_USER == self.POSTGRES_USER:
                    problems.append("APP_POSTGRES_USER must differ from POSTGRES_USER (least-privilege runtime role)")
                elif len(self.APP_POSTGRES_PASSWORD or "") < 16:
                    problems.append("APP_POSTGRES_PASSWORD must be at least 16 characters")
            elif self.MIGRATION_POSTGRES_USER:
                from sqlalchemy.engine import make_url
                runtime_user = make_url(self.DATABASE_URL).username
                if runtime_user and runtime_user == self.MIGRATION_POSTGRES_USER:
                    problems.append("DATABASE_URL runtime user must differ from MIGRATION_POSTGRES_USER")
            if any(o.startswith(("http://localhost", "http://127.0.0.1")) for o in self.ALLOWED_ORIGINS):
                problems.append("ALLOWED_ORIGINS must not include localhost or 127.0.0.1")
            if not (self.SMTP_HOST or "").strip():
                # Not fatal: refusing to boot took the WHOLE API down (nginx 502 on every request)
                # just because email was unset. Email-dependent actions (signup codes, invitations,
                # password resets) fail with a clear 503/notice instead; nothing leaks a link.
                import logging

                logging.getLogger("rooman_billing").critical(
                    "SMTP_HOST is not set in %s: signup verification codes, invitations and password "
                    "resets cannot be emailed until SMTP_* is configured", self.ENVIRONMENT
                )
            if "*" in self.ALLOWED_ORIGINS:
                problems.append("ALLOWED_ORIGINS must not contain '*' (the API allows credentials)")
            elif any(not o.startswith("https://") for o in self.ALLOWED_ORIGINS):
                problems.append("ALLOWED_ORIGINS must only contain https:// origins")
            if not (self.FRONTEND_URL or "").strip().startswith("https://"):
                problems.append("FRONTEND_URL must be an https:// URL")
            if any(h.strip() == "*" for h in self.ALLOWED_HOSTS):
                problems.append("ALLOWED_HOSTS must list hostnames explicitly, not '*'")
            elif self.effective_allowed_hosts == list(INTERNAL_HOSTS):
                problems.append("ALLOWED_HOSTS must be set (or derivable from FRONTEND_URL)")
            if self.razorpay_enabled and not (self.RAZORPAY_WEBHOOK_SECRET or "").strip():
                # Without it every webhook is rejected, so payments whose customer closes the
                # browser before /verify (and refunds, disputes...) are never recorded.
                problems.append("RAZORPAY_WEBHOOK_SECRET must be set when RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET are set")
            problems.extend(self._database_tls_problems())
            if problems:
                raise ValueError(
                    "Refusing to start in %s with insecure configuration: %s"
                    % (self.ENVIRONMENT, "; ".join(problems))
                )
        return self

    def _database_tls_problems(self) -> List[str]:
        """Remote (non-private) database hosts must authenticate the server certificate."""
        problems: List[str] = []
        seen = set()
        for label, url in (
            ("DATABASE_URL", self.sync_database_url),
            ("MIGRATION_DATABASE_URL", self.migration_database_url),
        ):
            if url.startswith("sqlite") or url in seen:
                continue
            seen.add(url)
            host = self.db_host(url)
            if is_private_db_host(host) or self.effective_sslmode(url) in VERIFIED_SSLMODES:
                continue
            message = (
                f"{label} host {host!r} is not on a private network: set POSTGRES_SSLMODE=verify-full "
                "(and POSTGRES_SSLROOTCERT) so the connection is encrypted and the server authenticated"
            )
            if self.POSTGRES_REQUIRE_VERIFIED_TLS:
                problems.append(message)
            else:
                warnings.warn(message + " (POSTGRES_REQUIRE_VERIFIED_TLS=false: continuing)", RuntimeWarning, stacklevel=2)
        return problems

    @field_validator("POSTGRES_SSLMODE", mode="after")
    @classmethod
    def validate_sslmode(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        if v.strip().lower() not in _VALID_SSLMODES:
            raise ValueError(f"POSTGRES_SSLMODE must be one of {sorted(_VALID_SSLMODES)}")
        return v.strip().lower()

    def __repr__(self) -> str:
        """Mask sensitive secrets so logging or printing Settings never leaks credentials."""
        sensitive_fields = {
            "SECRET_KEY",
            "PLATFORM_JWT_SECRET",
            "POSTGRES_PASSWORD",
            "RAZORPAY_KEY_SECRET",
            "RAZORPAY_WEBHOOK_SECRET",
            "SMTP_PASSWORD",
            "GEMINI_API_KEY",
            "REDIS_URL",
            "DATABASE_URL",
            "MIGRATION_DATABASE_URL",
            "MIGRATION_POSTGRES_PASSWORD",
            "ENCRYPTION_KEYS",
            "ALERT_WEBHOOK_URL",
            "SENTRY_DSN",
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
        # Validation errors must never echo raw values (SECRET_KEY, ENCRYPTION_KEYS, DB URLs)
        # into startup logs.
        hide_input_in_errors=True,
    )


settings = Settings()
