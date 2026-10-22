"""Repository-side guards for the production deployment pipeline.

ONE website, ONE public origin: the tenant app (/admin) and the platform / Super Admin console
(/superadmin) are served by the same web image on the origin of FRONTEND_URL. The complete
application (api, scheduler, web) must be built from one commit, shipped by one mechanism
(deploy.yml -> GHCR -> deploy/deploy-poll.sh) and gated by health + rollback. These tests read the
files as text (no YAML dependency) so a change that brings back a second public platform origin,
drops the console from the web image, or drops the preflight fails CI.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from backend.app.core.config import Settings

REPO = Path(__file__).resolve().parents[2]
RETIRED = ("PLATFORM_APP_ORIGIN", "PLATFORM_DOMAIN", "TENANT_APP_ORIGIN", "platform-web", "Dockerfile.platform")
DEPLOY_FILES = (
    "docker-compose.prod.yml", "docker-compose.caddy.yml", "deploy/Caddyfile", ".github/workflows/deploy.yml",
    ".github/workflows/ci.yml", "deploy/deploy-poll.sh", "frontend/Dockerfile", "frontend/docker/nginx.conf",
    "frontend/vite.config.ts", "frontend/package.json",
)


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _service_block(compose: str, name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z-]*:\n|^volumes:)", compose, re.S | re.M)
    assert match, f"service {name} not found in docker-compose.prod.yml"
    return match.group(1)


def _nginx_location(conf: str, spec: str) -> str:
    match = re.search(rf"^    location {re.escape(spec)} \{{\n(.*?)^    \}}", conf, re.S | re.M)
    assert match, f"nginx location {spec} not found"
    return match.group(1)


def test_no_second_public_platform_origin_anywhere_in_the_deployment():
    for rel in DEPLOY_FILES:
        text = _read(rel)
        for needle in RETIRED:
            assert needle not in text, f"{rel} still mentions {needle}"
    for gone in ("frontend/Dockerfile.platform", "frontend/docker/nginx.platform.conf",
                 "frontend/vite.platform.config.ts", "frontend/platform.html", "frontend/docker/check-origin.sh"):
        assert not (REPO / gone).exists(), gone


def test_compose_serves_one_website_and_keeps_platform_sign_in_mandatory():
    compose = _read("docker-compose.prod.yml")
    assert not re.search(r"^  platform-web:", compose, re.M)
    backend = _service_block(compose, "backend")
    assert "PLATFORM_JWT_SECRET: ${PLATFORM_JWT_SECRET:?" in backend  # the console always ships
    frontend = _service_block(compose, "frontend")
    assert "rooman-billing-web}:${IMAGE_TAG:-latest}" in frontend
    assert "healthcheck:" in frontend and "/healthz" in frontend
    # least-privilege DB role stays mandatory for the API and the scheduler
    for name in ("backend", "scheduler"):
        block = _service_block(compose, name)
        assert "${APP_POSTGRES_USER:?" in block and "${APP_POSTGRES_PASSWORD:?" in block


def test_caddy_overlay_has_one_public_domain():
    overlay = _read("docker-compose.caddy.yml")
    assert "DOMAIN: ${DOMAIN:?" in overlay
    caddyfile = _read("deploy/Caddyfile")
    sites = re.findall(r"^(\{\$[A-Z_]+\}) \{", caddyfile, re.M)
    assert sites == ["{$DOMAIN}"], sites
    assert caddyfile.count("reverse_proxy ") == 1 and "reverse_proxy frontend:80" in caddyfile


def test_web_image_builds_and_serves_both_entry_points():
    vite = _read("frontend/vite.config.ts")
    assert "index.html" in vite and "superadmin.html" in vite  # one build, two documents
    assert (REPO / "frontend" / "superadmin.html").exists()
    dockerfile = _read("frontend/Dockerfile")
    assert "RUN npm run build" in dockerfile
    assert "platform-security-headers.conf /etc/nginx/snippets/platform-security-headers.conf" in dockerfile
    assert not re.search(r"^ARG \w*ORIGIN", dockerfile, re.M)  # no origin is baked into the bundle


def test_nginx_serves_the_console_at_superadmin_with_the_strict_headers():
    conf = _read("frontend/docker/nginx.conf")
    for spec in ("= /superadmin", "^~ /superadmin/"):
        block = _nginx_location(conf, spec)
        assert "try_files /superadmin.html =404;" in block, spec
        assert "platform-security-headers.conf" in block and "no-store" in block, spec
    # the platform API keeps its own (stricter) headers and small body limit on the shared origin
    api = _nginx_location(conf, "^~ /api/v1/platform/")
    assert "platform-security-headers.conf" in api and "client_max_body_size 64k;" in api
    upload = _nginx_location(conf, "= /api/v1/platform/website/assets")
    assert "client_max_body_size 32m;" in upload
    # the tenant app keeps the tenant headers and the SPA fallback
    assert "try_files $uri /index.html;" in _nginx_location(conf, "/")
    headers = _read("frontend/docker/platform-security-headers.conf")
    assert "frame-ancestors 'none'" in headers and "script-src 'self';" in headers
    assert "razorpay" not in headers and "fonts.g" not in headers


def test_visual_editor_preview_frame_is_same_origin_only():
    """The console may embed exactly one page of its own origin (the visual editor preview); the
    preview may be framed only by that origin and frames nothing itself."""
    conf = _read("frontend/docker/nginx.conf")
    block = _nginx_location(conf, "= /superadmin/ui-preview")
    assert "platform-preview-security-headers.conf" in block and "no-store" in block
    assert "try_files /superadmin.html =404;" in block
    preview = _read("frontend/docker/platform-preview-security-headers.conf")
    assert "frame-ancestors 'self';" in preview and "frame-src 'none';" in preview
    assert 'X-Frame-Options "SAMEORIGIN"' in preview and "script-src 'self';" in preview
    assert "razorpay" not in preview and "https:" not in preview.split("Content-Security-Policy", 1)[1]
    # the preview answers every request from sample data: the browser refuses any network request
    assert "connect-src 'none';" in preview and "form-action 'none';" in preview
    for snippet in (preview, _read("frontend/docker/platform-security-headers.conf")):
        for line in snippet.splitlines():  # only comments and well-formed `add_header ... always;`
            assert not line.strip() or line.startswith("#") or (
                line.startswith("add_header ") and line.endswith(" always;")), line
    console =_read("frontend/docker/platform-security-headers.conf")
    assert "frame-ancestors 'none';" in console and "frame-src 'self';" in console
    assert 'X-Frame-Options "DENY"' in console
    dockerfile = _read("frontend/Dockerfile")
    assert "platform-preview-security-headers.conf /etc/nginx/snippets/platform-preview-security-headers.conf" in dockerfile
    # no other location uses the framable header set
    assert conf.count("platform-preview-security-headers.conf") == 1


def test_deploy_workflow_builds_both_images_from_the_same_sha():
    wf = _read(".github/workflows/deploy.yml")
    for image in ("API_IMAGE", "WEB_IMAGE"):
        assert re.search(rf"tags: \${{{{ env\.{image} }}}}:\${{{{ env\.DEPLOY_SHA }}}}", wf), image
    assert "file: frontend/Dockerfile\n" in wf
    # still gated on a successful CI run for a push to main; never a pull request
    assert "workflow_run" in wf and "github.event.workflow_run.conclusion == 'success'" in wf
    assert "github.event.workflow_run.head_branch == 'main'" in wf
    # :latest moves only after every sha-tagged image exists, api last (the poller reads it)
    promote = wf[wf.index("Promote :latest"):]
    assert promote.index("$WEB_IMAGE:latest") < promote.index("$API_IMAGE:latest")


def test_poller_preflight_rollback_and_backup_are_kept():
    poll = _read("deploy/deploy-poll.sh")
    assert "check-env.sh" in poll  # preflight before anything is pulled or restarted
    assert "for service in backend frontend; do" in poll
    for needle in ("Rolling back to previous release", "pg_dump", 'deployed_sha"', "alert "):
        assert needle in poll, needle
    assert poll.index("3b. Preflight") < poll.index("4. Pull the release images") < poll.index("5. Pre-deploy database backup")


def test_env_example_and_check_require_the_production_settings():
    check = _read("deploy/check-env.sh")
    for name in ("APP_POSTGRES_USER", "APP_POSTGRES_PASSWORD", "PLATFORM_JWT_SECRET", "GITHUB_PAT", "SECRET_KEY",
                 "FRONTEND_URL"):
        assert re.search(rf"check REQUIRED[^\n]*\b{name}\b", check), name
    example = _read(".env.production.example")
    for name in ("APP_POSTGRES_USER", "APP_POSTGRES_PASSWORD", "PLATFORM_JWT_SECRET", "GITHUB_PAT",
                 "ALERT_WEBHOOK_URL", "OFFSITE_BACKUP_REMOTE"):
        match = re.search(rf"^{name}=(.*)$", example, re.M)
        assert match, f"{name} missing from .env.production.example"
        assert match.group(1).strip() == "", f"{name} must not carry a committed value"
    for name in ("PLATFORM_APP_ORIGIN", "PLATFORM_DOMAIN", "TENANT_APP_ORIGIN"):
        assert not re.search(rf"^{name}=", example, re.M), f"retired {name} is still a setting"


VALID_ENV = """\
SECRET_KEY=8f3c1e7a9b2d4c6e0f1a3b5c7d9e2f4a6b8c0d2e
FRONTEND_URL=https://billing.example.test
ALLOWED_ORIGINS=https://billing.example.test
DOMAIN=billing.example.test
POSTGRES_USER=rooman_owner
POSTGRES_PASSWORD=owner-password-0123456789
POSTGRES_DB=rooman_billing
APP_POSTGRES_USER=rooman_app
APP_POSTGRES_PASSWORD=app-password-0123456789
PLATFORM_JWT_SECRET=4e6a8c0e2a4c6e8a0c2e4a6c8e0a2c4e6a8c0e2a
GITHUB_PAT=ghp_placeholder_for_test_only
SMTP_HOST=smtp.example.test
SMTP_PORT=587
SMTP_USERNAME=mailer
SMTP_PASSWORD=mailer-password
EMAIL_FROM_ADDRESS=billing@example.test
DEBUG=false
"""


def _check_env(tmp_path, text: str) -> subprocess.CompletedProcess:
    env_file = tmp_path / ".env.production"
    env_file.write_text(text, encoding="utf-8", newline="\n")
    return subprocess.run(["sh", str(REPO / "deploy" / "check-env.sh"), str(env_file)], capture_output=True, text=True)


def test_check_env_passes_a_single_origin_configuration(tmp_path):
    result = _check_env(tmp_path, VALID_ENV)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT: PASS" in result.stdout
    # names only, never values
    assert "4e6a8c0e2a4c6e8a0c2e" not in result.stdout and "owner-password" not in result.stdout


def test_check_env_refuses_a_missing_platform_key_or_a_non_origin_frontend_url(tmp_path):
    no_key = VALID_ENV.replace("PLATFORM_JWT_SECRET=4e6a8c0e2a4c6e8a0c2e4a6c8e0a2c4e6a8c0e2a\n", "")
    assert _check_env(tmp_path, no_key).returncode == 1
    with_path = VALID_ENV.replace("FRONTEND_URL=https://billing.example.test", "FRONTEND_URL=https://billing.example.test/app")
    assert _check_env(tmp_path, with_path).returncode == 1
    plain_http = VALID_ENV.replace("FRONTEND_URL=https://", "FRONTEND_URL=http://")
    assert _check_env(tmp_path, plain_http).returncode == 1
    other_domain = VALID_ENV.replace("DOMAIN=billing.example.test", "DOMAIN=platform.example.test")
    assert _check_env(tmp_path, other_domain).returncode == 1


def test_check_env_only_warns_about_retired_origin_settings(tmp_path):
    stale = VALID_ENV + "PLATFORM_APP_ORIGIN=https://platform.example.test\nPLATFORM_DOMAIN=platform.example.test\n"
    result = _check_env(tmp_path, stale)
    assert result.returncode == 0, result.stdout
    assert "FAIL (optional)" in result.stdout


# --------------------------------------------------------------------------- database roles
# The exact environment docker-compose.prod.yml gives the API and the scheduler, resolved against a
# .env.production like .env.production.example, must pass the production Settings validation with
# the runtime connection on APP_POSTGRES_USER and Alembic on the owner role - before and after the
# entrypoint drops the owner credentials. A compose file that makes POSTGRES_USER the runtime role
# again (POSTGRES_USER: ${APP_POSTGRES_USER}) refuses to start in production and fails here.

ENV_PRODUCTION = {
    "POSTGRES_SERVER": "db", "POSTGRES_PORT": "5432", "POSTGRES_DB": "rooman_billing",
    "POSTGRES_USER": "rooman", "POSTGRES_PASSWORD": "owner-secret-0123456789",
    "APP_POSTGRES_USER": "rooman_app", "APP_POSTGRES_PASSWORD": "app-secret-0123456789",
}
OWNER_PASSWORD = ENV_PRODUCTION["POSTGRES_PASSWORD"]
DB_KEYS = ("POSTGRES_", "APP_POSTGRES_", "MIGRATION_", "DATABASE_URL")
PROD_BASE = {
    "ENVIRONMENT": "production", "DEBUG": False,
    "SECRET_KEY": "a-cryptographically-secure-random-secret-key-67890",
    "ALLOWED_ORIGINS": ["https://billing.example.com"], "FRONTEND_URL": "https://billing.example.com",
    "SMTP_HOST": "smtp.example.com",
}


def _resolve(value: str, env: dict) -> str:
    value = value.strip()
    if value[:1] in "\"'":
        return value[1:-1]
    required = re.fullmatch(r"\$\{([A-Z_]+):\?[^}]*\}", value)
    if required:
        assert env.get(required.group(1)), f"compose requires {required.group(1)}"
        return env[required.group(1)]
    default = re.fullmatch(r"\$\{([A-Z_]+):-([^}]*)\}", value)
    if default:
        return env.get(default.group(1)) or default.group(2)
    assert "${" not in value, value
    return value


def _container_db_env(service: str) -> dict:
    """env_file (.env.production) overlaid with the service's `environment:` block - DB keys only."""
    block = _service_block(_read("docker-compose.prod.yml"), service)
    environment = re.search(r"^    environment:\n((?:^      .*\n)+)", block, re.M)
    assert environment, f"{service} has no environment block"
    env = dict(ENV_PRODUCTION)
    for key, value in re.findall(r"^      ([A-Z_]+): (.*)$", environment.group(1), re.M):
        if key.startswith(DB_KEYS):
            env[key] = _resolve(value, ENV_PRODUCTION)
    return env


def _after_entrypoint(env: dict) -> dict:
    """What backend/docker/entrypoint.sh leaves for the container command."""
    script = _read("backend/docker/entrypoint.sh")
    assert "unset MIGRATION_DATABASE_URL MIGRATION_POSTGRES_USER MIGRATION_POSTGRES_PASSWORD" in script
    assert re.search(r'if \[ -n "\$\{APP_POSTGRES_USER:-\}" \]; then\n\s+unset POSTGRES_PASSWORD\n', script)
    dropped = {"MIGRATION_DATABASE_URL", "MIGRATION_POSTGRES_USER", "MIGRATION_POSTGRES_PASSWORD"}
    if env.get("APP_POSTGRES_USER"):
        dropped.add("POSTGRES_PASSWORD")
    return {k: v for k, v in env.items() if k not in dropped}


def _settings(monkeypatch, env: dict):
    # Only the container environment counts: no inherited DB variables from the test process.
    for key in [k for k in os.environ if k.startswith(DB_KEYS)]:
        monkeypatch.delenv(key)
    monkeypatch.delenv("PLATFORM_JWT_SECRET", raising=False)
    return Settings(_env_file=None, **PROD_BASE, **env)


def _user_and_password(url: str) -> tuple:
    parsed = make_url(url)
    return parsed.username, parsed.password


def test_compose_keeps_postgres_user_as_the_owner_role():
    compose = _read("docker-compose.prod.yml")
    assert not re.search(r"^\s+POSTGRES_(USER|PASSWORD): \$\{APP_POSTGRES_", compose, re.M)
    for name in ("backend", "scheduler"):
        env = _container_db_env(name)
        assert env["POSTGRES_USER"] == "rooman" and env["APP_POSTGRES_USER"] == "rooman_app"
        assert "DATABASE_URL" not in env  # the compose deployment assembles the URLs from the roles


def test_backend_migrates_as_owner_and_serves_as_runtime_role(monkeypatch):
    env = _container_db_env("backend")
    migrating = _settings(monkeypatch, env)  # the entrypoint's wait + Alembic step
    assert _user_and_password(migrating.sync_database_url) == ("rooman_app", "app-secret-0123456789")
    assert _user_and_password(migrating.migration_database_url) == ("rooman", OWNER_PASSWORD)

    serving = _settings(monkeypatch, _after_entrypoint(env))  # gunicorn
    assert _user_and_password(serving.sync_database_url) == ("rooman_app", "app-secret-0123456789")
    assert OWNER_PASSWORD not in _after_entrypoint(env).values()


def test_scheduler_never_receives_the_owner_password(monkeypatch):
    env = _container_db_env("scheduler")
    assert OWNER_PASSWORD not in env.values()
    for stage in (env, _after_entrypoint(env)):
        s = _settings(monkeypatch, stage)
        assert _user_and_password(s.sync_database_url) == ("rooman_app", "app-secret-0123456789")


def test_production_still_refuses_postgres_user_as_the_runtime_role(monkeypatch):
    env = {**_container_db_env("backend"), "POSTGRES_USER": "rooman_app"}
    with pytest.raises(ValidationError, match="APP_POSTGRES_USER must differ from POSTGRES_USER"):
        _settings(monkeypatch, env)


def test_proxied_api_responses_carry_each_security_header_once():
    """Production QA BUG-25: /api responses had every security header twice (backend middleware
    + nginx snippet) with conflicting values. nginx must drop the backend's copies."""
    conf = _read("frontend/docker/nginx.conf")
    for spec in ("location /api/ {", "location ^~ /api/v1/platform/ {", "location = /api/v1/platform/website/assets {"):
        block = conf.split(spec, 1)[1].split("\n    }", 1)[0]
        assert "upstream-header-dedup.conf" in block, spec
    dedup = _read("frontend/docker/upstream-header-dedup.conf")
    for header in ("X-Frame-Options", "Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy",
                   "Permissions-Policy", "Strict-Transport-Security", "Cache-Control"):
        assert f"proxy_hide_header {header};" in dedup, header
    assert "upstream-header-dedup.conf /etc/nginx/snippets/upstream-header-dedup.conf" in _read("frontend/Dockerfile")


def test_backend_fallback_csp_does_not_allow_inline_scripts():
    from backend.app.main import SECURITY_HEADERS

    script_src = [d for d in SECURITY_HEADERS["Content-Security-Policy"].split(";") if d.strip().startswith("script-src")][0]
    assert "'unsafe-inline'" not in script_src
