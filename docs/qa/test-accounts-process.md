# Test accounts needed to finish role verification

The production audit of release `6dbf7d1` tested 5 of the 8 roles. These three are still **BLOCKED** because no account exists:

| Role | Kind | How accounts are created | Why it is blocked |
|---|---|---|---|
| **Viewer** | Tenant member | An Owner or Admin invites the user (Settings → Users & Roles → Invite member, role Viewer). The person accepts the emailed link and sets a password. | Two invitation emails to the QA inbox never arrived (BUG-26), and the QA org is at its seat limit (4/4). |
| **Platform Operations** | Platform staff (`platform_operations`) | **Only by the server-side CLI.** There is no API or console form, by design. | No such account exists. |
| **Platform Support** | Platform staff (`platform_support`) | As above, with role `platform_support`. | No such account exists. |

## Safe procedure

### Viewer
1. Free a seat in the QA org. Either deactivate the pending, never-accepted Viewer invite (Users & Roles), or have a Platform Administrator raise the QA org's seat limit by one via Change plan (needs password confirmation; audited).
2. Invite a dedicated QA address as **Viewer** from the QA org's Owner account.
3. The inbox owner opens the email and accepts. If the email does not arrive, check spam/quarantine. If it is truly missing, the server owner checks the SMTP logs for that address (this is also BUG-26).
4. Remove or deactivate the account after testing.

### Platform Operations and Support
Only someone with shell access to the production backend container can do this, following `docs/deployment.md`:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml exec backend \
  python -m backend.app.cli.platform_staff create \
  --email <qa-ops-address> --name "QA Operations" --role platform_operations --password-stdin
# repeat with --role platform_support
```

- The password is read from stdin. **Never pass it on the command line or in chat.** The CLI never prints secrets (covered by `test_platform_staff_cli.py`).
- Use dedicated QA addresses, record the accounts as test accounts, and deactivate them after the audit (Platform staff page, Administrator only).

## Authorisation needed
- **Platform staff:** creating staff accounts gives access to the platform console, so it needs explicit approval from the product owner and the server owner.
- **Tenant Viewer:** affects only the QA organization.

## What will be verified once the accounts exist

| Role | Checks |
|---|---|
| Viewer | Read-only on every module. Every create/edit/delete/send/approve is refused by the API (403), not just hidden. Direct URLs. |
| Operations / Support | Read-only console access. Approve/reject subscription requests, Create Admin, suspend/reactivate, plan change, visual editor publish and staff management are all refused (403). Audit entries show their actor. |
