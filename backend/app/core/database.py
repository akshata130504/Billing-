from typing import Generator, Tuple, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.core.config import settings
from backend.app.core.logging import logger

database_url = settings.sync_database_url

# Configure connection pooling appropriately
engine_kwargs = {}
if database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(database_url, **engine_kwargs)
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
        logger.warning("Database healthcheck connection failed: %s", str(exc))
        return {
            "status": "disconnected",
            "dialect": engine.dialect.name,
            "error": str(exc),
        }
