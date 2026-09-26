"""Tests for Alembic migrations to ensure schema consistency and rollback capability."""
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
import pytest


def test_alembic_migrations_upgrade_and_downgrade(tmp_path):
    """Verify that all migrations apply cleanly to a blank SQLite DB and downgrade cleanly."""
    test_db_file = tmp_path / "migration_test.sqlite3"
    test_db_url = f"sqlite:///{test_db_file.as_posix()}"

    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = repo_root / "backend" / "alembic.ini"
    assert alembic_ini_path.exists(), f"Missing alembic.ini at {alembic_ini_path}"

    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
    alembic_cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))

    # Upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Downgrade back to base
    command.downgrade(alembic_cfg, "base")

    # Re-upgrade to head to ensure repeatable application
    command.upgrade(alembic_cfg, "head")


# --------------------------------------------------------------------------- #
# PostgreSQL: native enum types created by migrations == Python enums in models
# --------------------------------------------------------------------------- #


def _postgres_test_url():
    url = os.environ.get("TEST_DATABASE_URL", "")
    return url if url.startswith("postgresql") else None


# Labels a legacy migration (d9f1a2b3c4e5) added that the ORM never writes (SQLAlchemy stores the
# enum *names*, e.g. "ACTIVE"). PostgreSQL cannot drop enum labels without rebuilding the type, so
# they are tolerated explicitly; any other extra label, and every missing label, still fails.
KNOWN_LEGACY_ENUM_LABELS = {
    "subscription_status": {
        "draft", "pending_activation", "active", "trialing", "past_due", "paused", "cancelled", "expired",
    },
}


@pytest.mark.skipif(_postgres_test_url() is None, reason="needs TEST_DATABASE_URL pointing at PostgreSQL")
def test_postgres_enums_match_python_enums():
    """After `alembic upgrade head`, every Postgres ENUM type must carry exactly the labels the
    models persist. A missing label means inserts of that value fail in production (while the
    SQLite-based suite, which stores enums as VARCHAR, passes)."""
    from sqlalchemy import Enum as SAEnum
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from backend.app.core.database import Base
    import backend.app.models  # noqa: F401  (register every model)

    base_url = make_url(_postgres_test_url())
    scratch_name = f"{base_url.database}_enumcheck"
    admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_name}"'))
        conn.execute(text(f'CREATE DATABASE "{scratch_name}"'))

    scratch_url = base_url.set(database=scratch_name)
    try:
        repo_root = Path(__file__).resolve().parents[2]
        cfg = Config(str(repo_root / "backend" / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", scratch_url.render_as_string(hide_password=False))
        cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
        command.upgrade(cfg, "head")

        engine = create_engine(scratch_url)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT t.typname, e.enumlabel FROM pg_type t "
                    "JOIN pg_enum e ON e.enumtypid = t.oid ORDER BY t.typname, e.enumsortorder"
                )
            ).all()
        engine.dispose()

        db_enums = {}
        for typname, label in rows:
            db_enums.setdefault(typname, set()).add(label)

        model_enums = {}
        for table in Base.metadata.tables.values():
            for column in table.columns:
                col_type = column.type
                if isinstance(col_type, SAEnum) and col_type.name and getattr(col_type, "native_enum", True):
                    model_enums.setdefault(col_type.name, set()).update(col_type.enums)

        problems = []
        for name, expected in sorted(model_enums.items()):
            actual = db_enums.get(name)
            if actual is None:
                problems.append(f"{name}: enum type missing in database (model expects {sorted(expected)})")
                continue
            missing = expected - actual
            if missing:
                problems.append(f"{name}: labels missing in database: {sorted(missing)}")
            extra = actual - expected - KNOWN_LEGACY_ENUM_LABELS.get(name, set())
            if extra:
                problems.append(f"{name}: labels in database but not in the Python enum: {sorted(extra)}")
        assert not problems, "Postgres enums drifted from Python enums:\n  " + "\n  ".join(problems)
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": scratch_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_name}"'))
        admin.dispose()


# --------------------------------------------------------------------------- #
# Model <-> migration drift (the programmatic equivalent of `alembic check`)
# --------------------------------------------------------------------------- #


def _alembic_config(url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    return cfg


def _metadata_diffs(engine):
    """Diffs autogenerate would emit for `engine` vs the models, with the same (default)
    comparison options backend/alembic/env.py uses for `alembic check`."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from backend.app.core.database import Base
    import backend.app.models  # noqa: F401  (register every model)

    with engine.connect() as conn:
        return compare_metadata(MigrationContext.configure(conn), Base.metadata)


def test_models_declare_no_duplicate_indexes():
    """Two indexes over the same column list on one table (e.g. an explicit named Index plus a
    column's index=True) double write cost and make `alembic check` drift-prone."""
    from backend.app.core.database import Base
    import backend.app.models  # noqa: F401

    duplicates = []
    for table in Base.metadata.sorted_tables:
        seen = {}
        for index in table.indexes:
            key = (tuple(c.name for c in index.columns), bool(index.unique))
            if key in seen:
                duplicates.append(f"{table.name}{list(key[0])}: {seen[key]} and {index.name}")
            seen[key] = index.name
    assert not duplicates, "Duplicate indexes declared in models:\n  " + "\n  ".join(duplicates)


def test_sqlite_migrated_schema_matches_models(tmp_path):
    """`alembic upgrade head` on a blank SQLite DB must leave nothing for autogenerate to do."""
    from sqlalchemy import create_engine

    url = f"sqlite:///{(tmp_path / 'drift_check.sqlite3').as_posix()}"
    command.upgrade(_alembic_config(url), "head")
    engine = create_engine(url)
    try:
        diffs = _metadata_diffs(engine)
    finally:
        engine.dispose()
    assert diffs == [], f"Models drifted from migrations (run `alembic check`): {diffs}"


@pytest.mark.skipif(_postgres_test_url() is None, reason="needs TEST_DATABASE_URL pointing at PostgreSQL")
def test_postgres_migrated_schema_matches_models():
    """`alembic check` on PostgreSQL: after `alembic upgrade head` into a scratch database the
    models and the migrated schema must match exactly (index names, columns, uniqueness...)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    base_url = make_url(_postgres_test_url())
    scratch_name = f"{base_url.database}_driftcheck"
    admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_name}"'))
        conn.execute(text(f'CREATE DATABASE "{scratch_name}"'))

    scratch_url = base_url.set(database=scratch_name)
    try:
        command.upgrade(_alembic_config(scratch_url.render_as_string(hide_password=False)), "head")
        engine = create_engine(scratch_url)
        try:
            diffs = _metadata_diffs(engine)
        finally:
            engine.dispose()
        assert diffs == [], f"Models drifted from migrations (run `alembic check`): {diffs}"
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": scratch_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_name}"'))
        admin.dispose()


@pytest.mark.skipif(_postgres_test_url() is None, reason="needs TEST_DATABASE_URL pointing at PostgreSQL")
def test_0023_drops_legacy_duplicate_integration_indexes_only_when_replaced():
    """Databases created before the models declared explicit index names carry auto-named
    duplicates on organization_integrations; 0023 must drop them (keeping the replacements)
    and leave the schema free of drift."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    base_url = make_url(_postgres_test_url())
    scratch_name = f"{base_url.database}_idx0023"
    admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_name}"'))
        conn.execute(text(f'CREATE DATABASE "{scratch_name}"'))
    scratch_url = base_url.set(database=scratch_name)
    cfg = _alembic_config(scratch_url.render_as_string(hide_password=False))
    engine = create_engine(scratch_url)
    try:
        command.upgrade(cfg, "b9c0d1e2f3a4")
        with engine.begin() as conn:  # recreate the legacy auto-named duplicates
            conn.execute(text("CREATE INDEX ix_organization_integrations_organization_id ON organization_integrations (organization_id)"))
            conn.execute(text("CREATE INDEX ix_organization_integrations_provider ON organization_integrations (provider)"))
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            names = {r[0] for r in conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'organization_integrations'"))}
        assert "ix_organization_integrations_organization_id" not in names
        assert "ix_organization_integrations_provider" not in names
        assert {"ix_org_integrations_org_id", "ix_org_integrations_provider"} <= names
        assert _metadata_diffs(engine) == []
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n AND pid <> pg_backend_pid()"), {"n": scratch_name})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_name}"'))
        admin.dispose()
