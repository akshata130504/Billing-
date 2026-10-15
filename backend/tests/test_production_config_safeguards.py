"""Production configuration safeguards for Rooman's own plan billing, the email sender and trusted proxies.

Settings are built with _env_file=None (never the local .env). No Razorpay call, no email; all key values below are
fakes, and every refusal is checked not to echo them.
"""
import pytest

from backend.app.core.config import Settings
from backend.tests.test_deployment_config import VALID_ENV, _check_env

PLATFORM_TEST_ID = "rzp_test_PlatformFakeKey123"
PLATFORM_LIVE_ID = "rzp_live_PlatformFakeKey123"
PLATFORM_SECRET = "platform-api-secret-FAKE-9f8e7d"
PLATFORM_WEBHOOK = "platform-webhook-secret-FAKE-1a2b3c"
TENANT_TEST_ID = "rzp_test_TenantFakeKey456"
TENANT_SECRET = "tenant-api-secret-FAKE-4d5e6f"
TENANT_WEBHOOK = "tenant-webhook-secret-FAKE-7g8h9i"
SMTP_PASSWORD = "smtp-password-FAKE-0j1k2l"
SECRETS = (PLATFORM_SECRET, PLATFORM_WEBHOOK, TENANT_SECRET, TENANT_WEBHOOK, SMTP_PASSWORD)

PROD = {
    "ENVIRONMENT": "production", "DEBUG": False,
    "SECRET_KEY": "a-cryptographically-secure-random-secret-key-67890",
    "DATABASE_URL": "postgresql+psycopg://app_user:prod_strong_pass_123@db:5432/rooman_billing",
    "ALLOWED_ORIGINS": ["https://billing.rooman-billing.in"], "FRONTEND_URL": "https://billing.rooman-billing.in",
    "SMTP_HOST": "smtp.rooman-billing.in", "SMTP_PASSWORD": SMTP_PASSWORD,
    "EMAIL_FROM_ADDRESS": "billing@rooman-billing.in",
}
LIVE_PLATFORM = {"PLATFORM_RAZORPAY_KEY_ID": PLATFORM_LIVE_ID, "PLATFORM_RAZORPAY_KEY_SECRET": PLATFORM_SECRET,
                 "PLATFORM_RAZORPAY_WEBHOOK_SECRET": PLATFORM_WEBHOOK}
TEST_PLATFORM = {**LIVE_PLATFORM, "PLATFORM_RAZORPAY_KEY_ID": PLATFORM_TEST_ID}


def _settings(**overrides):
    return Settings(_env_file=None, **{**PROD, **overrides})


def _refused(match, **overrides):
    with pytest.raises(ValueError, match=match) as exc:
        _settings(**overrides)
    message = str(exc.value)
    for secret in SECRETS:
        assert secret not in message  # values are never echoed
    return message


# --- Rooman's platform Razorpay account ---------------------------------------------------------------------------


@pytest.mark.parametrize("allow_live", [False, True])
def test_production_refuses_platform_test_mode_keys(allow_live):
    message = _refused("Live Mode key", **TEST_PLATFORM, PLATFORM_CHECKOUT_ALLOW_LIVE=allow_live)
    assert PLATFORM_TEST_ID not in message


def test_production_refuses_platform_keys_without_their_webhook_secret():
    _refused("PLATFORM_RAZORPAY_WEBHOOK_SECRET must be set",
             **{**LIVE_PLATFORM, "PLATFORM_RAZORPAY_WEBHOOK_SECRET": ""})
    _refused("PLATFORM_RAZORPAY_WEBHOOK_SECRET must be set",
             **{**LIVE_PLATFORM, "PLATFORM_RAZORPAY_WEBHOOK_SECRET": "   "}, PLATFORM_CHECKOUT_ALLOW_LIVE=True)


def test_production_refuses_live_checkout_enabled_without_platform_credentials():
    _refused("PLATFORM_CHECKOUT_ALLOW_LIVE=true needs", PLATFORM_CHECKOUT_ALLOW_LIVE=True)


@pytest.mark.parametrize("allow_live", [False, True])
def test_production_accepts_live_platform_keys_with_their_webhook(allow_live):
    s = _settings(**LIVE_PLATFORM, PLATFORM_CHECKOUT_ALLOW_LIVE=allow_live)
    assert s.platform_razorpay_enabled and s.is_live_environment


def test_production_with_platform_billing_off_needs_nothing_more():
    s = _settings()  # no platform keys, live checkout off: plan checkout stays unavailable (fail-safe)
    assert not s.platform_razorpay_enabled and not s.PLATFORM_CHECKOUT_ALLOW_LIVE


def test_staging_may_rehearse_with_test_keys_but_still_needs_the_webhook():
    s = _settings(ENVIRONMENT="staging", **TEST_PLATFORM)
    assert s.is_production and not s.is_live_environment
    _refused("PLATFORM_RAZORPAY_WEBHOOK_SECRET must be set", ENVIRONMENT="staging",
             **{**TEST_PLATFORM, "PLATFORM_RAZORPAY_WEBHOOK_SECRET": ""})


@pytest.mark.parametrize("environment", ["development", "test"])
def test_development_and_test_keep_working_with_test_keys_and_placeholders(environment):
    s = Settings(_env_file=None, ENVIRONMENT=environment, PLATFORM_RAZORPAY_KEY_ID=PLATFORM_TEST_ID,
                 PLATFORM_RAZORPAY_KEY_SECRET=PLATFORM_SECRET, SMTP_HOST="localhost",
                 EMAIL_FROM_ADDRESS="billing@example.com", TRUSTED_PROXIES="0.0.0.0/0")
    assert not s.is_production and s.platform_razorpay_enabled  # no webhook secret needed locally


def test_tenant_razorpay_keys_are_not_judged_by_the_platform_rules():
    # Tenant fallback keys in Test Mode with their own webhook: no platform rule applies to them.
    s = _settings(RAZORPAY_KEY_ID=TENANT_TEST_ID, RAZORPAY_KEY_SECRET=TENANT_SECRET, RAZORPAY_WEBHOOK_SECRET=TENANT_WEBHOOK)
    assert s.razorpay_enabled and not s.platform_razorpay_enabled
    # and live platform keys alongside them are accepted
    assert _settings(**LIVE_PLATFORM, RAZORPAY_KEY_ID=TENANT_TEST_ID, RAZORPAY_KEY_SECRET=TENANT_SECRET,
                     RAZORPAY_WEBHOOK_SECRET=TENANT_WEBHOOK).platform_razorpay_enabled
    # the existing tenant rule is unchanged: tenant keys still need their own webhook secret
    message = _refused("RAZORPAY_WEBHOOK_SECRET must be set when RAZORPAY_KEY_ID",
                       RAZORPAY_KEY_ID=TENANT_TEST_ID, RAZORPAY_KEY_SECRET=TENANT_SECRET)
    assert "PLATFORM_RAZORPAY" not in message


def test_the_platform_webhook_secret_cannot_reuse_a_tenant_secret():
    _refused("must be its own value", **{**LIVE_PLATFORM, "PLATFORM_RAZORPAY_WEBHOOK_SECRET": TENANT_WEBHOOK},
             RAZORPAY_KEY_ID=TENANT_TEST_ID, RAZORPAY_KEY_SECRET=TENANT_SECRET, RAZORPAY_WEBHOOK_SECRET=TENANT_WEBHOOK)


# --- email sender ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sender", [
    "billing@example.com", "BILLING@EXAMPLE.COM", "noreply@example.org", "billing@example.net", "billing@example.in",
    "billing@mail.example", "billing@rooman.test", "billing@rooman.invalid", "billing@host.local", "billing@my.localhost",
])
def test_production_refuses_placeholder_senders(sender):
    message = _refused("not a placeholder", EMAIL_FROM_ADDRESS=sender)
    assert sender.lower() not in message.lower().replace("billing@example.com", "")  # only the generic example


@pytest.mark.parametrize("sender", ["", "billing", "billing@", "@rooman-billing.in", "Rooman <billing@rooman-billing.in>",
                                    "billing@localhost", "billing@rooman_billing"])
def test_production_refuses_malformed_senders(sender):
    _refused("EMAIL_FROM_ADDRESS must be a valid email address", EMAIL_FROM_ADDRESS=sender)


@pytest.mark.parametrize("sender", ["billing@rooman-billing.in", "no-reply@mail.rooman.co.in", "Billing.Team@Rooman.com"])
def test_production_accepts_real_senders(sender):
    assert _settings(EMAIL_FROM_ADDRESS=sender).EMAIL_FROM_ADDRESS == sender


def test_production_without_smtp_does_not_judge_the_sender():
    # Email disabled (existing behaviour: the API starts and logs a critical message); nothing is sent from it.
    assert _settings(SMTP_HOST="", EMAIL_FROM_ADDRESS="billing@example.com").email_enabled is False


def test_staging_also_refuses_placeholder_senders():
    _refused("not a placeholder", ENVIRONMENT="staging", EMAIL_FROM_ADDRESS="billing@example.com")


# --- trusted proxies ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("proxies", ["0.0.0.0/0", "::/0", "10.0.0.0/8,0.0.0.0/0"])
def test_production_refuses_trusting_every_address_as_a_proxy(proxies):
    _refused("TRUSTED_PROXIES must not trust every address", TRUSTED_PROXIES=proxies)


def test_production_accepts_specific_proxy_ranges():
    assert len(_settings(TRUSTED_PROXIES="10.0.0.0/8,173.245.48.0/20").trusted_proxy_networks) == 2


def test_all_problems_are_reported_together_without_values():
    message = _refused("Refusing to start in production", **{**TEST_PLATFORM, "PLATFORM_RAZORPAY_WEBHOOK_SECRET": ""},
                       EMAIL_FROM_ADDRESS="billing@example.com", TRUSTED_PROXIES="0.0.0.0/0")
    for part in ("PLATFORM_RAZORPAY_WEBHOOK_SECRET", "Live Mode key", "EMAIL_FROM_ADDRESS", "TRUSTED_PROXIES"):
        assert part in message
    assert PLATFORM_TEST_ID not in message


# --- pre-deploy check (deploy/check-env.sh) ---------------------------------------------------------------------


def _env(**values):
    text = VALID_ENV
    for key, value in values.items():
        if f"\n{key}=" in "\n" + text:
            text = "\n".join(f"{key}={value}" if line.startswith(f"{key}=") else line for line in text.splitlines()) + "\n"
        else:
            text += f"{key}={value}\n"
    return text


def test_check_env_refuses_a_placeholder_sender(tmp_path):
    assert _check_env(tmp_path, _env(EMAIL_FROM_ADDRESS="billing@example.com")).returncode == 1
    assert _check_env(tmp_path, _env(EMAIL_FROM_ADDRESS="billing@rooman.test")).returncode == 1
    assert _check_env(tmp_path, _env()).returncode == 0


def test_check_env_platform_rules(tmp_path):
    test_keys = _env(PLATFORM_RAZORPAY_KEY_ID=PLATFORM_TEST_ID, PLATFORM_RAZORPAY_KEY_SECRET=PLATFORM_SECRET,
                     PLATFORM_RAZORPAY_WEBHOOK_SECRET=PLATFORM_WEBHOOK)
    result = _check_env(tmp_path, test_keys)
    assert result.returncode == 1 and "platform key is LIVE mode" in result.stdout
    no_webhook = _env(PLATFORM_RAZORPAY_KEY_ID=PLATFORM_LIVE_ID, PLATFORM_RAZORPAY_KEY_SECRET=PLATFORM_SECRET)
    assert _check_env(tmp_path, no_webhook).returncode == 1
    only_id = _env(PLATFORM_RAZORPAY_KEY_ID=PLATFORM_LIVE_ID, PLATFORM_RAZORPAY_WEBHOOK_SECRET=PLATFORM_WEBHOOK)
    assert _check_env(tmp_path, only_id).returncode == 1
    assert _check_env(tmp_path, _env(PLATFORM_CHECKOUT_ALLOW_LIVE="true")).returncode == 1
    good = _env(PLATFORM_RAZORPAY_KEY_ID=PLATFORM_LIVE_ID, PLATFORM_RAZORPAY_KEY_SECRET=PLATFORM_SECRET,
                PLATFORM_RAZORPAY_WEBHOOK_SECRET=PLATFORM_WEBHOOK, PLATFORM_CHECKOUT_ALLOW_LIVE="true")
    result = _check_env(tmp_path, good)
    assert result.returncode == 0, result.stdout
    for value in (PLATFORM_LIVE_ID, PLATFORM_SECRET, PLATFORM_WEBHOOK):
        assert value not in result.stdout  # names only, never values


# --- Caddy overlay: ACME_EMAIL contract ----------------------------------------------------------------------------


def _without(text, key):
    return "".join(line + "\n" for line in text.splitlines() if not line.startswith(f"{key}="))


def test_check_env_requires_a_real_acme_email_when_the_caddy_overlay_is_used(tmp_path):
    no_acme = _without(VALID_ENV, "ACME_EMAIL")  # DOMAIN is set = Caddy overlay
    result = _check_env(tmp_path, no_acme)
    assert result.returncode == 1 and "ACME_EMAIL is a real mailbox" in result.stdout
    for placeholder in ("ops@example.com", "OPS@EXAMPLE.ORG", "ops@rooman.test", "ops@host.invalid", "ops", "ops@localhost"):
        result = _check_env(tmp_path, _env(ACME_EMAIL=placeholder))
        assert result.returncode == 1, placeholder
    marker = "ops-MARKERACME7f3a@rooman-billing.in"
    result = _check_env(tmp_path, _env(ACME_EMAIL=marker))
    assert result.returncode == 0, result.stdout
    assert "MARKERACME7f3a" not in result.stdout  # names only, never values


def test_check_env_does_not_require_acme_email_without_the_caddy_overlay(tmp_path):
    plain = _without(_without(VALID_ENV, "DOMAIN"), "ACME_EMAIL")
    result = _check_env(tmp_path, plain)
    assert result.returncode == 0, result.stdout
    assert "ACME_EMAIL" not in result.stdout


def test_caddy_overlay_example_and_caddyfile_share_one_contract():
    import re
    from pathlib import Path

    import yaml

    repo = Path(__file__).resolve().parents[2]
    overlay = yaml.safe_load((repo / "docker-compose.caddy.yml").read_text(encoding="utf-8"))
    acme = overlay["services"]["caddy"]["environment"]["ACME_EMAIL"]
    assert acme.startswith("${ACME_EMAIL:?"), acme  # compose refuses to start the overlay without it
    assert "email {$ACME_EMAIL}" in (repo / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    example = (repo / ".env.production.example").read_text(encoding="utf-8")
    assert re.search(r"^ACME_EMAIL=$", example, re.M) and re.search(r"^DOMAIN=$", example, re.M)
    assert "ops@example.com" not in re.findall(r"^ACME_EMAIL=(.*)$", example, re.M)


# --- check-env.sh: catch-all trusted proxies -----------------------------------------------------------------------


@pytest.mark.parametrize("proxies", ["0.0.0.0/0", "::/0", "10.0.0.0/8,::/0", "10.0.0.0/8, 0.0.0.0/0",
                                     '["10.0.0.0/8","0.0.0.0/0"]', "1.2.3.4/0", "::/00"])
def test_check_env_refuses_catch_all_trusted_proxies(tmp_path, proxies):
    result = _check_env(tmp_path, _env(TRUSTED_PROXIES=proxies))
    assert result.returncode == 1 and "TRUSTED_PROXIES has no catch-all" in result.stdout


@pytest.mark.parametrize("proxies", ["10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8,::1/128,fc00::/7",
                                     "173.245.48.0/20,2400:cb00::/32", "203.0.113.5", "10.0.0.0/10", "100.64.0.0/10"])
def test_check_env_accepts_specific_trusted_proxies(tmp_path, proxies):
    result = _check_env(tmp_path, _env(TRUSTED_PROXIES=proxies))
    assert result.returncode == 0, result.stdout


def test_check_env_and_the_api_agree_on_trusted_proxies(tmp_path):
    # the same values the API refuses at startup are refused before deployment, and vice versa
    for proxies, refused in (("0.0.0.0/0", True), ("::/0", True), ("10.0.0.0/8,173.245.48.0/20", False)):
        api_refused = False
        try:
            _settings(TRUSTED_PROXIES=proxies)
        except ValueError:
            api_refused = True
        assert api_refused is refused, proxies
        assert (_check_env(tmp_path, _env(TRUSTED_PROXIES=proxies)).returncode == 1) is refused, proxies
