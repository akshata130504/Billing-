"""Repository-side guards for the production deployment pipeline.

ONE website, ONE public origin: the tenant app (/admin) and the platform / Super Admin console
(/superadmin) are served by the same web image on the origin of FRONTEND_URL. The complete
application (api, scheduler, web) must be built from one commit, shipped by one mechanism
(deploy.yml -> GHCR -> deploy/deploy-poll.sh) and gated by health + rollback. These tests read the
files as text (no YAML dependency) so a change that brings back a second public platform origin,
drops the console from the web image, or drops the preflight fails CI.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

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
    assert "rooman-billing-web:${IMAGE_TAG:-latest}" in frontend
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
