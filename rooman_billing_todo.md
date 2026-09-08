# Rooman-Billing — Complete Implementation TODO

## PROJECT CONTEXT

- **Repository root:** `C:\projects\Rooman_Billing\Rooman-Billing`
- **Git branch:** `charan` (NEVER change this)
- **Python venv:** `.venv\Scripts\python.exe` (Windows)
- **Test runner:** `.venv\Scripts\python.exe -m pytest`
- **Master plan file:** `Rooman-Billing-Feature-Architecture-Implementation-Plan.md` (READ-ONLY — never modify or delete)
- **Feature requirement PDFs:** `C:\projects\Rooman_Billing\my_features\` (10 PDFs)
- **Current test count:** 185 passed (baseline was 110; Phase 6 added 6, Phase 7 added 6, Phase 8 added 8) — all 8 plan phases now complete

---

## CRITICAL CONSTRAINTS

1. Branch MUST remain `charan` — no switching.
2. **NO** destructive Git commands: `git reset --hard`, `git clean -fd`, `git checkout -- .`, `git restore .`
3. **NEVER** delete or modify `Rooman-Billing-Feature-Architecture-Implementation-Plan.md`
4. Zero regression: ALL existing 185 tests must pass at every step before moving forward.
5. Always run tests with `.venv\Scripts\python.exe -m pytest` on Windows.

---

## ARCHITECTURE GOTCHAS (Learned from previous implementation)

- `Subscription` requires `subscription_number` (non-nullable) and `start_date` (non-nullable).
- `CustomerPaymentMethod` column is `card_brand` (NOT `brand`).
- SQLAlchemy 2 with `joinedload` requires `.unique()` before `.all()` or `.first()`:
  ```python
  db.scalars(stmt.options(joinedload(...))).unique().all()
  ```
- SQLite dates are offset-naive; always normalize before comparing with `utcnow()`:
  ```python
  if dt and dt.tzinfo is None:
      dt = dt.replace(tzinfo=timezone.utc)
  ```
- Standard logger uses `%s` formatting, NOT keyword args (raises `TypeError`):
  ```python
  logger.info("Created %s", value)   # CORRECT
  logger.info("Created {value}")      # WRONG
  ```
- Next number sequence generator: `from backend.app.services.numbering import next_number`
- All Pydantic schemas use `model_config = ConfigDict(from_attributes=True)` for ORM mode.
- Test conftest creates all tables with `Base.metadata.create_all()` — new models MUST be imported in `backend/app/models/__init__.py`.

---

## MIGRATION CHAIN (Current)

```
base
  → 9c919cae6ade (0001_initial_baseline)
  → f34df9d017e1 (0002_phase1_shared_foundation)
  → a1b2c3d4e5f6 (0003_phase2_proration_and_metering)
  → b2c3d4e5f6a7 (0004_phase3_trial_management)
  → c3d4e5f6a7b8 (0005_phase4_hosted_checkout_and_portal)
  → d4e5f6a7b8c9 (0006_phase5_dunning_management)
  → e5f6a7b8c9d0 (0007_phase6_customization_and_automation)
  → a7b8c9d0e1f2 (0008_phase7_client_platforms)
  → b8c9d0e1f2a3 (0009_phase8_ai_billing)  ← HEAD
```

---

## COMPLETED PHASES

### Phase 0 — Production Integrity ✅ (110 → 134 tests)
- [x] Alembic baseline migration (`0001_initial_baseline.py`)
- [x] Scheduler `run_forever()` entry point fixed
- [x] Strict API router imports
- [x] Request/correlation IDs and structured logging
- [x] Migration upgrade/downgrade test (`test_migrations.py`)
- [x] Characterization tests for subscriptions, invoices, payments, webhooks, scheduler

### Phase 1 — Shared Billing Foundation ✅ (134 → 141 tests)
- [x] Unit of work pattern (`backend/app/services/unit_of_work.py`)
- [x] Command idempotency service (`backend/app/services/idempotency_service.py`)
- [x] Durable job service (`backend/app/services/durable_job_service.py`)
- [x] Domain event models (`backend/app/models/events.py`)
- [x] Billing cycle models (`backend/app/models/billing_cycles.py`)
- [x] Credit note models and service (`backend/app/models/credits.py`, `backend/app/services/credit_service.py`)
- [x] Customer payment method models and service (`backend/app/models/payments.py`, `backend/app/services/payment_method_service.py`)
- [x] Notification models and service (`backend/app/models/notifications.py`, `backend/app/services/notification_service.py`)
- [x] Gateway abstraction (`backend/app/services/gateways/`, `backend/app/services/razorpay_gateway.py`)
- [x] Migration `0002_phase1_shared_foundation.py`
- [x] Tests: `test_foundation_services.py` (7 passed)

### Phase 2 — Core Billing Behavior ✅ (141 → 146 tests)
- [x] Proration calculator (`backend/app/services/proration_calculator.py`)
- [x] Proration models (`backend/app/models/proration.py`)
- [x] Subscription change service (`backend/app/services/subscription_change_service.py`)
- [x] Meter models and service (`backend/app/models/meters.py`, `backend/app/services/meter_service.py`)
- [x] Proration schemas (`backend/app/schemas/proration.py`)
- [x] Meter schemas (`backend/app/schemas/meters.py`)
- [x] Endpoints: `subscription_changes.py`, `meters.py`
- [x] Migration `0003_phase2_proration_and_metering.py`
- [x] Tests: `test_proration.py`, `test_metered_billing.py` (5 passed)

### Phase 3 — Trial Lifecycle ✅ (146 → 152 tests)
- [x] Trial models (`backend/app/models/trials.py`)
- [x] Trial service (`backend/app/services/trial_service.py`)
- [x] Trial schemas (`backend/app/schemas/trials.py`)
- [x] Endpoints: `trials.py`
- [x] Migration `0004_phase3_trial_management.py`
- [x] Tests: `test_trial_management.py` (6 passed)

### Phase 4 — Customer-Facing Payments ✅ (152 → 157 tests)
- [x] Checkout models (`backend/app/models/checkout.py`) — `CheckoutTemplate`, `CheckoutSession`
- [x] Portal models (`backend/app/models/portal.py`) — `CustomerPortalSettings`, `CustomerPortalUser`, `CustomerPortalSession`
- [x] Checkout service (`backend/app/services/checkout_service.py`)
- [x] Customer portal service (`backend/app/services/customer_portal_service.py`)
- [x] Checkout schemas (`backend/app/schemas/checkout.py`)
- [x] Portal schemas (`backend/app/schemas/portal.py`)
- [x] Endpoints: `hosted_checkout.py`, `portal.py`
- [x] Migration `0005_phase4_hosted_checkout_and_portal.py`
- [x] Tests: `test_customer_facing_payments.py` (5 passed)

### Phase 5 — Collections & Dunning ✅ (157 → 165 tests)
- [x] Dunning models (`backend/app/models/dunning.py`) — `DunningPolicy`, `DunningCase`, `DunningAttempt`, `DunningCommunication`
- [x] Dunning service (`backend/app/services/dunning_service.py`)
- [x] Dunning schemas (`backend/app/schemas/dunning.py`)
- [x] Endpoints: `dunning.py`
- [x] Scheduler integration — `dunning_recovered` retry batch loop in `scheduler.py:run_billing_jobs`
- [x] Migration `0006_phase5_dunning_management.py`
- [x] Tests: `test_dunning_management.py` (8 passed)

---

## IN-PROGRESS & REMAINING PHASES

### Phase 6 — Customization and Automation ✅ (165 → 171 tests)

**What's DONE:**
- [x] Models created (`backend/app/models/customization.py`):
  - `TransactionNumberSeries`, `DocumentTemplate`, `ReportingTag`, `WebTab`
  - `AutomationRule`, `AutomationAction`, `OutboundWebhookDelivery`
  - `AutomationLog`, `AutomationSchedule`
  - Enums: `TemplateLayoutType`, `DocumentType`, `AutomationTriggerEvent`, `AutomationActionType`, `AutomationLogStatus`, `ScheduleFrequency`
- [x] Models exported in `backend/app/models/__init__.py`
- [x] Migration created: `e5f6a7b8c9d0_0007_phase6_customization_and_automation.py` (verified ✅)
- [x] Schemas created (`backend/app/schemas/customization.py`):
  - Number series: `TransactionNumberSeriesCreate/Update/Out`, `NumberSeriesPreviewRequest/Response`
  - Document templates: `DocumentTemplateCreate/Update/Out`, `DocumentTemplatePreviewResponse`
  - Reporting tags: `ReportingTagCreate/Update/Out`
  - Web tabs: `WebTabCreate/Update/Out`
  - Automation rules: `AutomationRuleCreate/Update/Out`, `AutomationActionCreate/Out`
  - Webhook deliveries: `OutboundWebhookDeliveryOut`
  - Automation logs: `AutomationLogOut`
  - Automation schedules: `AutomationScheduleCreate/Update/Out`, `ScheduleTriggerResponse`
- [x] **Service built** (`backend/app/services/customization_service.py`):
  - Number series: `{YYYY}`/`{MM}`/`{DD}` token resolution, `format_series_number`, `preview_number_series`, `reserve_next_number` / `reserve_next_number_for_module` (atomic increment), default-per-module toggling
  - Document templates: default-per-document_type toggling, `render_template_preview` (HTML + text)
  - Automation engine: `rule_matches`/`find_matching_rules`/`process_automation_event`, `execute_automation_action` (email_alert via notification_service, webhook via simulated `OutboundWebhookDelivery`, field_update), `test_rule` dry-run, logging to `automation_logs`
  - Webhook delivery: simulated attempt (`simulate_failure` config flag for deterministic tests), `retry_webhook_delivery`
  - Schedules: `compute_next_schedule_date`, `trigger_schedule` (advances `next_date`, records `last_executed_on`)
- [x] **API Router built** (`backend/app/api/v1/endpoints/customization.py`) — all CRUD + preview/test/trigger/retry endpoints listed above, registered in `backend/app/api/v1/api_router.py`
- [x] **Tests written** (`backend/tests/test_customization_and_automation.py`) — 6 tests, all green:
  - Number series token resolution & next-number generation (incl. default-series demotion)
  - Template default selection per document_type & preview rendering
  - Automation rule condition matching dry-run (`/test` endpoint)
  - Automation engine action execution (webhook + field_update) & log recording
  - Webhook delivery failure + retry recovery (+ reject retry on already-delivered)
  - Schedule creation, manual trigger, `next_date` advancement
- [x] **Full suite run** — 171 passed (165 baseline + 6 new), zero regressions

---

### Phase 7 — Client Platforms ✅ (171 → 177 tests)

> **Plan Reference:** Section 9.4 (Desktop) and 9.8 (Mobile)
> **PDF sources:** `Desktop.pdf`, `Mobile.pdf` — both read; scope narrowed to the shared backend surface
> (device registration/trust, native auth exchange, mobile bootstrap) per the plan's "thin online shell
> first, defer offline mutation support" guidance. Timer/expense/mileage/receipt endpoints from the PDFs
> depend on Projects/Expenses modules that do not exist in this codebase yet, so they are out of scope.

- [x] Read `Desktop.pdf` and `Mobile.pdf`
- [x] Read Plan Sections 9.4 and 9.8

**Backend work:**
- [x] `Device` model (`backend/app/models/devices.py`): `organization_id`, `user_id`, `device_identifier`
  (client-generated, unique per user), `device_name`, `platform` (windows/macos/android/ios), `os_version`,
  `app_version`, `push_token`, `trust_status` (pending/trusted/revoked), `last_seen_at`, `trusted_at`,
  `revoked_at`, `revoked_reason`
- [x] Migration `a7b8c9d0e1f2_0008_phase7_client_platforms.py` (down-revision `e5f6a7b8c9d0`, verified via
  `test_migrations.py` upgrade → downgrade → re-upgrade)
- [x] Schemas (`backend/app/schemas/devices.py`): `DeviceRegisterIn/Out`, `NativeExchangeRequest/Response`,
  `MobileBootstrapOut` (reuses `UserOut`/`OrganizationOut`/`MembershipOut`/`OrganizationSummary` from
  `schemas/auth.py` and `schemas/organization.py`)
- [x] Service (`backend/app/services/device_service.py`):
  - `register_device`/`list_devices`/`get_device`/`revoke_device` — registering an already-authenticated
    user's own device trusts it immediately (no separate approval step in this MVP); re-registering the
    same `device_identifier` refreshes it; revoked identifiers cannot be re-registered
  - `exchange_native_credentials` — reuses `auth_service.login` for the OAuth-style exchange, decodes the
    issued access token for `user_id`/`organization_id`, then registers the device in the same call
  - `build_mobile_bootstrap` — wraps `auth_service.build_me` plus `server_time`
- [x] Endpoints (`backend/app/api/v1/endpoints/devices.py`), registered in `api_router.py`:
  - `POST /auth/native/exchange` (rate-limited like `/auth/login`)
  - `POST /devices`, `GET /devices`, `DELETE /devices/{id}`
  - `GET /mobile/bootstrap`
- [x] Tests (`backend/tests/test_client_platforms.py`) — 6 tests, all green: trusted registration +
  idempotent re-registration, per-caller device listing isolation, revoke blocks re-registration under the
  same identifier, native exchange (success + bad-password 401), mobile bootstrap contents
- [x] Full suite run — 177 passed (171 baseline + 6 new), zero regressions

---

### Phase 8 — AI in Billing ✅ (177 → 185 tests) — LAST PHASE, PLAN COMPLETE

> **Plan Reference:** Section 9.1
> **PDF source:** `AI in billing .pdf` — read in full (Ask Zia, CoCreate, Writing Assistant, Zia
> Insights/Forecasting/Anomaly Detection, receivables risk signals, voice input, Zoho MCP,
> human-in-the-loop, data privacy)
>
> **Scope decision:** No external LLM provider is wired into this deployment — Plan §4.1 explicitly
> marks "model provider" as **UNSPECIFIED / REQUIRES PRODUCT DECISION**. Implemented a deterministic,
> in-house "AI": a keyword intent classifier over a fixed set of grounded query tools, plus
> template-based text generation — reproducible in tests with no network calls, consistent with how
> other phases simulate external integrations (webhook delivery, SMS dispatch). `AIRequest` carries
> `model_provider`/`model_name` fields so a real provider can be plugged in later without a schema
> change. CoCreate-equivalent drafting is scoped to **one concrete domain command — credit notes**
> (via the existing `credit_service.create_credit_note`) to prove the propose → re-validate → confirm
> → execute-via-domain-service pattern end to end, rather than reimplementing draft support for every
> transaction type (quotes/invoices/subscriptions) PDF-mentions; `AIActionType` stays a single-value
> enum for now, extendable later.

- [x] Read `AI in billing .pdf` and Plan Section 9.1

**Backend work:**
- [x] AI models (`backend/app/models/ai.py`):
  - `AIConversation` — session/thread tracking
  - `AIRequest` — individual query/draft/writing requests with `model_provider`/`model_name` metadata
  - `AISourceReference` — grounding/attribution references (invoice/report cited per answer)
  - `AIToolInvocation` — tool calls made during query processing
  - `AIActionDraft` — proposed actions requiring confirmation (states: proposed/validated →
    executed/rejected/expired; `approved` reserved for a future explicit approval step)
- [x] Migration `b8c9d0e1f2a3_0009_phase8_ai_billing.py` (down-revision `a7b8c9d0e1f2`, verified via
  `test_migrations.py` upgrade → downgrade → re-upgrade)
- [x] Schemas (`backend/app/schemas/ai.py`): `AIQueryRequest/Response`, `AIDraftRequest`,
  `AIDraftResponse`/`AIDraftConfirmResponse` (confirm takes only a path param, no request body needed),
  `AIWritingRequest/Response`, `AIHistoryOut`
- [x] Service (`backend/app/services/ai_service.py`):
  - `answer_query` — keyword-classifies the prompt into one of four grounded tools (outstanding
    balance, overdue invoice count, invoices beyond the org's average late-payment cycle — mirrors
    the PDF's worked example exactly, MRR summary), each returning an answer + numeric data +
    `AISourceReference` rows
  - `propose_draft` / `confirm_draft` — structural validation at proposal time (customer/invoice
    existence, ownership) and **re-validation at confirmation time** (stale-data check) before calling
    `credit_service.create_credit_note` — AI never writes to billing tables directly; drafts expire
    after 30 minutes and cannot be confirmed once expired or already executed
  - `generate_writing` — tone-adjusted (`friendly`/`firm`/`neutral`) payment-reminder and generic note
    drafting
  - `list_history` — tenant + mode filtered activity log
  - Every query/draft/confirm/writing call is recorded via the existing `audit` service
  - Forecasting/anomaly detection were left out of scope — Plan §9.1 lists them as informational,
    lower-priority additions, and no forecasting/statistics infrastructure exists yet to ground them
- [x] Endpoints (`backend/app/api/v1/endpoints/ai.py`), registered in `api_router.py`:
  - `POST /ai/queries` (viewer role — read-only)
  - `POST /ai/drafts`, `POST /ai/drafts/{id}/confirm` (finance role — money-affecting)
  - `POST /ai/writing` (viewer role)
  - `GET /ai/history` (viewer role)
- [x] Tests (`backend/tests/test_ai_billing.py`) — 8 tests, all green:
  - Outstanding-balance and overdue-count queries against known invoice data
  - Overdue-invoices-beyond-average-cycle query (average computed from 3 overdue invoices, exactly
    one exceeds it — matches the PDF's worked example shape)
  - Draft proposal rejects a nonexistent customer (structured validation) while still persisting the
    rejected draft for audit history
  - Draft propose → confirm executes a real credit note via `credit_service`, confirming twice is
    rejected, both steps are audit-logged
  - Confirming an expired draft is rejected and flips its status to `expired`
  - Viewer role is forbidden from proposing drafts (finance-only)
  - Cross-organization isolation: org B sees no history from org A and cannot confirm org A's draft
  - Writing Assistant produces the expected tone-adjusted reminder; history filters by mode
- [x] Full suite run — 185 passed (177 baseline + 8 new), zero regressions

**Phase 8 was the final phase in `Rooman-Billing-Feature-Architecture-Implementation-Plan.md`.
All 8 planned phases (0–8) are now complete.**

---

## FILE REFERENCE MAP

### Models (all in `backend/app/models/`)
| File | Purpose | Phase |
|------|---------|-------|
| `identity.py` | Users, Organizations, Memberships | Pre-existing |
| `customers.py` | Customers, Contacts | Pre-existing |
| `catalog.py` | Products, Plans | Pre-existing |
| `subscriptions.py` | Subscriptions | Pre-existing |
| `invoices.py` | Invoices, InvoiceLines | Pre-existing |
| `payments.py` | Payments, PaymentAllocations, Refunds, CustomerPaymentMethod, PaymentAttempt | Pre-existing + P1 |
| `quotes.py` | Quotes, QuoteLines | Pre-existing |
| `governance.py` | AuditLogs, Approvals | Pre-existing |
| `events.py` | DomainEvent, InboxEvent, OutboxEvent, DurableJob | P1 |
| `billing_cycles.py` | BillingCycle, PriceSnapshot, SubscriptionItem | P1 |
| `credits.py` | CreditNote, CreditNoteLine, CreditApplication | P1 |
| `notifications.py` | NotificationTemplate, NotificationDelivery | P1 |
| `proration.py` | SubscriptionChange, ProrationAdjustment | P2 |
| `meters.py` | UsageMeter, UsageEvent, UsageAggregate | P2 |
| `trials.py` | TrialPeriod, TrialExtension, TrialConversionAttempt, TrialPolicy | P3 |
| `checkout.py` | CheckoutTemplate, CheckoutSession | P4 |
| `portal.py` | CustomerPortalSettings, CustomerPortalUser, CustomerPortalSession | P4 |
| `dunning.py` | DunningPolicy, DunningCase, DunningAttempt, DunningCommunication | P5 |
| `customization.py` | TransactionNumberSeries, DocumentTemplate, ReportingTag, WebTab, AutomationRule, AutomationAction, OutboundWebhookDelivery, AutomationLog, AutomationSchedule | P6 |
| `devices.py` | Device (client platform registration/trust) | P7 |
| `ai.py` | AIConversation, AIRequest, AISourceReference, AIToolInvocation, AIActionDraft | P8 |

### Services (all in `backend/app/services/`)
| File | Purpose | Phase |
|------|---------|-------|
| `unit_of_work.py` | Transaction boundary management | P1 |
| `idempotency_service.py` | Command idempotency | P1 |
| `durable_job_service.py` | Durable job execution | P1 |
| `credit_service.py` | Credit notes & applications | P1 |
| `payment_method_service.py` | Customer payment methods | P1 |
| `notification_service.py` | Notification templates & delivery | P1 |
| `proration_calculator.py` | Pure proration calculations | P2 |
| `subscription_change_service.py` | Subscription change preview/apply | P2 |
| `meter_service.py` | Usage meters, events, aggregation | P2 |
| `trial_service.py` | Trial lifecycle management | P3 |
| `checkout_service.py` | Hosted checkout sessions | P4 |
| `customer_portal_service.py` | Customer portal | P4 |
| `dunning_service.py` | Dunning policies, cases, retries | P5 |
| `customization_service.py` | Number series, templates, automation engine | P6 |
| `device_service.py` | Device registration/trust, native auth exchange, mobile bootstrap | P7 |
| `ai_service.py` | AI queries, credit-note drafting, writing assistant, history | P8 |

### Schemas (all in `backend/app/schemas/`)
| File | Phase |
|------|-------|
| `customization.py` | P6 ✅ Created |
| `devices.py` | P7 ✅ Built |
| `ai.py` | P8 ✅ Built |

### Endpoints (all in `backend/app/api/v1/endpoints/`)
| File | Phase |
|------|-------|
| `customization.py` | P6 ✅ Built |
| `devices.py` | P7 ✅ Built |
| `ai.py` | P8 ✅ Built |

### Tests (all in `backend/tests/`)
| File | Phase |
|------|-------|
| `test_customization_and_automation.py` | P6 ✅ 6 tests passing |
| `test_client_platforms.py` | P7 ✅ 6 tests passing |
| `test_ai_billing.py` | P8 ✅ 8 tests passing |

---

## EXECUTION CHECKLIST — ALL 8 PLAN PHASES COMPLETE

Phases 0 through 8 are all done (see the phase-by-phase sections above). There is no remaining
phase in `Rooman-Billing-Feature-Architecture-Implementation-Plan.md`'s Section 11 implementation
order. Remaining work, if any, is discretionary hardening rather than a scoped next phase:

- The plan's PDFs describe several capabilities that were explicitly scoped out of the backend-only
  MVP implemented here (frontend UI for every module remains mostly `ComingSoonPage` placeholders per
  Plan §2 "Frontend"; Desktop/Mobile native shells were not built, only the shared device/auth/bootstrap
  backend surface per Plan §9.4/§9.8; AI drafting covers credit notes only, not the full
  quote/invoice/subscription set CoCreate supports per Plan §9.1).
- If continuing, prioritize per Plan §11: frontend implementation of the now-complete backend APIs,
  then the scoped-out draft action types, then native client shells.

---

## HOW TO VERIFY THE FULL BACKEND

```bash
# Run the full test suite (MUST pass 185+ tests — the current regression baseline)
.venv\Scripts\python.exe -m pytest

# Verify the full migration chain (0001 -> 0009) upgrades and downgrades cleanly
.venv\Scripts\python.exe -m pytest backend/tests/test_migrations.py

# Run any single phase's test file, e.g.:
.venv\Scripts\python.exe -m pytest backend/tests/test_ai_billing.py -v
```
