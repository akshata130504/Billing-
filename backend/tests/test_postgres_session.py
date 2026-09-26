"""PostgreSQL-only: the connection session must run in UTC so API timestamps render with 'Z'
regardless of the database server's configured timezone."""
import pytest
from sqlalchemy import text

from backend.app.core.database import engine

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="needs PostgreSQL")


def test_postgres_session_timezone_is_utc():
    with engine.connect() as conn:
        assert conn.execute(text("SHOW timezone")).scalar() == "UTC"
