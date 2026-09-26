# Rooman Billing — Email & SMTP Configuration Guide

This guide covers outbound email configuration in Rooman Billing for both **local development** and **production deployment**.

---

## 1. Architecture Overview

Rooman Billing features a dual-layer SMTP architecture:

1. **System-Wide Fallback (`backend/.env` or container environment)**:
   - Configured via `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_USE_SSL`, `EMAIL_FROM_ADDRESS`, and `EMAIL_FROM_NAME`.
   - Used automatically whenever a tenant has not configured custom SMTP credentials.
   - When `SMTP_HOST` is left empty, email sending is safely disabled; invitation and password reset links are returned directly to the admin in the API/UI.

2. **Tenant-Level Custom SMTP (`Settings -> Integrations -> Custom SMTP Server`)**:
   - Each organization can configure their own custom SMTP server via the UI or API.
   - Stored in the `organization_integrations` table with **AES-128 Fernet encryption at rest** derived from the server `SECRET_KEY`.
   - Passwords and keys are **strictly masked and redacted**: they are never returned in plaintext in API responses, logs, or frontend state.

---

## 2. Local Development Configuration

For local development, Rooman Billing supports two zero-cost testing methods without sending emails to the real internet:

### Option A: Built-in Python SMTP Mock Server (Default)
Rooman Billing includes a local RFC 5321 mock SMTP listener:
```bash
python scripts/local_smtp_server.py
```
- Listens on `127.0.0.1:1025`.
- Accepts all standard SMTP commands (`HELO`, `EHLO`, `AUTH LOGIN/PLAIN`, `MAIL FROM`, `RCPT TO`, `DATA`, `RSET`, `QUIT`).
- Logs message size and recipient details to the console without routing to the internet.

**`backend/.env` for Local Mock:**
```env
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=false
SMTP_USE_SSL=false
EMAIL_FROM_ADDRESS=billing@rooman.com
EMAIL_FROM_NAME="Rooman Billing"
```

### Option B: Mailpit (with Web UI)
If Docker Desktop is available:
```bash
docker run -d --name mailpit -p 1025:1025 -p 8025:8025 axllent/mailpit
```
- SMTP endpoint: `localhost:1025`
- Web inbox UI: `http://localhost:8025`

---

## 3. Production SMTP Configuration

In production, you connect Rooman Billing to an established transactional email service provider.

### Supported Providers & Connection Details

| Provider | Host | Port | TLS / SSL | Username | Password / API Key |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **Brevo (Sendinblue)** | `smtp-relay.brevo.com` | `587` | STARTTLS (`use_tls=true`) | Your Brevo account email | Brevo SMTP Master Key |
| **SendGrid** | `smtp.sendgrid.net` | `587` | STARTTLS (`use_tls=true`) | `apikey` | SendGrid API Key (`SG....`) |
| **Amazon SES** | `email-smtp.<region>.amazonaws.com` | `587` | STARTTLS (`use_tls=true`) | SES SMTP Username | SES SMTP Password |
| **Mailgun** | `smtp.mailgun.org` | `587` | STARTTLS (`use_tls=true`) | `postmaster@<domain>` | Mailgun SMTP password |
| **Postmark** | `smtp.postmarkapp.com` | `587` | STARTTLS (`use_tls=true`) | Server API Token | Server API Token |
| **Google Workspace** | `smtp.gmail.com` | `587` | STARTTLS (`use_tls=true`) | Your Google email | 16-char Google App Password |

### Production Environment Variables (`.env.production`)
```env
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=<your-sendgrid-api-key>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
EMAIL_FROM_ADDRESS=billing@yourcompany.com
EMAIL_FROM_NAME="Rooman Billing"
```

> **Note on TLS vs. SSL:**
> - Port `587` requires `SMTP_USE_TLS=true` and `SMTP_USE_SSL=false` (STARTTLS).
> - Port `465` requires `SMTP_USE_SSL=true` and `SMTP_USE_TLS=false` (Implicit SSL).
> - Never set both to `true`.

---

## 4. Domain Verification & Anti-Spam (SPF, DKIM, DMARC)

To prevent customer emails (invoices, receipts, reset links) from landing in spam or being rejected by Gmail/Outlook, the sending domain must be verified in external DNS.

### Step 1: SPF (Sender Policy Framework)
Add or update the TXT record on your root domain:
```text
Host:   @
Type:   TXT
Value:  v=spf1 include:sendgrid.net ~all
```
*(Replace `include:sendgrid.net` with your provider's specific include directive, e.g. `include:spf.brevo.com` or `include:amazonses.com`)*.

### Step 2: DKIM (DomainKeys Identified Mail)
Generate DKIM keys in your mail provider dashboard and add the corresponding CNAME or TXT records to your DNS:
```text
Host:   s1._domainkey.yourcompany.com
Type:   CNAME
Value:  s1.domainkey.u12345.sendgrid.net
```

### Step 3: DMARC (Domain-based Message Authentication)
Add a TXT record to declare your alignment policy:
```text
Host:   _dmarc.yourcompany.com
Type:   TXT
Value:  v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@yourcompany.com; pct=100
```

---

## 5. How to Test a Real Email

### Via UI:
1. Log in as an Administrator and go to **Settings -> Integrations**.
2. Click **Configure** on **Custom SMTP Server**.
3. Enter your provider's Host, Port, Username, Password, and From Email.
4. Click **Test Connection**:
   - Performs a live TCP handshake and checks authentication credentials with the mail server.
5. In the **Send Test Email** section:
   - Enter your personal or work email address.
   - Click **Send Test Email**.
   - Check your inbox (including spam folder) for the verification message.
6. Click **Save & Connect** to persist the encrypted configuration.

### Via API:
```bash
curl -X POST http://localhost:8000/api/v1/settings/integrations/smtp/test-email \
  -H "Authorization: Bearer <ADMIN_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"recipient_email": "your-email@example.com"}'
```

---

## 6. Troubleshooting SMTP Failures

| Error Message | Common Cause | Solution |
| :--- | :--- | :--- |
| `535 Authentication failed` | Incorrect username, password, or API key. | Verify credentials. For Gmail, use an App Password, not your account login password. |
| `Connection timed out` | Port blocked by host firewall or cloud provider. | Many cloud hosts (AWS EC2, DigitalOcean) block outbound port 25. Ensure you are using port `587` or `465`. |
| `STARTTLS extension not supported` | Connecting to an SSL-only port with `use_tls=true`. | If using port 465, switch to `use_ssl=true` and `use_tls=false`. |
| `550 5.7.1 Relaying denied / Sender rejected` | Sender email domain not verified in provider dashboard. | Verify the domain in your email provider's console and ensure `from_email` matches. |
| `Connection unexpectedly closed` | TLS/SSL handshake mismatch. | Check provider documentation for whether port 587 (STARTTLS) or 465 (SSL) is expected. |
