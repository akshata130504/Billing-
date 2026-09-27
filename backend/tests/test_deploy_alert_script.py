"""deploy/alert.sh (systemd OnFailure hook) must POST valid JSON with the scrubbed journal tail.

Regression: the JSON-escaping sed expression was malformed, so every alert went out as
{"text": ""} (rejected by Slack-style webhooks); and "Authorization: Bearer <token>" leaked the
token because the key=value rule consumed "Bearer" before the bearer rule could match.
"""
import json
import os
import shutil
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None, reason="needs a POSIX sh")

JOURNAL = r"""#!/bin/sh
printf 'deploy-poll: cd /opt/rooman-billing && docker compose pull failed\n'
printf 'error: "manifest unknown" at C:\\tmp\\x\ttab\n'
printf 'GITHUB_PAT=ghp_abcdefghijklmnopqrstuvwxyz0123456789 password=hunter2hunter2\n'
printf 'fetch https://user:s3cretpw@github.com/org/repo.git Authorization: Bearer abcdefgh12345678\n'
"""
SECRETS = ("ghp_abcdefghijklmnop", "hunter2hunter2", "s3cretpw", "abcdefgh12345678")


@pytest.fixture
def receiver():
    bodies = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            bodies.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/hook", bodies
    server.shutdown()


def test_alert_sh_posts_valid_scrubbed_json(tmp_path, receiver):
    url, bodies = receiver
    fake = tmp_path / "journalctl"
    fake.write_text(JOURNAL, newline="\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "ALERT_WEBHOOK_URL": url, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"}

    result = subprocess.run([SH, "deploy/alert.sh", "rooman-billing-poll.service"], cwd=REPO_ROOT, env=env,
                            capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stderr
    assert len(bodies) == 1
    text = json.loads(bodies[0])["text"]  # raises if the escaping produced invalid JSON
    assert "rooman-billing-poll.service FAILED" in text
    assert "/opt/rooman-billing" in text and '"manifest unknown"' in text and "C:\\tmp\\x" in text
    assert not [s for s in SECRETS if s in text]


def test_alert_sh_without_url_only_logs(tmp_path):
    env = {**os.environ, "ALERT_WEBHOOK_URL": ""}
    result = subprocess.run([SH, str(REPO_ROOT / "deploy/alert.sh"), "some.service"], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    assert "alert only logged" in result.stderr
