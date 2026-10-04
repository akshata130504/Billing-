from typing import Any, Dict, Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.app.core.config import settings
from backend.app.core.logging import logger

database_url = settings.sync_database_url

# Configure connection pooling appropriately
engine_kwargs: Dict[str, Any] = {}
# SQLite: check_same_thread=False. PostgreSQL: "-c timezone=UTC" (sessions pinned to UTC so
# timestamptz values come back in UTC) plus POSTGRES_SSLMODE/SSLROOTCERT/SSLCERT/SSLKEY.
engine_kwargs["connect_args"] = settings.db_connect_args(database_url)
if not database_url.startswith("sqlite"):
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW

engine = create_engine(database_url, **engine_kwargs)

if database_url.startswith("sqlite"):
    # SQLite ignores foreign keys unless asked; keep behaviour close to PostgreSQL in tests.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fks(dbapi_connection, _record):  # pragma: no cover - trivial
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI Dependency for database session management."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health() -> Dict[str, Any]:
    """Verifies connection to the database without throwing uncaught exceptions."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "connected",
            "dialect": engine.dialect.name,
            "url_masked": str(engine.url).split("@")[-1] if "@" in str(engine.url) else str(engine.url),
        }
    except Exception as exc:
        # Log the driver error (may contain host names / usernames) but never return it to
        # unauthenticated callers of the health endpoints.
        logger.warning("Database healthcheck connection failed: %s", str(exc))
        return {
            "status": "disconnected",
            "dialect": engine.dialect.name,
            "error": "database unreachable",
        }
