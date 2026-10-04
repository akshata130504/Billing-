"""0034: an untouched published landing page (still the original bundled default with invented
customer examples) gets the corrected default published as a new version; a page staff customised
is never touched, and an environment that never seeded the page is left alone."""
import importlib.util
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BEFORE = "1e2f3a4b5c6d"
TARGET = "2f3a4b5c6d7e"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _migration():
    path = next((REPO_ROOT / "backend" / "alembic" / "versions").glob("2f3a4b5c6d7e_*.py"))
    spec = importlib.util.spec_from_file_location("m0034", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cfg(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
    return cfg


def _seed_page(engine, sha: str) -> str:
    now = datetime.now(timezone.utc)
    version_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO website_content_versions (id, page_key, state, version, revision, content, content_sha256, "
                "created_at, updated_at, published_at) VALUES (:id, 'landing', 'published', 1, 1, :content, :sha, :now, :now, :now)"
            ),
            {"id": version_id, "content": json.dumps({"placeholder": True}), "sha": sha, "now": now},
        )
        conn.execute(
            sa.text("INSERT INTO website_pages (key, published_version_id, updated_at) VALUES ('landing', :v, :now)"),
            {"v": version_id, "now": now},
        )
    return version_id


def _published(engine):
    with engine.connect() as conn:
        return conn.execute(
            sa.text(
                "SELECT v.id, v.version, v.content_sha256, v.based_on_version FROM website_pages p "
                "JOIN website_content_versions v ON v.id = p.published_version_id WHERE p.key = 'landing'"
            )
        ).first()


def _fresh(tmp_path, name):
    url = f"sqlite:///{(tmp_path / name).as_posix()}"
    command.upgrade(_cfg(url), BEFORE)
    return url, sa.create_engine(url)


def test_untouched_original_default_is_replaced_by_corrected_default(tmp_path):
    from backend.app.services.website_service import seed_content, sha256

    url, engine = _fresh(tmp_path, "m0034a.sqlite3")
    try:
        old_id = _seed_page(engine, _migration().ORIGINAL_DEFAULT_SHA256)
        command.upgrade(_cfg(url), TARGET)
        row = _published(engine)
        assert row.id != old_id
        assert row.version == 2 and row.based_on_version == 1
        assert row.content_sha256 == sha256(seed_content())
        with engine.connect() as conn:  # history is append-only: the old version is still there
            assert conn.execute(sa.text("SELECT count(*) FROM website_content_versions")).scalar() == 2
    finally:
        engine.dispose()


def test_customised_landing_page_is_not_touched(tmp_path):
    url, engine = _fresh(tmp_path, "m0034b.sqlite3")
    try:
        old_id = _seed_page(engine, "f" * 64)
        command.upgrade(_cfg(url), TARGET)
        assert _published(engine).id == old_id
    finally:
        engine.dispose()


def test_never_seeded_landing_page_is_a_no_op(tmp_path):
    url, engine = _fresh(tmp_path, "m0034c.sqlite3")
    try:
        command.upgrade(_cfg(url), TARGET)
        assert _published(engine) is None
        command.downgrade(_cfg(url), BEFORE)
        command.upgrade(_cfg(url), "head")
    finally:
        engine.dispose()


def test_original_default_hash_matches_the_retired_content():
    """Guards the constant: the corrected bundled default must NOT hash to the retired original."""
    from backend.app.services.website_service import seed_content, sha256

    assert sha256(seed_content()) != _migration().ORIGINAL_DEFAULT_SHA256
