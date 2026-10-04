"""Repository-side guards for the production deployment pipeline.

The complete application (api, scheduler, tenant web AND the platform/Super Admin console) must be
built from one commit, shipped by one mechanism (deploy.yml -> GHCR -> deploy/deploy-poll.sh) and
gated by health + rollback. These tests read the files as text (no YAML dependency) so a change that
silently drops the platform image, a required origin or the preflight fails CI.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _service_block(compose: str, name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z-]*:\n|^volumes:)", compose, re.S | re.M)
    assert match, f"service {name} not found in docker-compose.prod.yml"
    return match.group(1)


def test_compose_runs_platform_web_as_a_real_sha_matched_service():
    block = _service_block(_read("docker-compose.prod.yml"), "platform-web")
    assert "rooman-billing-platform-web:${IMAGE_TAG:-latest}" in block  # same SHA tag as api/web
    assert "dockerfile: Dockerfile.platform" in block
    assert "healthcheck:" in block and "/healthz" in block  # the poller waits for this
    assert "restart: unless-stopped" in block
    assert "ports:" not in block  # only the reverse proxy reaches it, never a host port
    # The build origin has no default: compose refuses to start without it.
    assert "VITE_TENANT_APP_ORIGIN: ${TENANT_APP_ORIGIN:?" in block


def test_compose_requires_platform_origin_and_secret_for_backend_and_tenant_build():
    compose = _read("docker-compose.prod.yml")
    backend = _service_block(compose, "backend")
    assert "PLATFORM_APP_ORIGIN: ${PLATFORM_APP_ORIGIN:?" in backend
    assert "PLATFORM_JWT_SECRET: ${PLATFORM_JWT_SECRET:?" in backend
    frontend = _service_block(compose, "frontend")
    assert "VITE_PLATFORM_APP_ORIGIN: ${PLATFORM_APP_ORIGIN:?" in frontend
    # least-privilege DB role stays mandatory for the API and the scheduler
    for name in ("backend", "scheduler"):
        block = _service_block(compose, name)
        assert "${APP_POSTGRES_USER:?" in block and "${APP_POSTGRES_PASSWORD:?" in block


def test_caddy_overlay_routes_the_platform_domain():
    overlay = _read("docker-compose.caddy.yml")
    assert "PLATFORM_DOMAIN: ${PLATFORM_DOMAIN:?" in overlay
    assert "platform-web:" in overlay
    caddyfile = _read("deploy/Caddyfile")
    assert "{$PLATFORM_DOMAIN}" in caddyfile and "reverse_proxy platform-web:80" in caddyfile


def test_deploy_workflow_builds_all_three_images_from_the_same_sha():
    wf = _read(".github/workflows/deploy.yml")
    for image in ("API_IMAGE", "WEB_IMAGE", "PLATFORM_IMAGE"):
        assert re.search(rf"tags: \${{{{ env\.{image} }}}}:\${{{{ env\.DEPLOY_SHA }}}}", wf), image
    assert "file: frontend/Dockerfile.platform" in wf
    assert "VITE_TENANT_APP_ORIGIN=${{ vars.TENANT_APP_ORIGIN }}" in wf
    assert "VITE_PLATFORM_APP_ORIGIN=${{ vars.PLATFORM_APP_ORIGIN }}" in wf
    # still gated on a successful CI run for a push to main; never a pull request
    assert "workflow_run" in wf and "github.event.workflow_run.conclusion == 'success'" in wf
    assert "github.event.workflow_run.head_branch == 'main'" in wf
    # origins are validated (and the run fails) before anything is built
    assert wf.index("Require valid production origins") < wf.index("Build & push API image")
    # :latest moves only after every sha-tagged image exists, api last (the poller reads it)
    promote = wf[wf.index("Promote :latest"):]
    assert promote.index("$PLATFORM_IMAGE:latest") < promote.index("$WEB_IMAGE:latest") < promote.index("$API_IMAGE:latest")
    assert wf.index("Build & push platform") < wf.index("Promote :latest")


def test_platform_dockerfile_requires_its_origin_and_has_no_default():
    dockerfile = _read("frontend/Dockerfile.platform")
    assert re.search(r"^ARG VITE_TENANT_APP_ORIGIN$", dockerfile, re.M)  # no default value
    assert "check-origin VITE_TENANT_APP_ORIGIN" in dockerfile and "required" in dockerfile
    assert "localhost" not in dockerfile.lower().replace("# ", "")
    tenant = _read("frontend/Dockerfile")
    assert re.search(r'^ARG VITE_PLATFORM_APP_ORIGIN=""$', tenant, re.M)


def test_origin_check_script_rejects_missing_and_malformed_origins(tmp_path):
    script = REPO / "frontend" / "docker" / "check-origin.sh"

    def run(value: str, mode: str = "required") -> int:
        return subprocess.run(["sh", str(script), "VITE_X", value, mode], capture_output=True, text=True).returncode

    assert run("https://billing.example.com") == 0
    assert run("") != 0  # required and missing: fail
    assert run("", "optional") == 0  # optional and empty: feature stays disabled
    assert run("https://billing.example.com/") != 0  # trailing slash
    assert run("https://billing.example.com/app") != 0  # path
    assert run("billing.example.com") != 0  # no scheme


def test_poller_ships_and_gates_the_platform_service():
    poll = _read("deploy/deploy-poll.sh")
    assert "PLATFORM_IMAGE" in poll and "platform-web" in poll
    assert "wait_platform_healthy" in poll  # an unhealthy console fails the release
    assert "check-env.sh" in poll  # preflight before anything is pulled or restarted
    # rollback, pre-deploy backup, SHA record and alerting are preserved
    for needle in ("Rolling back to previous release", "pg_dump", 'deployed_sha"', "alert "):
        assert needle in poll, needle
    # the preflight runs before the pull and the backup
    assert poll.index("3b. Preflight") < poll.index("4. Pull the release images") < poll.index("5. Pre-deploy database backup")


def test_env_example_and_check_require_the_production_settings():
    check = _read("deploy/check-env.sh")
    for name in ("APP_POSTGRES_USER", "APP_POSTGRES_PASSWORD", "PLATFORM_APP_ORIGIN", "PLATFORM_DOMAIN",
                 "PLATFORM_JWT_SECRET", "TENANT_APP_ORIGIN", "GITHUB_PAT", "SECRET_KEY", "FRONTEND_URL"):
        assert re.search(rf"check REQUIRED[^\n]*\b{name}\b", check), name
    example = _read(".env.production.example")
    for name in ("APP_POSTGRES_USER", "APP_POSTGRES_PASSWORD", "PLATFORM_APP_ORIGIN", "PLATFORM_DOMAIN",
                 "PLATFORM_JWT_SECRET", "TENANT_APP_ORIGIN", "GITHUB_PAT", "ALERT_WEBHOOK_URL", "OFFSITE_BACKUP_REMOTE"):
        match = re.search(rf"^{name}=(.*)$", example, re.M)
        assert match, f"{name} missing from .env.production.example"
        assert match.group(1).strip() == "", f"{name} must not carry a committed value"
