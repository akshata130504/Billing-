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
