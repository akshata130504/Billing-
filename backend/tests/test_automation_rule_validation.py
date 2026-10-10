"""BUG-59: automation rules need a real name, and new webhook actions must use https."""
import pytest

from backend.tests.test_customization_and_automation import webhook_network  # noqa: F401 (fixture)

RULES = "/api/v1/automation/rules"


def _rule(name="Invoice hook", url="https://hooks.example.test/in"):
    return {
        "name": name,
        "module": "invoice",
        "trigger_event": "created",
        "actions": [{"action_type": "webhook", "name": "hook", "configuration": {"url": url}}],
    }


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_blank_rule_name_rejected(client, tenant, auth_headers, webhook_network, name):  # noqa: F811
    res = client.post(RULES, headers=auth_headers, json=_rule(name=name))
    assert res.status_code == 422, res.text


def test_rule_name_is_trimmed_and_blank_rename_rejected(client, tenant, auth_headers, webhook_network):  # noqa: F811
    res = client.post(RULES, headers=auth_headers, json=_rule(name="  Nightly sync  "))
    assert res.status_code == 200, res.text
    rule = res.json()
    assert rule["name"] == "Nightly sync"

    bad = client.put(f"{RULES}/{rule['id']}", headers=auth_headers, json={"name": " "})
    if bad.status_code == 405:
        bad = client.patch(f"{RULES}/{rule['id']}", headers=auth_headers, json={"name": " "})
    assert bad.status_code == 422, bad.text


def test_plain_http_webhook_rejected(client, tenant, auth_headers, webhook_network):  # noqa: F811
    res = client.post(RULES, headers=auth_headers, json=_rule(url="http://hooks.example.test/in"))
    assert res.status_code == 422, res.text
    assert res.json()["error"]["details"]["fields"]["url"] == "https_required"


def test_https_webhook_still_ssrf_checked(client, tenant, auth_headers, webhook_network):  # noqa: F811
    for url in ("https://127.0.0.1/h", "https://169.254.169.254/latest", "https://10.0.0.5/h"):
        assert client.post(RULES, headers=auth_headers, json=_rule(url=url)).status_code == 422, url
    assert client.post(RULES, headers=auth_headers, json=_rule()).status_code == 200
