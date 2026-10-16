# Production migration plan: rooman-itsd/Rooman-Billing → Rooman-Billing-Modular

**Status: plan only. Do not execute without explicit approval from the owner.** Until the cutover,
`rooman-itsd/Rooman-Billing` remains the only production source, and it is the rollback.

## 0. Preconditions (evidence required before approval)

1. **Modularization done:** every module planned for this repository is merged, with CI green, including the PostgreSQL suite, migrations, drift checks, RLS as a non-superuser role, the security suite, the frontend and both Docker builds.
2. **No schema differences:** `alembic heads` here equals production's current head, or the extra migrations are listed, reviewed and reversible.
3. **Staging soak:** a staging deploy has run on this repository's images for an agreed period, with the browser QA checklist passed.
4. **Fixes carried over:** every fix merged into `rooman-itsd/Rooman-Billing` since the copy started (base `a287d17`) has been brought over. Check with `git log a287d17..upstream/main`.

## 1. Repository and deployment configuration

Two options. Option A is recommended because production images and the server don't change:

- **A. Code moves back.** Open a PR from this repository's `main` into `rooman-itsd/Rooman-Billing`, so the existing pipeline deploys it as usual. Nothing on the server changes.
- **B. The pipeline moves here.** Restore `deploy/reference/deploy.workflow.yml.txt` as `.github/workflows/deploy.yml` in this repository and publish images under this repository's owner. Then change the server's poller settings (`GITHUB_REPO`, `API_IMAGE`, `WEB_IMAGE`) and add a `GITHUB_PAT` that can read this repository.

## 2. Environment variables and secrets

- **Option A:** nothing changes.
- **Option B:**
  - The server's `.env.production` keeps every application secret as it is.
  - Only the poller variables change, plus a new **read-only** PAT for this repository.
  - Production secrets are never committed or copied into this repository's Actions secrets unless a deploy job needs them. Today it needs none: the server pulls.

## 3. Database and migration compatibility

- **Migrations run on container start.** Before the cutover, confirm a fresh migration from empty to head and an upgrade from production's head (`4c5d6e7f8091` on 2026-10-16) both work in CI and in staging.
- **Pre-deploy backup:** the existing poller keeps taking a `pg_dump` before each deploy. Confirm the dump restores before the cutover.
- **Model changes:** P1 makes no model or migration changes. Any later model move needs `alembic check` to be clean.

## 4. Authentication, integrations and external services

- **Sessions and tokens:** they carry over unchanged, because `SECRET_KEY` and `PLATFORM_JWT_SECRET` stay the same. Check sign-in for both the tenant app and the platform console.
- **Webhooks:** the Razorpay webhook URL and secret are unchanged, because the domain stays the same. Send a **test-mode** webhook in staging only.
- **Email:** the SMTP settings are unchanged. Don't send real emails during verification.
- **Allowed origins:** CORS and `FRONTEND_URL` are unchanged.

## 5. Health checks and smoke tests (read-only)

1. `GET /api/v1/health`: `healthy`, database `connected`.
2. `GET /api/v1/health/ready`: `ready: true`, migrations `at_head`, no `failures`.
3. `GET /`, `/admin`, `/superadmin`: 200. `GET /api/v1/projects` without login: 401.
4. A signed-in, read-only walk-through of Dashboard, Customers, Invoices, Payments and Projects, using an approved test account. No writes.

## 6. Rollback

- **Option A:** revert the merge PR in `rooman-itsd/Rooman-Billing`. The pipeline redeploys the previous commit, and the poller's automatic rollback (`:previous`) also applies if readiness fails.
- **Option B:** restore the poller's previous `GITHUB_REPO` / `API_IMAGE` / `WEB_IMAGE` values and redeploy the last known-good tag. The old images are still in `ghcr.io/rooman-itsd/*`.
- **Database:** restore the pre-deploy `pg_dump` only if a migration is not backward-compatible. That needs its own approval.

## 7. Verifying which commit is running in production

Today production doesn't expose its commit, and that blocked verification on 2026-10-16. Before the cutover:

- **Expose it read-only:** add the build SHA to `/api/v1/health` (for example `"revision": "<sha>"`), taken from the image label `org.opencontainers.image.revision`. That is a separate small PR with its own approval.
- **Until then:** an operator on the server compares `docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'` on the running API container, and `.deploy/deployed_sha`, with the expected commit.

## 8. Approval checklist

- [ ] Preconditions in §0 met, with evidence attached.
- [ ] Option A or B chosen.
- [ ] Revision exposed, or operator verification arranged.
- [ ] Backup restore tested.
- [ ] Rollback owner and time window agreed.
- [ ] Explicit go-ahead from the owner.
