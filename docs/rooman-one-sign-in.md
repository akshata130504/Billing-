# Sign in with Rooman One

People signed in at Rooman One open Billing without a second password, and Billing keeps
Rooman One's ids: the id_token's `sub` is the Billing user id and its `org_id` the Billing
organization id. Billing's own email/password sign-in and sign-up are unchanged. Everything
below is **off until `OIDC_ISSUER` and `OIDC_CLIENT_ID` are set**.

## Settings (`.env.production`)

```
OIDC_ISSUER=https://roomanone.futureacad.ae
OIDC_CLIENT_ID=billing-web-...        # from the Rooman One team
OIDC_CLIENT_SECRET=...                # from the Rooman One team
OIDC_REDIRECT_URI=https://<billing host>/api/v1/auth/rooman-one/callback
```

Ask the Rooman One team to register Billing with exactly that redirect URI. Set
`SECURE_COOKIES=true` in production (the flow cookie is then `Secure`). With `REDIS_URL` set,
"use once" checks hold across workers; without it they are per process (development only).

## Flow (`/api/v1/auth/rooman-one`)

| Endpoint | What it does |
|---|---|
| `GET ""` | `{"enabled": true/false}`; the login page shows "Sign in with Rooman One" only when enabled |
| `GET /start?next=/path` | state, nonce and PKCE (S256) in a 10-minute httpOnly, SameSite=Lax cookie sealed with `SECRET_KEY`; 303 to Rooman One. `next` must be a same-origin path |
| `GET /callback` | checks state (once), exchanges the code, verifies the id_token (RS256 via JWKS, `aud`, `iss`, `exp`/`iat`, nonce), sets the person up on first sign-in, runs the login checks, then 303 to `{FRONTEND_URL}/auth/rooman-one#handoff=...` or `{FRONTEND_URL}/login?sso_error=...` |
| `POST /exchange` | redeems the encrypted 60-second hand-over **once** for the usual sign-in result: tokens, or the two-factor challenge |

Code: `backend/app/services/rooman_one_service.py`, `backend/app/api/v1/endpoints/rooman_one_login.py`,
`frontend/src/pages/auth/RoomanOneCallbackPage.tsx`. Tests: `backend/tests/test_rooman_one_login.py`.

## First sign-in

- **Unknown user, email already used in Billing:** refused ("This email already has its own Rooman
  Billing account..."). Accounts are never merged.
- **Unknown organization:** created by `auth_service.create_organization` with Rooman One's id, exactly
  like self-service sign-up (ACTIVE, free trial, `ORGANIZATION_CREATED` and
  `ORGANIZATION_TRIAL_STARTED` platform audit entries).
- **User and membership:** the user gets no password (they can add one with "Forgot password"); the
  membership is ACTIVE, and a colleague joining an existing organization takes a seat.
- **Roles:** the `admin` who creates the organization becomes `owner`; other `admin`s become `admin`,
  `staff` becomes `finance`, and `viewer` or unknown roles become `viewer`.
- **Later sign-ins:** they find the same user and membership. A deactivated user or membership is
  refused, and a user with 2FA on still gets the TOTP step.
