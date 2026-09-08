# Rooman Billing — Feature Architecture & Implementation Plan

## 1. Executive Summary

Rooman Billing has a useful backend foundation: multi-tenant organizations, role-based membership, customers, products/plans, quotes, subscriptions, invoices, payments, refunds, approvals, audit logs, imports, public invoice payment, and Razorpay integration.

It is not yet structurally ready for the ten planned capabilities. The main limitations are:

- Subscriptions contain one plan and one quantity; there are no subscription items, add-ons, immutable price snapshots, usage meters, or structured change history.
- Billing work is performed by a fragile scheduler with incomplete production wiring.
- Payment “methods” are transaction channels, not reusable tokenized customer payment methods.
- There are no payment-attempt, credit-note, credit-application, dunning-policy, checkout-session, notification-delivery, workflow-run, or outbox models.
- Services frequently commit internally, preventing reliable multi-step billing transactions.
- The Alembic revision directory is empty.
- Most core frontend pages are placeholders despite backend APIs existing.
- Existing tests do not materially cover subscriptions, invoices, payments, webhooks, scheduled billing, concurrency, or frontend behavior.

The recommended target is a modular monolith—not microservices—with:

1. PostgreSQL as the transactional source of truth.
2. Explicit billing-domain modules.
3. Application services owning transaction boundaries.
4. Pure, deterministic money/proration/usage calculators.
5. A transactional outbox and PostgreSQL-backed durable jobs.
6. Idempotent commands, gateway calls, webhook consumption, and scheduled work.
7. Immutable price, usage, proration, and invoice evidence.
8. Shared payment-method, notification, audit, and authorization foundations.
9. Responsive web functionality before native mobile/desktop shells.
10. AI added last, using permissioned domain tools rather than direct database or money manipulation.

No files were modified, no tests were rerun, and no Git operations were performed.

---

## 2. Current Rooman Billing Architecture

### Backend

The backend is a FastAPI application using synchronous SQLAlchemy 2, Pydantic v2, PostgreSQL, Alembic configuration, APScheduler, ReportLab, SMTP, and Razorpay.

Verified structural points:

- Application composition, middleware, error handling, CORS, rate limiting, and optional scheduler lifecycle are in [main.py](C:/projects/Rooman_Billing/Rooman-Billing/backend/app/main.py).
- API modules are dynamically imported with `STRICT = False` in [api_router.py](C:/projects/Rooman_Billing/Rooman-Billing/backend/app/api/v1/api_router.py:39). Missing endpoint modules can therefore be silently skipped.
- Core models cover identity, customers, catalog, quotes, subscriptions, invoices, payments, approvals, audit records, and imports.
- Services contain most business behavior and database access.
- A generic repository exists, but production services mostly query SQLAlchemy directly and commit internally.
- Monetary values use `Decimal`/`NUMERIC`, which is the correct base.
- Invoice calculation is reasonably centralized, but supports only relatively simple percentage tax and invoice discount behavior.

### Identity and tenancy

The system includes:

- Global users.
- Organizations with billing defaults and numbering counters.
- Memberships with owner, admin, finance, and viewer roles.
- Organization-aware request context.
- JWT access tokens and rotating opaque refresh tokens.
- Invitations and password-reset tokens.
- Tenant filtering in most application services.

The role hierarchy is useful but too coarse for future functions such as AI actions, workflow administration, dunning policy changes, refunds, portal impersonation, payment-method access, and invoice finalization.

The frontend stores access and refresh tokens in `localStorage` in [apiClient.ts](C:/projects/Rooman_Billing/Rooman-Billing/frontend/src/services/apiClient.ts:28). That increases the impact of an XSS issue and should be redesigned before exposing more financial workflows.

### Catalog and subscriptions

`Product` and `Plan` support:

- Goods, services, and subscription products.
- One-time, monthly, quarterly, semiannual, and yearly intervals.
- Flat and per-unit pricing.
- Setup fees and trial days.
- Organization-scoped codes and SKUs.

A subscription references exactly one plan and one integer quantity in [subscriptions.py](C:/projects/Rooman_Billing/Rooman-Billing/backend/app/models/subscriptions.py:19). It cannot represent:

- Multiple recurring components.
- Add-ons.
- Versioned pricing.
- Metered components.
- Mixed fixed and usage charges.
- Multiple quantities or units.
- Per-item trial or proration evidence.

Current states are `trialing`, `active`, `past_due`, `paused`, and `cancelled`.

### Invoices, payments, and webhooks

Invoices support draft, sent, partially paid, paid, overdue, and void states. They have line items, tax/discount totals, public tokens, due dates, subscription-period dates, reminders, payments, and PDF generation.

Payments support:

- Manual and Razorpay collection.
- Payment allocations.
- Refunds.
- Gateway order/payment references.
- Webhook signature verification and event deduplication.

However, `PaymentMethod` in [payments.py](C:/projects/Rooman_Billing/Rooman-Billing/backend/app/models/payments.py:11) is an enum describing transaction channels such as cash, card, UPI, or cheque. It is not a stored customer payment instrument. A separate `CustomerPaymentMethod` entity is required.

Webhook events are recorded, but failures are acknowledged to the provider without a durable internal retry/dead-letter process.

### Scheduler and asynchronous work

[Scheduler processing](C:/projects/Rooman_Billing/Rooman-Billing/backend/app/services/scheduler.py) currently:

- Converts ended trials.
- Renews active subscriptions.
- Marks invoices overdue.
- Sends fixed-interval overdue reminders.

Rows are processed and committed individually. There is no job record, lease, retry policy, or database-level claim mechanism.

More critically, [docker-compose.prod.yml](C:/projects/Rooman_Billing/Rooman-Billing/docker-compose.prod.yml:82) invokes `run_forever()`, but the scheduler module exports only `run_billing_jobs`, `start_scheduler`, and `stop_scheduler`. The documented production scheduler command cannot start as written.

### Database migrations

`backend/alembic/versions` contains only `.gitkeep`. Tests construct tables with `Base.metadata.create_all()` in [conftest.py](C:/projects/Rooman_Billing/Rooman-Billing/backend/tests/conftest.py:37).

This is a critical release blocker. A production billing product cannot safely evolve without reviewed, repeatable, reversible database revisions and PostgreSQL migration tests.

### Frontend

The frontend uses React 18, TypeScript, Vite, React Router, TanStack Query, Axios, and Tailwind.

The navigation and route system already reserve product areas, but the feature routes for usage, proration, dunning, customer portal, hosted payment pages, AI, automation, customization, mobile, and desktop render `ComingSoonPage` in [routes/index.tsx](C:/projects/Rooman_Billing/Rooman-Billing/frontend/src/routes/index.tsx:223).

Several supposedly core screens—customers, catalog, quotes, invoices, payments, subscriptions, trials, public payment, and public quote pages—are also placeholders. Projects and expenses persist mock/local data rather than using production backend APIs.

`frontend/package.json` contains TypeScript build/lint commands but no unit, component, or end-to-end test framework.

### Documentation drift

The repository documentation is helpful but not authoritative. Examples of drift include:

- Documentation claims a `run_forever()` scheduler entry point exists.
- Architecture documentation describes a repository layer more consistently than the implementation uses it.
- API documentation lists core frontend pages that are currently placeholders.
- The deployment process assumes migrations, although there are no actual Alembic revisions.

---

## 3. Current Baseline and Test Status

The supplied baseline is authoritative for this planning task:

- 110 tests collected.
- 110 tests passed.
- 41 warnings.
- Command previously used: `python -m pytest`.

I did not rerun it.

Visible tests cover approvals, audit logs, authentication, catalog, customers, health, imports, quotes, search, and teams. There are no dedicated visible test modules for:

- Subscriptions.
- Trials.
- Invoices.
- Payments and allocations.
- Refund lifecycle.
- Razorpay webhook behavior.
- Scheduler behavior.
- Concurrency or idempotency.
- Frontend components and workflows.
- PostgreSQL migration behavior.

Therefore, “110 passed” is a valuable regression baseline, but not evidence that the existing billing lifecycle is comprehensively verified.

---

## 4. Our 10 Feature Requirements

### 4.1 AI in Billing

The requirement describes a Zia-like AI umbrella:

- Natural-language querying over billing data.
- Co-creation of transactions from text or voice.
- Writing assistance for email, notes, and templates.
- Business insights and receivables prioritization.
- Forecast ranges and anomaly detection.
- Permissioned external AI access.
- Visible review and human confirmation before consequential actions.
- Explainable, source-grounded outputs and AI action history.

Model provider, retention, training/privacy policy, exact compliance requirements, and which actions AI may execute are **UNSPECIFIED / REQUIRES PRODUCT DECISION**.

:codex-file-citation{path="C:\projects\Rooman_Billing\my_features\AI in billing .pdf" purpose="source"}

### 4.2 Customer Portal

The confirmed requirements include:

- Branded portal URL and banner.
- Customer/contact access and invitations.
- Optional self-signup.
- MFA.
- Profile, address, document, project, and timesheet controls.
- Payment-method saving/default behavior.
- Duplicate pending-payment prevention.
- Comment and forwarding visibility rules.
- Invoice/estimate identity verification.
- Trial extension and early activation behavior.

Detailed cancellation, pause/resume, payment, and advanced subscription-management tabs are not fully specified by the PDF and must not be treated as confirmed.

:codex-file-citation{path="C:\projects\Rooman_Billing\my_features\Customer Portal.pdf" purpose="source"}

### 4.3 Customization and Automation

This groups eleven capabilities:

- Transaction number series.
- PDF/document templates.
- Digital signatures.
- Workflow actions.
- Workflow logs.
- Schedules.
- Hosted payment page settings.
- Email notification customization.
- SMS notification customization.
- Reporting tags.
- Web tabs.

The screenshots confirm uneven levels of detail. Exact multiple-series selection, template-editor rules, digital-signature standards, workflow condition grammar, retry behavior, SMS provider, reporting-tag semantics, and web-tab security are partly **UNSPECIFIED / REQUIRES PRODUCT DECISION**.

:codex-file-citation{path="C:\projects\Rooman_Billing\my_features\Customization and Automation.pdf" purpose="source"}

### 4.4 Desktop

The specification calls for Windows and macOS applications with:

- Native windows and multi-window operation.
- OS biometric authentication.
- Keyboard shortcuts.
- Dashboard and billing modules.
- Customers, quotes, invoices, subscriptions, expenses, projects, and payments.
- Retail tax invoicing.
- Digital signatures.
- Customer history and payment patterns.
- Automated reminders.

Offline operation, conflict resolution, jump lists, exact packaging/update mechanisms, and platform-specific differences are **UNSPECIFIED / REQUIRES PRODUCT DECISION**.

:codex-file-citation{path="C:\projects\Rooman_Billing\my_features\Desktop.pdf" purpose="source"}

### 4.5 Dunning Management

The requirement separates:

- Autocharge subscription failures.
- Non-autocharge past-due handling.
- One-time overdue invoices.
- Policy criteria/segments.
- Notifications.
- Up to three retries over no more than 30 days.
- Final actions.
- Pause, resume, and stop.
- Reactivation.
- Expiring-card notices.
- Recovery reporting.

Failure-category-specific retry schedules, SMS/push support, intelligent timing, and provider retry semantics need product decisions.

:codex-file-citation{path="C:\projects\Rooman_Billing\my_features\Dunning Management.pdf" purpose="source"}

### 4.6 Hosted Payment Pages

The requirement covers hosted checkout for:

- New subscriptions.
- Subscription updates.
- Card/payment-method updates.
- One-time add-ons.
- Adding a payment method.
- Invoice payment.

It also includes template branding, multi-page/single-page layouts, configurable fields, localized messages, expiry, redirects, abandoned-cart reminders, analytics integrations, QR/link/embed distribution, responsive layout, and automatic synchronization of resulting billing records.

:codex-file-citation{path="C:\projects\Rooman_Billing\my_features\Hosted Payment Pages.pdf" purpose="source"}

### 4.7 Metered Billing

The core flow is:

> measure → record → calculate → invoice → collect

Requirements include fixed subscription charges plus actual usage, manual/API usage ingestion, and renewal invoices held pending while usage is finalized.

Aggregation methods, late events, corrections, dimensions, rate tiers, idempotency semantics, cutoff times, precision, minimums, and volume/package pricing are **UNSPECIFIED / REQUIRES PRODUCT DECISION**.

:codex-file-citation{path="C:\projects\Rooman_Billing\my_features\Metered Billing.pdf" purpose="source"}

### 4.8 Mobile

The requirement describes Android and iOS companion applications with:

- Quotes, invoices, subscriptions, payments, reminders, and dashboards.
- Projects, timers, lock-screen controls, expenses, receipt capture, GPS/mileage.
- Contact import.
- Notifications and home-screen widgets.
- Quick Create.
- Branded documents.
- Passcode and biometric access.

Offline writes, mobile-only modules, background GPS rules, storage retention, and whether to use a PWA or native application are **UNSPECIFIED / REQUIRES PRODUCT DECISION**.

:codex-file-citation{path="C:\projects\Rooman_Billing\my_features\Mobile.pdf" purpose="source"}

### 4.9 Proration

The requirement includes:

- Mid-cycle plan upgrades and downgrades.
- Quantity changes.
- Immediate, period-end, or scheduled application.
- Credit for unused old service.
- Charge for remaining new service.
- Credit-note creation and automatic application.
- Excess-credit carry-forward or refund.
- Flat-coupon proration.
- Full new price at the next renewal.
- Per-organization and per-subscription configuration.

Tax treatment, rounding policy, repeated changes, add-on behavior, paid/overdue invoice interactions, and timezone cutoff rules require explicit decisions.

:codex-file-citation{path="C:\projects\Rooman_Billing\my_features\Proration.pdf" purpose="source"}

### 4.10 Trial Management

Required trial behavior includes:

- Plan trial days and subscription-specific overrides.
- Future starts.
- Trial expiry notifications.
- Payment-method-aware conversion.
- `Trial Expired`, `Live`, and `Cancelled` outcomes.
- Early conversion.
- Portal extension with maximum-count rules.
- Optional fallback to a free plan.
- Trial reports and conversion metrics.

Repeat-trial prevention, access after expiry, change-plan behavior during trial, extension abuse controls, and exact reminder cadence require product decisions.

:codex-file-citation{path="C:\projects\Rooman_Billing\my_features\Trial Management.pdf" purpose="source"}

---

## 5. Zoho Billing Domain Research

The following describes public product behavior, not Zoho’s internal architecture.

- Zoho models plans, add-ons, coupons, and subscription preferences as related but distinct catalog and lifecycle concepts. This supports Rooman’s need for subscription items and immutable applied-price snapshots rather than continuing with one mutable plan reference. [Plans](https://www.zoho.com/us/billing/help/product-catalog/plans/understanding-plans.html), [add-ons](https://www.zoho.com/us/billing/help/product-catalog/addons/), [coupons](https://www.zoho.com/us/billing/help/product-catalog/coupons/).
- Its documented subscription APIs expose subscription lifecycle operations as explicit application commands. Rooman should follow that behavioral pattern without copying API shapes or implementation. [Subscriptions API](https://www.zoho.com/billing/api/v1/subscription/).
- Metered billing combines a base subscription with additional tracked usage. Renewal invoices can remain pending until usage charges are added and the invoice is finalized. [Metered billing](https://www.zoho.com/us/billing/help/settings/preferences/metered-billing.html).
- Proration covers mid-cycle subscription changes and documents settings for plans, coupons, and selected add-on cases. [Proration](https://www.zoho.com/us/billing/help/settings/subscriptions/proration.html).
- Dunning distinguishes autocharge recovery from non-autocharge grace handling and supports retries, notifications, pause/resume/stop, and configurable final actions. [Dunning management](https://www.zoho.com/us/billing/help/settings/dunning-management.html).
- Hosted pages are expiring checkout sessions with multiple purposes rather than permanent invoice URLs. The API documentation states that generated pages expire within an hour. [Hosted Pages API](https://www.zoho.com/billing/api/v1/hosted-pages/), [template customization](https://www.zoho.com/us/billing/help/settings/hosted-payment-pages/templates.html).
- The customer portal supports self-service billing information, invoices, payments, quotes, subscriptions, and selected approvals. Rooman’s PDF confirms only a subset, so broader Zoho behavior should remain reference material until product approves it. [Portal overview](https://www.zoho.com/billing/help/settings/customer-portal/customer-portal.html), [portal functions](https://www.zoho.com/us/billing/help/settings/customer-portal/customer-portal-functions.html).
- Workflow automation exposes event/date triggers, criteria, immediate or delayed actions, logs, webhooks, and schedules. Rooman should adopt the domain concepts but define its own safe condition/action model. [Automation](https://www.zoho.com/us/billing/help/settings/automation.html).
- Document templates have per-document customization, language, branding, and default-selection behavior. [Templates](https://www.zoho.com/us/billing/help/settings/templates.html).
- Publicly documented AI capabilities include Ask Zia, transaction co-creation, insights, forecasting, anomaly detection, and writing assistance. Confirmation is retained for transaction-generating behavior. [AI features](https://www.zoho.com/us/billing/features/ai-features/?src=zohobilling_topmenu), [CoCreate](https://www.zoho.com/us/billing/help/cocreate.html).
- Mobile applications are documented as iOS and Android companion experiences. This does not establish a need to duplicate backend business logic in native clients. [Mobile applications](https://www.zoho.com/us/billing/kb/general/mobile-apps.html).
- Multi-currency exists at the customer/transaction level in mature billing products, but Rooman must decide exchange-rate ownership, realized differences, and reporting currency before implementing it. [Multi-currency invoices](https://www.zoho.com/us/billing/kb/subscriptions/create-invoices-in-multiple-currencies.html).

---

## 6. Current System vs Required System — Gap Analysis

Classification:

- **A** — Already supported.
- **B** — Partially supported.
- **C** — New capability.
- **D** — Architectural change required.
- **E** — Product decision required.

| Feature | Major requirement | Class | Reason |
|---|---|---:|---|
| AI | Billing data and auditable user context | A/B | Data and audit logs exist, but analytics coverage and source provenance are incomplete. |
| AI | Permissioned querying and drafting | C/D | Requires tool contracts, capability authorization, retrieval, confirmation, and AI-specific audit. |
| AI | Forecast/anomaly models | C/E | No forecasting pipeline; definitions and acceptance thresholds are unspecified. |
| Portal | Public invoice access | B | Opaque invoice-token endpoints exist, but the frontend is a placeholder and tokens lack a full session/expiry model. |
| Portal | Customer identity, MFA, invitations | C/D | Existing users/memberships are internal; customer contacts need a separate portal identity boundary. |
| Portal | Profile, documents, subscription management | C/E | No complete portal backend or file-storage architecture. |
| Customization | Basic numbering | B | Organization counters/prefixes exist; multiple versioned series and assignment policies do not. |
| Customization | Templates and notifications | B/C | PDF/email generation exists but no versioned template domain or delivery records. |
| Customization | Workflows and schedules | C/D | Requires event/outbox/job infrastructure and safe action execution. |
| Desktop | Shared API and web UI | B | Reusable backend/API exists; UI completeness and native shell are missing. |
| Desktop | Biometrics/multiple windows | C/E | Requires native integration and secure token storage. |
| Dunning | Overdue marking and reminders | B | Fixed generic reminders exist; no charge retries, cases, policies, attempt history, or final-action engine. |
| Dunning | Autocharge recovery | C/D | Requires reusable payment methods, payment attempts, durable jobs, and gateway abstraction. |
| Hosted pages | Invoice payment order | B | Razorpay public-invoice order/verify exists; customer-facing page is a placeholder. |
| Hosted pages | General checkout sessions | C/D | Requires expiring, single-use sessions, templates, purpose-specific result application, and gateway abstraction. |
| Metered billing | Per-unit plan quantity | B | Static quantity exists, but not measured usage. |
| Metered billing | Usage ingestion/rating | C/D/E | Requires meters, idempotent events, aggregation, rate models, cutoffs, and correction policies. |
| Mobile | Responsive API-backed modules | B | Shared APIs and React exist, but many core pages are placeholders. |
| Mobile | Native capabilities | C/E | Widgets, biometrics, camera, GPS, push, offline behavior need a client/platform decision. |
| Proration | Calendar period calculations | B | Calendar-safe period advancement exists; proration, credits, and historical snapshots do not. |
| Proration | Credit and adjustment lifecycle | C/D/E | Requires credit notes/applications and explicit tax/rounding policy. |
| Trials | Trial days and scheduled conversion | B | Basic fields and automatic conversion exist. |
| Trials | Payment-aware conversion/extension/reporting | C/D/E | No stored payment method, trial-expired state, extension history, charge attempt, or reports. |

### Cross-cutting severity

| Finding | Classification |
|---|---|
| Empty Alembic revision history | **CRITICAL REFACTOR** |
| Production scheduler calls nonexistent `run_forever()` | **CRITICAL REFACTOR** |
| No reliable tests for core billing lifecycle | **CRITICAL REFACTOR** |
| Service methods own commits | **NECESSARY FOR FEATURE** |
| No durable job/outbox mechanism | **NECESSARY FOR FEATURE** |
| Single-plan subscription model | **NECESSARY FOR FEATURE** |
| No reusable tokenized payment method | **NECESSARY FOR FEATURE** |
| No credit-note/application model | **NECESSARY FOR FEATURE** |
| Process-local rate limiting and synchronous email | **RECOMMENDED IMPROVEMENT** |
| Microservices, Kafka, Kubernetes, full CQRS | **OPTIONAL / NOT JUSTIFIED** |

---

## 7. Recommended Rooman Billing Target Architecture

### Backend architecture

Retain a modular FastAPI monolith:

```text
API endpoints
    ↓ validation/authentication
Application command/query services
    ↓ transaction boundary
Domain policies and calculators
    ↓
Repositories / SQLAlchemy persistence
    ↓
PostgreSQL + outbox + durable jobs
```

Recommended modules:

- Identity and tenancy.
- Customers and portal identities.
- Catalog, prices, add-ons, discounts.
- Subscriptions and lifecycle changes.
- Usage and rating.
- Invoicing, credit notes, and balances.
- Payments and gateway adapters.
- Dunning and collections.
- Checkout/hosted pages.
- Templates and notifications.
- Automation and outbound webhooks.
- Reporting and analytics.
- AI orchestration.
- Audit and governance.

Endpoint handlers should not calculate billing results or commit midway. Application services should open one unit of work, invoke domain calculations, persist all state, append audit/outbox records, and commit once.

### Database architecture

Continue with PostgreSQL. Add normalized transactional records and immutable calculation evidence. Do not store core billing state only in JSON.

JSON is appropriate for:

- Gateway payload evidence.
- Template layout configuration.
- Usage dimensions.
- Workflow condition definitions.
- AI source metadata.

It should not replace indexed state, amounts, lifecycle dates, ownership, or foreign keys.

### API architecture

- Keep `/api/v1`.
- Separate commands from ordinary partial resource updates.
- Require `Idempotency-Key` for externally retried mutations.
- Add optimistic concurrency using a `version` field or `If-Match`.
- Use cursor pagination for events, logs, usage, jobs, and audit history.
- Maintain one error envelope with stable machine-readable codes.
- Generate an OpenAPI client or checked frontend service types to reduce contract drift.

### Frontend architecture

Use the existing React application as the primary admin client and foundation for:

- Customer portal.
- Hosted checkout.
- Responsive mobile web/PWA.
- Desktop shell.

Create feature-oriented frontend modules with:

- Typed API services.
- Query-key factories.
- Command hooks.
- Permission-aware route and action guards.
- Reusable money/date/status components.
- Accessible form and confirmation patterns.
- Separate public, portal, and internal application layouts.

### Asynchronous processing

Use PostgreSQL-backed jobs and an outbox before adopting external queue infrastructure.

A dedicated worker should:

1. Claim due jobs using leases and row locking.
2. Record attempt count and failure details.
3. Execute one idempotent operation.
4. Reschedule transient failures with backoff.
5. Move exhausted work to a failed/dead state.
6. Emit operational metrics and audit evidence.

APScheduler may enqueue periodic scans, but it should not be the sole source of job durability.

### Integrations

Define interfaces for:

- Payment gateway.
- Email provider.
- SMS provider.
- File/object storage.
- Push notification provider.
- AI provider.
- Analytics/pixel delivery.
- Digital-signature provider.

Razorpay becomes one payment-gateway adapter, not a condition scattered through billing services.

### Security

- Use internal capabilities such as `invoice.send`, `refund.approve`, `dunning.manage`, `workflow.manage`, `portal.impersonate`, and `ai.execute`.
- Prefer HttpOnly, Secure, SameSite refresh cookies for browsers; keep short-lived access tokens in memory.
- Use OS secure storage for native applications.
- Hash portal and checkout tokens at rest.
- Apply expiry, audience, purpose, and single-use constraints.
- Never store raw card or bank credentials.
- Add Content Security Policy and CSRF controls appropriate to the chosen session design.
- Encrypt sensitive provider credentials using managed key material.
- Step up authentication for refunds, gateway configuration, exports, and portal impersonation.

### Auditing and events

Every consequential command should record:

- Organization.
- Actor type and actor ID.
- Entity and operation.
- Request/correlation ID.
- Before/after state or a redacted diff.
- Reason, approval, or policy source.
- AI involvement where applicable.
- Timestamp and result.

Domain events should describe committed business facts such as `InvoiceIssued`, `PaymentFailed`, `UsageRecorded`, `TrialExpired`, and `SubscriptionChanged`. The transactional outbox reliably hands them to notifications, automation, analytics, and integrations.

---

## 8. Shared Core Domain Model

### Central relationships

```text
Organization
 ├─ Users/Memberships
 ├─ Customers ─ PortalIdentities ─ PortalSessions
 │              └─ CustomerPaymentMethods
 ├─ Products ─ Prices/Plans/Add-ons
 ├─ Subscriptions ─ SubscriptionItems ─ PriceSnapshots
 │       ├─ BillingCycles
 │       ├─ SubscriptionChanges ─ ProrationAdjustments
 │       ├─ UsageMeters ─ UsageEvents/Aggregates
 │       └─ DunningCases
 ├─ Invoices ─ InvoiceLines
 │       ├─ CreditApplications ─ CreditNotes
 │       └─ PaymentAllocations ─ Payments ─ PaymentAttempts
 ├─ CheckoutTemplates ─ CheckoutSessions
 ├─ NotificationTemplates ─ NotificationDeliveries
 ├─ AutomationRules ─ AutomationRuns/ActionRuns
 └─ AuditLogs / InboxEvents / OutboxEvents / Jobs
```

### Important additions

- **Price/PriceVersion:** Immutable amount, currency, interval, pricing model, tax behavior, and effective dates.
- **SubscriptionItem:** One plan, add-on, fixed, per-unit, or metered component attached to a subscription.
- **PriceSnapshot:** Exact commercial terms used for an active subscription item.
- **BillingCycle:** Durable evidence of a generated/finalized cycle and its invoice.
- **SubscriptionChange:** Requested, previewed, scheduled, applied, cancelled, or failed lifecycle command.
- **UsageMeter/Event/Aggregate:** Measurement definition, idempotent raw usage, and reproducible aggregation.
- **CustomerPaymentMethod:** Provider token reference, brand/type, masked details, expiry, default and autocharge eligibility.
- **PaymentAttempt:** Every charge attempt, including purpose, sequence, result, failure category, and provider reference.
- **CreditNote/Application:** Issued credit and its applications to one or more invoices.
- **ProrationAdjustment:** Immutable formula inputs and resulting debit/credit amounts.
- **DunningPolicy/Case/Step:** Policy configuration and per-failure execution state.
- **CheckoutSession:** Purpose-bound expiring session with immutable commercial snapshot.
- **NotificationDelivery:** Channel, recipient, template version, provider status, attempts, and errors.
- **InboxEvent/OutboxEvent:** Durable integration boundaries.
- **Job:** Scheduled or retryable work.
- **PortalIdentity:** Authentication boundary for customer contacts, separate from internal organization membership.
- **AutomationRun:** Deterministic record of matching, actions, outcomes, and retries.
- **AIRequest/ToolInvocation/Draft:** Prompt metadata, sources, proposed actions, approval, and final outcome.

A full general-ledger implementation is not yet justified. Credit notes and applications are required; double-entry accounting can remain a separate future decision.

---

## 9. Feature-by-Feature Implementation Plans

### 9.1 AI in Billing

1. **Objective:** Add safe, explainable assistance for querying, drafting, writing, forecasting, anomaly detection, and collection prioritization.
2. **Requirements:** Ask-style questions, transaction co-creation, voice input, writing help, insights, forecast ranges, anomaly detection, receivables risk, human review, action history, and permissioned external access.
3. **Existing code:** Organization-scoped APIs, audit logs, customers, invoices, quotes, subscriptions, payments, dashboard data, approvals, and search.
4. **Reuse:** Authentication context, authorization guards, audit service, reporting queries, Pydantic schemas, and existing command services.
5. **Backend:** Add `ai` module with conversation orchestration, retrieval/query tools, policy enforcement, redaction, structured proposal generation, and confirmation execution. AI must call domain commands; it must never update billing tables directly.
6. **Database:** Add `ai_conversations`, `ai_requests`, `ai_source_references`, `ai_tool_invocations`, and `ai_action_drafts`. Store minimal redacted prompts and provider metadata according to retention policy.
7. **APIs:** `POST /api/v1/ai/queries` returns an answer plus sources; `POST /ai/drafts` returns a validated proposed command; `POST /ai/drafts/{id}/confirm` executes with optimistic checks; `POST /ai/writing` returns editable text; `GET /ai/history` returns tenant-filtered activity. Authorization varies by tool and proposed action.
8. **Frontend:** AI workspace, source drawer, draft preview/diff, explicit confirmation, permission warnings, feedback controls, forecast/anomaly panels, and voice-transcript review.
9. **Jobs/events:** Refresh analytics features, compute forecasts, detect anomalies, and produce summaries asynchronously. Recompute when relevant outbox events arrive.
10. **Integrations:** Pluggable AI provider and optional speech-to-text provider. External model access must be organization-configurable.
11. **Rules:** Models may propose; deterministic Rooman services validate and calculate. Answers must identify sources and uncertainty. Stale drafts cannot be confirmed.
12. **States:** Request `queued → running → completed/failed`; draft `proposed → validated → approved/executed/rejected/expired`.
13. **Validation:** Schema-constrained outputs, tenant-filtered tools, supported currencies/date ranges, maximum result sizes, and command revalidation at confirmation.
14. **Edge cases:** Prompt injection in customer data, deleted source records, changed invoice state, concurrent approval, provider outage, incomplete history, and ambiguous natural language.
15. **Security:** Per-tool capabilities, prompt/data minimization, provider isolation, redaction, rate limits, and no secrets or raw payment details in model context.
16. **Audit:** Record model/provider/version, user, sources, tool calls, redacted inputs, proposed changes, confirmer, final command result, and overridden warnings.
17. **Testing:** Tool authorization, tenant isolation, malicious content, structured-output rejection, stale confirmation, deterministic calculation delegation, source correctness, provider failure, and audit completeness.
18. **Dependencies:** Mature reporting queries, capability permissions, outbox, audit, feature-complete domain commands, and defined retention policy.
19. **Order:** Last major product phase, after billing behavior and analytics definitions stabilize.
20. **Definition of Done:** AI answers are source-grounded; drafts cannot bypass permissions or calculators; every consequential action requires the configured confirmation/approval and is fully auditable.

### 9.2 Customer Portal

1. **Objective:** Give customers and authorized contacts secure self-service access without granting internal organization membership.
2. **Requirements:** Branding, invitations/self-signup, MFA, profile/address/documents, project/timesheet visibility, payment methods, comment/forwarding controls, identity verification, pending-payment protection, trial extension, and early activation.
3. **Existing code:** Customers and contacts, invoice/quote public tokens, Razorpay payment flow, organization settings, invoice PDFs, email service, and audit logs.
4. **Reuse:** Tenant/customer relationships, invoice/payment APIs behind new portal policies, PDF rendering, gateway adapter, and notification infrastructure.
5. **Backend:** Add portal identity/session, invitation, MFA/recovery, profile-policy, document, comment, and scoped customer-service modules. Do not reuse internal JWT claims unchanged.
6. **Database:** Add `portal_identities`, contact links, invitations, sessions, MFA factors/recovery codes, portal settings, documents, document shares, comments, and portal activity records.
7. **APIs:** `POST /portal/auth/invitations/{token}/accept`, `/portal/auth/login`, `/portal/auth/mfa/verify`; `GET/PATCH /portal/me`; `GET /portal/invoices|quotes|subscriptions|projects`; `POST /portal/invoices/{id}/payment-sessions`; `POST /portal/subscriptions/{id}/trial-extension`; `POST /portal/subscriptions/{id}/activate`. Responses expose only customer-owned projections.
8. **Frontend:** Separate `/portal` application layout, authentication/recovery/MFA, dashboard, documents, profile, invoices, quotes, payments, trial controls, and accessible mobile-first pages.
9. **Jobs/events:** Invitations, verification messages, document scanning, activity alerts, trial-extension notices, and abandoned portal-registration reminders.
10. **Integrations:** Email/SMS, object storage with malware scanning, payment gateway, and optional identity provider.
11. **Rules:** Organization settings govern visibility and self-service. A contact sees only linked customers. Pending gateway payment blocks duplicates until terminal failure/expiry.
12. **States:** Invitation `issued → accepted/expired/revoked`; identity `pending → active/locked/disabled`; session `active → expired/revoked`; document `uploaded → scanning → available/rejected`.
13. **Validation:** Unique normalized email within portal scope, verified identity where required, file type/size limits, trial extension count, and ownership on every resource.
14. **Edge cases:** One contact across customers, contact removal, invoice reassignment, concurrent payments, invitation reuse, lost MFA, deleted documents, and suspended organizations.
15. **Security:** Hash tokens, expire sessions, rotate refresh credentials, MFA, secure cookies, rate limiting, anti-enumeration, signed short-lived downloads, CSP, and step-up for payment-method changes.
16. **Audit:** Login/security events, profile changes, document access, comments, forwarding, trial actions, payment-session creation, admin impersonation, and policy changes.
17. **Testing:** Cross-customer isolation, invitation replay, MFA recovery, resource enumeration, pending-payment races, file security, policy matrices, and responsive accessibility.
18. **Dependencies:** Payment methods, checkout sessions, notifications, object storage, capability authorization, trials, and subscription lifecycle commands.
19. **Order:** Build identity/settings and read-only views first; then payments/trials; then broader subscription self-service after product confirmation.
20. **Definition of Done:** A verified contact can securely access only permitted customer data and complete approved self-service workflows with end-to-end audit evidence.

### 9.3 Customization and Automation

1. **Objective:** Let organizations customize identifiers/documents/messages and execute controlled event/date-driven workflows.
2. **Requirements:** Number series, PDF templates, digital signatures, email/webhook/custom-function actions, logs, schedules, email/SMS settings, reporting tags, web tabs, and hosted-page customization.
3. **Existing code:** Organization numbering fields, PDF generation, SMTP sending, audit logging, approval records, APScheduler, and organization settings.
4. **Reuse:** Existing number allocation as the seed for a transactional sequence service; current renderers as legacy template adapters; outbox and jobs as execution infrastructure.
5. **Backend:** Add numbering, templates, notification, automation, schedules, outbound-webhook, signature, reporting-tag, and web-tab modules. Use an allow-listed rule DSL; do not permit arbitrary Python.
6. **Database:** `number_series`, assignments, `document_templates`, versions/defaults, `notification_templates`, `automation_rules`, triggers, action definitions, runs/action-runs, schedules, outbound webhook deliveries, signature requests, tags, and entity-tag links.
7. **APIs:** CRUD `/settings/number-series`, `/templates`, `/notification-templates`, `/automation/rules`, `/automation/schedules`, `/reporting-tags`, `/web-tabs`; `POST /templates/{id}/preview`; `POST /automation/rules/{id}/test`; `POST /webhook-deliveries/{id}/retry`; `GET /automation/logs`. Configuration requires admin/owner; logs can permit finance read access.
8. **Frontend:** Visual number-series configuration, template gallery/editor/preview, workflow trigger-condition-action builder, schedule editor, log explorer, retry controls, signature settings, tag manager, and safe web-tab configuration.
9. **Jobs/events:** Consume domain events, evaluate rules, schedule delayed actions, send notifications/webhooks, render documents, request signatures, and retry transient failures.
10. **Integrations:** Email, SMS, outbound HTTPS webhooks, signature provider, object storage, and narrowly sandboxed custom-function runtime only if later approved.
11. **Rules:** One active default template per organization/document type/language; number allocation is transactional; workflow execution has recursion/depth limits; template versions used on issued documents remain immutable.
12. **States:** Template `draft → active → retired`; rule `draft → active → paused/retired`; run/action `queued → running → succeeded/failed/skipped`; signature `requested → signed/declined/expired`.
13. **Validation:** Unique series assignments, token allow-list, valid HTTPS endpoints, safe templates, bounded conditions/actions, schedule timezone, signature eligibility, and web-tab origin policy.
14. **Edge cases:** Concurrent number allocation, deleted templates, repeated events, workflow loops, DST schedules, partial action failure, endpoint timeouts, and default-template replacement.
15. **Security:** Encrypt webhook secrets, SSRF protection, redact logs, sanitize HTML, prohibit arbitrary code initially, apply least privilege, and verify signature callbacks.
16. **Audit:** Configuration versions, activations, previews, retries, deliveries, signature transitions, number overrides, and manual workflow executions.
17. **Testing:** Concurrent numbering, template snapshots, rendering regression, rule matching, delayed actions, recursion prevention, SSRF payloads, retry/idempotency, and timezone boundaries.
18. **Dependencies:** Outbox, durable jobs, notification delivery, object storage, capability permissions, and stable domain events.
19. **Order:** Implement shared numbering/templates/notifications first, then workflows/logs/schedules, then signatures/tags/web tabs.
20. **Definition of Done:** Administrators can safely configure, preview, activate, observe, and troubleshoot versioned customization and automation without arbitrary code execution or duplicate actions.

### 9.4 Desktop

1. **Objective:** Deliver secure Windows/macOS access while sharing Rooman’s API and web business logic.
2. **Requirements:** Native windows, biometrics, shortcuts, dashboard, core billing modules, retail tax invoices, signatures, reminders, customer/payment history, and multiple windows.
3. **Existing code:** React/Vite application, FastAPI APIs, JWT authentication, dashboards, PDF generation, and settings.
4. **Reuse:** Use the web component system, generated API client, permission model, and backend commands. Do not reimplement billing calculations locally.
5. **Backend:** Add device/session registration, native OAuth-style exchange, secure refresh-token revocation, optional push/device notification endpoints, and desktop telemetry controls.
6. **Database:** Add `devices`, native sessions, push endpoints, application-version records, and revocation/security events. No platform-specific duplication of billing entities.
7. **APIs:** `POST /auth/native/exchange`, `POST /devices`, `DELETE /devices/{id}`, `GET /desktop/bootstrap`, and optional notification registration. Normal billing APIs remain shared and role-protected.
8. **Frontend:** First complete the web feature modules. Then package them in a thin Tauri or Electron shell with window routing, deep links, shortcuts, update UX, and native credential bridge.
9. **Jobs/events:** Push notification dispatch, application-update metadata, and optional background sync only for explicitly approved read caches.
10. **Integrations:** Windows Hello, macOS Keychain/LocalAuthentication, code-signing/notarization, crash reporting, and signature provider.
11. **Rules:** Server remains authoritative; native clients never allocate invoice numbers or finalize billing offline. Biometrics unlock local credentials rather than becoming server identity.
12. **States:** Device `pending → trusted → revoked`; application update `available → downloaded → installed/failed`.
13. **Validation:** Supported OS/app versions, secure deep-link origins, organization context, device limits, and clock-skew tolerance.
14. **Edge cases:** Lost devices, revoked users, multiple organizations/windows, expired credentials, interrupted updates, and partial network availability.
15. **Security:** OS keychain storage, signed binaries, auto-update signature verification, hardened IPC, navigation allow-list, no Node/browser escape, and remote session revocation.
16. **Audit:** Device registration, biometric-enabled status, logins, revocations, sensitive commands, application version, and signature activity—never biometric material.
17. **Testing:** Shared browser tests, shell IPC tests, install/update smoke tests, deep-link validation, credential revocation, Windows/macOS matrix, and accessibility/shortcut checks.
18. **Dependencies:** Feature-complete responsive web UI, stable API contracts, secure browser/native session strategy, notifications, and signature support.
19. **Order:** Thin online shell first; multi-window/shortcuts next. Offline mutation support should be deferred pending a separate conflict-model decision.
20. **Definition of Done:** Signed Windows/macOS builds expose complete authorized online workflows, store credentials securely, pass platform smoke tests, and contain no duplicated billing logic.

### 9.5 Dunning Management

1. **Objective:** Recover failed recurring and overdue payments predictably while applying configured customer/subscription outcomes.
2. **Requirements:** Autocharge/non-autocharge paths, retry schedules, notifications, grace periods, final actions, policy segments, pause/resume/stop, reactivation, one-time invoices, expiring-card alerts, and recovery metrics.
3. **Existing code:** Overdue invoice marking, `past_due` subscription state, reminders, Razorpay payments, webhook intake, and scheduler.
4. **Reuse:** Invoice balance/allocation rules, gateway verification, notification framework, audit, outbox, and durable jobs.
5. **Backend:** Add policy matching, case creation, payment retry orchestration, failure classification, final-action handling, manual control, recovery, and metrics services.
6. **Database:** Add `dunning_policies`, criteria, steps, `dunning_cases`, case attempts, scheduled actions, linked payment attempts, communication records, pause/resume metadata, and final-action evidence.
7. **APIs:** CRUD `/dunning/policies`; `GET /dunning/cases`; `POST /cases/{id}/pause|resume|stop|retry`; `GET /dunning/metrics`; customer update links create checkout sessions. Admin manages policies; finance operates cases.
8. **Frontend:** Policy builder, retry timeline, failure reason, amount at risk, next action, pause/resume/stop controls, bulk filters, communication preview, and recovery dashboard.
9. **Jobs/events:** `PaymentFailed` opens/updates a case; scheduled retry creates a payment attempt; success closes the case; final-action jobs cancel/reverse/retain invoice according to policy; pre-expiry jobs notify customers.
10. **Integrations:** Gateway token charging, email/SMS, checkout/payment-method update pages, and webhook processing.
11. **Rules:** At most the configured retry count/span; only one active case per failed obligation; success cancels pending actions; first ACH failure behavior follows the approved policy; manual payments also recover cases.
12. **States:** Case `open → retry_scheduled → retrying → recovered`, or `paused/stopped/exhausted/finalized`; payment attempt `created → submitted → pending → succeeded/failed/unknown`.
13. **Validation:** Increasing retry offsets, maximum span, compatible final action, active/default autocharge method, positive balance, no paid/void invoice, and matching organization currency/gateway.
14. **Edge cases:** Late webhooks, unknown gateway result, duplicate failures, partial payment, card update during retry, subscription cancellation, policy edits during active cases, and concurrent manual payment.
15. **Security:** Payment tokens only through provider references, signed update links, finance/admin permissions, webhook verification, and step-up for destructive final actions.
16. **Audit:** Selected policy/version, each scheduled/executed attempt, gateway outcome, notification, manual controls, final action, actor, and recovery source.
17. **Testing:** Policy matching, retry timelines with fake clock, concurrency, webhook replay, manual recovery, partial payment, final actions, policy versioning, and gateway timeout reconciliation.
18. **Dependencies:** Payment-method vault references, payment attempts, gateway abstraction, checkout sessions, notifications, jobs/outbox, credits, and lifecycle commands.
19. **Order:** After hosted payment/payment-method infrastructure and before advanced automation.
20. **Definition of Done:** Every failure has one deterministic, observable, idempotent recovery case; success or final action leaves invoice and subscription state consistent.

### 9.6 Hosted Payment Pages

1. **Objective:** Provide expiring, branded, secure checkout for invoice payment, subscriptions, add-ons, and payment-method updates.
2. **Requirements:** Multiple purposes, one/multi-page templates, branding, fields, order summary, localized messages, thank-you/redirect, expiry, abandoned checkout, analytics, links/QR/embed, gateway choices, and synchronized billing results.
3. **Existing code:** Public invoice token APIs, Razorpay order creation/signature verification, invoices, payments, and organization branding fields.
4. **Reuse:** Gateway adapter, invoice balance logic, price snapshots, notification templates, organization settings, and public frontend layout.
5. **Backend:** Add template/session services, purpose-specific payload validation, commercial snapshotting, payment initiation, completion reconciliation, abandonment, and result application.
6. **Database:** Add `checkout_templates`, versions, `checkout_sessions`, items/snapshots, session customers/fields, attempt links, analytics consent/events, and result references.
7. **APIs:** `POST /hosted-pages` creates `{purpose, resource, template, customer}` and returns `{id,url,expires_at}`; public `GET /checkout/{token}` returns safe display data; `POST /checkout/{token}/confirm`; `POST /checkout/{token}/payment-attempts`; `GET /hosted-pages/{id}`; template CRUD. Creation requires appropriate internal role; token routes are purpose-scoped public routes.
8. **Frontend:** Template editor/preview, internal session creation, public responsive checkout, verification, payment-method collection through provider components, failure/retry, success/redirect, and accessibility.
9. **Jobs/events:** Expire sessions, send abandonment reminders with consent, reconcile pending attempts, process webhooks, and apply successful results asynchronously when necessary.
10. **Integrations:** Razorpay first, gateway interface for later providers, email/SMS verification, QR generation, GA/Meta only with consent and strict payload minimization.
11. **Rules:** Session is immutable after payment starts; amount is server-calculated; token has purpose/audience/expiry; successful single-use sessions cannot be replayed; one active attempt is allowed unless prior attempt fails/expires.
12. **States:** `created → pending → processing → successful/failed/cancelled/expired`; ambiguous gateway results remain `processing` pending reconciliation.
13. **Validation:** Active resources/prices, currency/gateway compatibility, invoice outstanding amount, allowed quantity, verified identity when configured, safe redirect allow-list, and template validity.
14. **Edge cases:** Price changes after creation, session expiry during payment, duplicate callbacks, partial invoice payment, abandoned return, concurrent tabs, late webhook, and redirect failure.
15. **Security:** Never accept authoritative totals from the browser; hash tokens; provider-hosted fields; PCI scope review; CSP/frame policy; anti-bot/rate limits; signed redirects; no payment data in analytics.
16. **Audit:** Session creation, commercial snapshot, viewer verification, attempts, expiry, result application, redirect, and administrative template changes.
17. **Testing:** Token expiry/replay, price tampering, callback/webhook races, duplicate payment prevention, template sanitization, redirect attacks, responsive UI, and gateway contract tests.
18. **Dependencies:** Versioned prices/items, payment methods/attempts, gateway abstraction, notifications, portal identity, jobs/outbox, and subscription commands.
19. **Order:** Invoice payment MVP, payment-method update, new subscription, then subscription modification/add-ons and analytics.
20. **Definition of Done:** Each supported purpose completes through an expiring session whose server-side snapshot, payment result, and resulting billing records reconcile exactly once.

### 9.7 Metered Billing

1. **Objective:** Bill subscription customers from verifiable usage in addition to recurring fixed charges.
2. **Requirements:** Enable metering, collect usage manually/API, associate usage with billing periods, generate pending renewal invoices, add rated usage, finalize, send, and collect.
3. **Existing code:** Per-unit plans, subscription periods, invoice lines, Decimal calculation, invoice generation, and scheduler.
4. **Reuse:** Subscription items/price snapshots, billing cycles, invoice services, outbox/jobs, organization timezone, and audit.
5. **Backend:** Add meter definition, ingestion, correction, aggregation, rating, preview, cycle finalization, and late-event handling services. Calculators must be pure and versioned.
6. **Database:** Add `usage_meters`, price/meter associations, `usage_events`, corrections, aggregates, rating results, invoice-line sources, ingestion batches, and period close/finalization records.
7. **APIs:** CRUD `/meters`; `POST /usage-events` and `/usage-events/batch` with idempotency keys; `GET /subscriptions/{id}/usage`; `POST /billing-cycles/{id}/usage-preview`; `POST /billing-cycles/{id}/finalize`. Customers may receive read-only scoped usage access later.
8. **Frontend:** Meter setup, CSV/manual entry, usage explorer, rejected-event report, period preview, pending invoice review, adjustment workflow, and usage dashboard.
9. **Jobs/events:** Aggregate events, recompute open periods, detect missing/outlier usage, prepare pending invoices, close cutoffs, and process approved late adjustments.
10. **Integrations:** Customer API keys or scoped ingestion tokens, optional CSV/object imports, and future provider connectors.
11. **Rules:** Raw usage is append-only; corrections reference original events; aggregation and price versions are frozen at finalization; invoiced periods cannot be silently recalculated.
12. **States:** Event `accepted/rejected/corrected`; aggregate `open → calculated → finalized`; cycle `collecting → pending_review → finalized → invoiced`.
13. **Validation:** Idempotency key, meter/customer/subscription ownership, event time, unit precision, nonnegative/negative correction policy, dimensions, ingestion window, and maximum batch size.
14. **Edge cases:** Late/out-of-order events, duplicates, clock skew, plan changes mid-period, trial usage, paused subscriptions, missing events, corrections after invoicing, and timezone/DST boundaries.
15. **Security:** Scoped ingestion credentials, quotas, signature verification where applicable, field allow-lists, tenant isolation, and protection against cost-amplification attacks.
16. **Audit:** Meter/version changes, ingestion source, rejected events, corrections, aggregation inputs, formula version, finalizer, and invoice lineage.
17. **Testing:** Aggregation/rating property tests, duplicate ingestion, late corrections, precision/rounding, cutoff concurrency, plan changes, large batches, and exact invoice reproducibility.
18. **Dependencies:** Subscription items, immutable prices, billing cycles, invoice provenance, durable jobs, idempotency, and product decisions on rating models.
19. **Order:** Ship simple sum-based fixed-per-unit metering first only after its commercial policy is approved; add tiered/volume models in later slices.
20. **Definition of Done:** Given the same frozen event set and price version, Rooman reproducibly generates the same reviewed usage charge and invoice evidence.

### 9.8 Mobile

1. **Objective:** Provide reliable mobile access to the highest-value billing workflows and approved native capabilities.
2. **Requirements:** Quotes, invoices, subscriptions, payments, dashboards, projects/timers, expenses/receipts, GPS mileage, contacts, notifications, widgets, Quick Create, templates, passcode, and biometrics.
3. **Existing code:** React SPA, FastAPI APIs, authentication, dashboards, and partial project/expense frontend mocks.
4. **Reuse:** Responsive design system, generated API client, capability checks, server calculations, portal/checkout components, and notification infrastructure.
5. **Backend:** Complete missing production APIs before native work; add device registration, push tokens, compact dashboard endpoints, upload processing, timer commands, and mobile bootstrap/version policy.
6. **Database:** Devices/push endpoints plus real project, timesheet, expense, receipt, mileage, timer, and notification-read models if those modules remain in scope.
7. **APIs:** Shared resource APIs plus `GET /mobile/bootstrap`, `POST /devices`, `POST /uploads`, timer start/stop, receipt submission, mileage submission, notification feed/read endpoints, and widget summaries.
8. **Frontend:** First make the web app responsive/PWA-capable. If native value is approved, build a thin React Native or native-shell client for widgets, camera, GPS, push, and biometric unlocking.
9. **Jobs/events:** Push delivery, receipt OCR, mileage processing, document rendering, reminder scheduling, and safe synchronization.
10. **Integrations:** APNs/FCM, camera/photos, contacts, GPS, biometric/keychain services, and optional OCR.
11. **Rules:** Server is authoritative for financial values; explicit user consent is required for contacts/location/photos; background tracking is off unless clearly enabled.
12. **States:** Device trust and upload-processing states; timer must have a single active-session policy per user/project if product approves it.
13. **Validation:** Image/file limits, timer overlaps, mileage plausibility, required invoice fields, organization context, supported client version, and permission availability.
14. **Edge cases:** Intermittent networks, duplicate taps/uploads, OS permission revocation, background termination, timezone changes, token refresh, and multi-organization switching.
15. **Security:** OS secure storage, certificate/TLS validation, remote logout, encrypted caches, minimal local PII, screenshot/clipboard policy for sensitive screens, and rooted-device policy if required.
16. **Audit:** Device activity, financial commands, timer edits, receipt changes, mileage submissions, contact imports, and notification interaction.
17. **Testing:** Responsive Playwright suite, device API contracts, offline-read behavior, duplicate submission, push deep links, camera/GPS permission states, biometric unlock, and platform release smoke tests.
18. **Dependencies:** Complete web/API modules, notifications, uploads/object storage, secure device sessions, and decisions on projects/expenses/offline scope.
19. **Order:** Responsive web/PWA first; native wrapper second; widgets/camera/GPS last. Do not implement an offline financial write engine in the first release.
20. **Definition of Done:** Approved mobile workflows function on supported devices, preserve server authority and tenant permissions, and degrade safely under poor connectivity.

### 9.9 Proration

1. **Objective:** Apply subscription changes at controlled effective times with reproducible debit/credit adjustments.
2. **Requirements:** Upgrade, downgrade, quantity changes, immediate/end-term/scheduled effects, unused-service credit, new-service charge, credit note/application, carry-forward/refund, coupon handling, and next-renewal normalization.
3. **Existing code:** Subscription dates, plan/quantity changes, invoice generation, calendar-safe month arithmetic, Decimal totals, refunds, and organization approval threshold.
4. **Reuse:** Money primitives, invoice lines, subscription lifecycle framework, approvals, jobs, audit, and future credit-note service.
5. **Backend:** Add change preview/confirmation, proration calculator, scheduled application, credit-note issuance/application, reversal, and change-history services. Existing direct quantity update must stop bypassing this flow.
6. **Database:** Add `subscription_changes`, item before/after snapshots, `proration_adjustments`, `credit_notes`, credit lines/applications, calculation version, rounding/tax evidence, effective timestamp, and optimistic version.
7. **APIs:** `POST /subscriptions/{id}/changes/preview`; `POST /subscriptions/{id}/changes`; `GET /subscriptions/{id}/changes`; `POST /changes/{id}/cancel`; `POST /changes/{id}/apply`; credit-note read/application/refund endpoints. Finance can preview/apply; threshold or policy may require approval.
8. **Frontend:** Change wizard, current-versus-proposed comparison, effective-date choice, debit/credit preview, tax/coupon disclosure, approval status, scheduled-change timeline, and credit-balance display.
9. **Jobs/events:** Apply scheduled changes, expire stale previews, issue invoices/credits, notify customers, and reconcile payment/refund consequences.
10. **Integrations:** Gateway only when immediate net debit is configured for autocharge or excess credit is refunded.
11. **Rules:** Use actual service-period boundaries in organization timezone; snapshot all inputs; apply exactly once; next renewal uses full new price; do not mutate finalized invoice evidence.
12. **States:** Change `draft/previewed → pending_approval → scheduled → applying → applied`, or `cancelled/failed/expired`.
13. **Validation:** Active eligible subscription, supported target price/currency, effective date within allowed range, no conflicting scheduled change, positive quantity, and current version match.
14. **Edge cases:** Multiple same-day changes, leap years, February/month-end, trial/paused/past-due status, existing unpaid invoice, partial payment, coupon expiry, taxes, rounding remainder, and concurrent renewal.
15. **Security:** Capability checks, approval thresholds, trusted calculator only, no client-supplied totals, and step-up for refunds.
16. **Audit:** Before/after snapshots, formula inputs, calculation version, preview, approval, effective date, generated invoice/credit links, override reason, and actor.
17. **Testing:** Golden calculations, property tests, leap/month-end dates, rounding, coupon/tax policies, concurrency with renewal/payment, scheduled cancellation, and credit applications.
18. **Dependencies:** Subscription items/prices, billing cycles, credits, approval integration, jobs/outbox, and approved tax/rounding policy.
19. **Order:** Implement credit notes and immutable item pricing first, then preview-only, immediate changes, scheduled/end-term changes, and refunds.
20. **Definition of Done:** Every supported change produces explainable, immutable, balanced adjustments and remains correct under retries and concurrent renewal processing.

### 9.10 Trial Management

1. **Objective:** Manage trial acquisition, expiry, extension, conversion, charging, fallback, and reporting as an explicit lifecycle.
2. **Requirements:** Plan/default trial duration, overrides, future start, expiry/about-to-expire notifications, saved-method autocharge, cancellation without method, trial-expired on failure, early conversion, extension limits, optional free fallback, and reports.
3. **Existing code:** `trial_days`, `trial_end`, `trialing` state, create/convert behavior, scheduler, invoices, email, and audit.
4. **Reuse:** Subscription lifecycle commands, payment methods/attempts, checkout sessions, notification templates, dunning/event infrastructure, and reporting.
5. **Backend:** Replace unconditional conversion with a policy-driven trial-completion service. Add extension, early-conversion, fallback, access-entitlement, reminder, and reporting queries.
6. **Database:** Extend status model or add lifecycle reason fields for `trial_expired`; add `trial_periods`, `trial_extensions`, conversion attempts, policy snapshots, reminder records, and fallback-plan reference.
7. **APIs:** `POST /subscriptions/{id}/trial/extend`; `/trial/activate`; `/trial/convert`; `GET /trials`; `GET /trials/reports`; organization/plan trial-policy endpoints. Customer portal commands use narrower customer authorization.
8. **Frontend:** Internal trial list and detail timeline, extension/activation dialogs, policy settings, payment-method CTA, portal expired-state experience, conversion funnel, and sales-cycle report.
9. **Jobs/events:** About-to-expire notifications, end-of-trial evaluation, payment attempt, conversion, fallback/cancellation, entitlement cutoff, and metrics aggregation.
10. **Integrations:** Gateway, hosted payment page, email/SMS, customer portal, and optional entitlement webhook.
11. **Rules:** Trial end follows organization timezone; extension count and duration are enforced atomically; successful charge activates; missing method/failure follows the approved policy; duplicate end jobs are idempotent.
12. **States:** `scheduled → trialing → conversion_pending → active`; failure may lead to `trial_expired`, free fallback, or `cancelled`; extension returns eligible expired trials to `trialing`.
13. **Validation:** Eligible plan/status, allowed extension count, valid future dates, payment-method chargeability, free-plan compatibility, no duplicate trial for prohibited identities, and no conflicting lifecycle command.
14. **Edge cases:** Trial ending during DST, method added while job runs, late payment webhook, early conversion on final day, plan change during trial, repeated extensions, cancellation, and charge succeeded but invoice creation retried.
15. **Security:** Portal identity verification, anti-abuse controls, signed conversion links, rate limiting, payment token isolation, and administrator override reason.
16. **Audit:** Policy snapshot, reminders, extensions, payment-method presence, attempts, conversion/fallback/cancellation, entitlements, override reasons, and actor.
17. **Testing:** Fake-clock boundaries, missing/failed/successful payment method, webhook races, extension concurrency, free fallback, duplicate jobs, reminders, and report accuracy.
18. **Dependencies:** Payment methods/attempts, checkout, lifecycle state model, notification/jobs/outbox, portal, and entitlement policy.
19. **Order:** Build internal policy and lifecycle first, then hosted payment conversion, portal extension, fallback, and reporting.
20. **Definition of Done:** Trial completion is payment-aware, retry-safe, observable, configurable, customer-accessible where authorized, and accurately reported.

---

## 10. Cross-Feature Dependencies

| Foundation | Consumers |
|---|---|
| Alembic baseline and migration discipline | Every feature |
| Unit-of-work transaction ownership | Proration, usage, trials, dunning, checkout, automation |
| Immutable prices and subscription items | Metered billing, proration, trials, HPP, portal |
| Credit notes/applications | Proration, dunning, refunds, portal balances |
| Customer payment methods and attempts | Trials, HPP, dunning, portal |
| Gateway abstraction | Payment methods, HPP, dunning, trials |
| Transactional outbox and durable jobs | Dunning, trials, usage, notifications, automation, AI |
| Versioned notification templates/deliveries | Portal, trials, dunning, HPP, automation |
| Capability-based authorization | Portal administration, automation, AI, refund/dunning controls |
| Domain event vocabulary | Automation, reporting, notifications, AI |
| Complete responsive web workflows | Mobile and desktop |
| Reporting projections | AI insights, trial reports, dunning metrics, mobile dashboards |

AI, automation, mobile, and desktop should consume stable domain services. They must not become alternative paths that bypass them.

---

## 11. Recommended Implementation Order

### Phase 0 — Production integrity

- Create and validate the Alembic baseline.
- Correct the dedicated scheduler entry point.
- Make API router imports strict in tested/release environments.
- Add request/correlation IDs and structured operational logging.
- Add PostgreSQL CI and migration-upgrade verification.
- Add characterization tests for subscriptions, invoices, payments, scheduler, and webhooks.

### Phase 1 — Shared billing foundation

- Refactor transaction ownership into application services/unit of work.
- Introduce command idempotency and optimistic versions.
- Add inbox/outbox and durable job tables/worker.
- Add domain event vocabulary.
- Add immutable price versions, subscription items, and billing-cycle records.
- Add customer payment methods, gateway accounts/adapters, and payment attempts.
- Add credit notes and credit applications.
- Add versioned notification templates and delivery tracking.

### Phase 2 — Core billing behavior

- Proration preview and credit calculation.
- Immediate and scheduled subscription changes.
- Meter definitions, ingestion, aggregation, rating, and cycle finalization.
- Strengthened invoice provenance and issuance rules.

### Phase 3 — Trial lifecycle

- Payment-aware trial completion.
- Trial-expired state and extension history.
- Early conversion and hosted payment link.
- Optional free fallback.
- Trial reporting.

### Phase 4 — Customer-facing payments

- Hosted invoice payment.
- Payment-method collection/update.
- General hosted checkout templates and sessions.
- Portal identity, MFA, settings, and read-only views.
- Portal payments and approved trial controls.

### Phase 5 — Collections

- Dunning policies/cases.
- Autocharge retries.
- Non-autocharge grace handling.
- Pause/resume/stop and final actions.
- Recovery metrics and expiring-card notifications.

### Phase 6 — Customization and automation

- Number series.
- Document and notification templates.
- Outbound webhooks.
- Workflow rules, logs, and schedules.
- Digital signatures, reporting tags, and web tabs as separately scoped increments.

### Phase 7 — Client platforms

- Complete responsive internal and portal web UI.
- PWA behavior.
- Thin desktop shell.
- Native mobile client only for approved native-value features.

### Phase 8 — AI and advanced analytics

- Governed reporting/query layer.
- Ask-style assistance.
- Writing tools.
- Transaction drafts with confirmation.
- Forecasts, anomaly detection, and receivables prioritization.

Each phase should be split into small migrations and PRs rather than delivered as one branch.

---

## 12. Database Migration Strategy

1. Establish a reviewed Alembic baseline matching the currently deployed schema. Do not blindly generate against an unknown production database.
2. Add a CI job that creates a blank PostgreSQL database and runs `alembic upgrade head`.
3. Test upgrade from a representative previous schema.
4. Use expand/backfill/cutover/contract migrations:
   - Add nullable tables/columns.
   - Deploy compatible application code.
   - Backfill in resumable batches.
   - Verify counts and invariants.
   - Add constraints/indexes.
   - Switch reads/writes.
   - Remove old fields only in later releases.
5. Create subscription items from each legacy subscription’s plan and quantity.
6. Snapshot legacy plan price/currency/tax data before allowing catalog mutations to affect billing.
7. Preserve old public invoice tokens during an explicit compatibility window, then migrate to expiring checkout sessions.
8. Backfill notification/audit references where reliable; do not manufacture history that cannot be proven.
9. Create indexes concurrently in production where PostgreSQL and operational procedure permit it.
10. Add reconciliation queries and rollback/runbook instructions to every data migration PR.

Critical constraints should include:

- Tenant-consistent composite relationships where practical.
- Unique usage event idempotency keys per organization/meter/source.
- Unique provider transaction/attempt references.
- One active default payment method per customer/currency/gateway policy.
- One active default template per organization/document type/language.
- Unique billing-cycle generation key per subscription/period/type.
- Unique active dunning case per obligation.
- Unique checkout token hash.
- Due-job and unprocessed-outbox partial indexes.
- Check constraints for nonnegative money, quantity, counters, and valid date ranges.

---

## 13. API Strategy

- Preserve `/api/v1` and introduce new resources incrementally.
- Keep CRUD for configuration; use command endpoints for state transitions.
- Require idempotency for:
  - Usage ingestion.
  - Checkout creation/confirmation.
  - Payment attempts.
  - Subscription changes.
  - Trial conversion/extension.
  - Dunning retry/finalization.
  - Webhook consumption.
- Return operation/resource IDs so clients can safely poll asynchronous work.
- Use server-generated previews with opaque preview IDs for proration and complex subscription changes.
- Revalidate previews on confirmation.
- Use stable errors such as `invalid_state`, `version_conflict`, `idempotency_conflict`, `payment_pending`, `policy_denied`, and `resource_expired`.
- Version externally consumed webhook schemas.
- Sign outbound webhooks and include unique event/delivery IDs.
- Avoid exposing raw database objects. Public, portal, internal, and integration schemas must be separate.
- Generate and check a TypeScript API client as part of CI.

---

## 14. Testing Strategy

### Preserve the baseline

The existing 110-test baseline remains a mandatory gate. New work may add tests but must not weaken, delete, or bypass existing assertions without explicit review.

### Required test layers

- **Pure unit tests:** Money, date, tax, proration, rating, retry schedule, policy selection, and state machines.
- **Service tests:** One transaction across all records, audit, and outbox writes.
- **API tests:** Validation, error contracts, permissions, organization isolation, idempotency, and optimistic concurrency.
- **PostgreSQL tests:** Constraints, locking, numeric behavior, timezone behavior, and migration upgrades.
- **Integration tests:** Razorpay adapter, webhook replay, email/SMS delivery adapter, storage, and AI provider boundaries.
- **Job tests:** Fake clock, leases, retries, crashes, duplicate workers, dead jobs, and exactly-once business effects.
- **Frontend tests:** Vitest/React Testing Library for components and permissions; Playwright for critical internal, portal, and checkout journeys.
- **Security tests:** IDOR/tenant crossover, token replay, SSRF, XSS/template injection, CSRF/session behavior, webhook signatures, and rate limits.
- **Performance tests:** Usage ingestion batches, invoice finalization, dunning scans, audit/event pagination, and dashboard queries.

### PR test requirement

Before each PR:

1. Run the complete existing backend suite.
2. Run all newly introduced backend tests.
3. Run migration upgrade checks on PostgreSQL.
4. Run frontend type checking and production build.
5. Run relevant frontend unit/component tests.
6. Run impacted Playwright journeys.
7. Run integration/contract tests for changed provider boundaries.
8. Attach calculation fixtures or reconciliation output for billing changes.
9. Confirm no unreviewed schema drift.
10. Confirm retries produce no duplicate invoice, credit, charge, usage, or notification effect.

---

## 15. Security Considerations

- Strengthen tenant scoping with repository/query helpers and database constraints.
- Replace coarse role checks with named capabilities mapped to roles.
- Separate internal users from portal identities.
- Migrate browser refresh tokens away from `localStorage`.
- Hash all public, invitation, checkout, verification, and recovery tokens.
- Add purpose, audience, expiry, revocation, and single-use properties.
- Keep card/bank details in gateway-hosted/tokenized systems.
- Encrypt gateway, email, SMS, webhook, and AI credentials.
- Apply step-up authentication to refunds, gateway changes, exports, portal impersonation, and destructive dunning actions.
- Use CSP, secure headers, safe HTML/template rendering, CSRF protection, and strict redirect allow-lists.
- Implement SSRF protection for webhooks and web tabs.
- Redact PII and payment metadata from logs, AI prompts, analytics, and error messages.
- Establish data retention and deletion policies for portal files, webhook payloads, AI history, usage events, and notification content.
- Rate-limit authentication, checkout, payment attempts, usage ingestion, AI requests, and public document access.
- Add dependency, secret, SAST, and container scanning to CI.

---

## 16. Performance / Scalability Considerations

- Use set-based billing queries and indexed due-date scans.
- Claim jobs with short leases and `FOR UPDATE SKIP LOCKED`.
- Partition or archive high-volume usage, webhook, notification, audit, and outbox tables only when measured volume justifies it.
- Keep raw usage append-only and build incremental aggregates.
- Use cursor pagination for operational history.
- Cache only read models and configuration; never use a cache as authoritative billing state.
- Generate PDFs, send communications, run AI, and call external providers outside the primary database transaction.
- Add statement timeouts and batch limits to reporting and AI query tools.
- Precompute dashboard/report projections asynchronously where direct queries become expensive.
- Retain one modular application deployment initially. Scale API and worker processes independently before considering service extraction.
- Redis may later be justified for distributed rate limiting or caching, but it is not a prerequisite for the first implementation phases.

---

## 17. Risks and Architectural Concerns

1. **Migration risk:** There is no usable Alembic history.
2. **Scheduler risk:** The production command references a nonexistent function.
3. **Billing regression risk:** Core invoice/payment/subscription paths lack direct tests.
4. **Transaction risk:** Internal service commits make atomic cross-domain commands difficult.
5. **Duplicate-effects risk:** Current jobs and integrations do not have a complete idempotency model.
6. **Historical accuracy risk:** Mutable plan data can affect interpretation of older subscriptions.
7. **Frontend delivery risk:** Navigation breadth significantly exceeds functional page depth.
8. **Documentation risk:** Documents currently overstate implementation in several areas.
9. **Security risk:** Browser refresh credentials are stored in `localStorage`.
10. **Portal risk:** Permanent opaque public links are insufficient as general customer authentication.
11. **Dunning risk:** Automatic retries without durable attempts/reconciliation could double-charge.
12. **Metering risk:** Ambiguous aggregation and late-data rules can create billing disputes.
13. **Proration risk:** Undefined rounding, tax, coupon, and credit policies can produce inconsistent accounting.
14. **Automation risk:** Arbitrary custom code or unconstrained webhook calls would create tenant and infrastructure exposure.
15. **AI risk:** Hallucinated amounts or unauthorized actions could have direct financial consequences.
16. **Native-client risk:** Implementing mobile/desktop before web/API completeness would multiply incomplete behavior.

---

## 18. Product Decisions / Questions Requiring Human Confirmation

### Platform-wide

- Supported currencies and exchange-rate/reporting-currency policy.
- Tax jurisdictions and tax calculation ownership.
- Rounding mode, currency precision, and allocation of residual cents.
- Whether credit notes are sufficient or a general accounting ledger is required.
- Exact permission matrix and approval thresholds.
- Data retention, residency, export, and deletion requirements.
- SLA, recovery objectives, and supported billing volume.
- Notification providers and compliance/consent rules.

### Metered billing

- Aggregation: sum, maximum, last value, unique count, or multiple choices.
- Pricing: flat, per-unit, graduated, volume, package, minimum, or overage.
- Late-event and correction policy.
- Finalization cutoff and organization timezone.
- Negative usage and event-dimension rules.

### Proration

- Day-count and rounding rules.
- Tax and discount/coupon treatment.
- Repeated mid-cycle change behavior.
- Add-on proration.
- Interaction with unpaid, partially paid, and overdue invoices.
- Excess-credit refund policy.

### Dunning

- Supported retry count and schedule.
- Failure categories eligible for retry.
- Final actions for each segment.
- ACH-specific behavior.
- Policy version behavior for already-open cases.
- SMS/push scope and customer opt-out.

### Trials

- Repeat-trial/abuse policy.
- Entitlement after expiry.
- Free-plan fallback behavior.
- Plan changes during trial.
- Reminder cadence.
- Admin override and extension rules.

### Portal and checkout

- Portal URL/domain model.
- Contact-to-customer sharing rules.
- MFA method.
- Self-signup eligibility.
- File-storage provider and retention.
- Supported checkout purposes/gateways.
- Partial invoice payments.
- Analytics consent and iframe policy.

### Mobile and desktop

- PWA versus native client.
- Required native capabilities.
- Offline-read versus offline-write scope.
- Supported OS versions.
- Distribution, signing, and auto-update channel.

### AI

- AI provider and regional availability.
- Data use, retention, and opt-out.
- Allowed query/action tools.
- Mandatory approvals.
- Forecast/anomaly definitions and accuracy thresholds.
- Whether voice transcription is local or external.

All items above remain **UNSPECIFIED / REQUIRES PRODUCT DECISION** until explicitly approved.

---

## 19. Definition of Done

A feature is complete only when:

- Requirements and approved product decisions are traceable to implementation stories.
- Its schema has reviewed Alembic migrations and migration tests.
- Business calculations are centralized, deterministic, and independently tested.
- Transaction boundaries preserve all-or-nothing financial state.
- Commands, jobs, gateway calls, and webhooks are idempotent.
- Tenant isolation and capabilities are enforced server-side.
- Audit and outbox records accompany consequential changes.
- Async failures are visible, retryable, and operationally documented.
- Frontend screens are production-connected rather than mock/local-only.
- Public and portal experiences pass security and accessibility checks.
- API and frontend contracts are synchronized.
- Dashboards/reports reconcile against source transactions.
- Operational metrics and alerts exist.
- Relevant unit, service, API, PostgreSQL, integration, frontend, security, and end-to-end tests pass.
- The original 110-test baseline remains green.
- Documentation matches the actual deployed behavior.
- The change is implemented on `charan` or an approved feature branch, reviewed through a PR, and never directly committed to `main`.

---

## 20. Final Implementation Checklist for Antigravity

### Before feature work

- [ ] Preserve the 110-passing-test baseline.
- [ ] Create the Alembic baseline and PostgreSQL migration gate.
- [ ] Repair and test the production scheduler entry point.
- [ ] Add core invoice/payment/subscription/webhook/scheduler characterization tests.
- [ ] Establish application-owned transaction boundaries.
- [ ] Add correlation IDs, strict API module loading, and reliable error codes.
- [ ] Add idempotency, optimistic versioning, durable jobs, inbox, and outbox.

### Shared domain

- [ ] Add immutable price versions and subscription items.
- [ ] Add billing-cycle records and invoice provenance.
- [ ] Add customer payment methods and payment attempts.
- [ ] Add gateway adapter interfaces.
- [ ] Add credit notes and applications.
- [ ] Add notification templates and delivery history.
- [ ] Add capability-based authorization.
- [ ] Define stable domain events and audit requirements.

### Feature delivery

- [ ] Implement proration only after rounding/tax/credit decisions.
- [ ] Implement metering only after aggregation/rating/cutoff decisions.
- [ ] Replace unconditional trial conversion with payment-aware lifecycle rules.
- [ ] Build hosted checkout sessions before full dunning.
- [ ] Build portal identity separately from internal membership.
- [ ] Implement durable dunning policies/cases/attempts.
- [ ] Build automation on outbox/events/jobs, not direct model hooks.
- [ ] Complete responsive web workflows before native clients.
- [ ] Add AI only through permissioned, audited domain tools.

### Every PR

- [ ] Small, independently deployable scope.
- [ ] Forward and compatibility migration included.
- [ ] No client-calculated authoritative money.
- [ ] No external call inside a long database transaction.
- [ ] Retry and concurrency behavior tested.
- [ ] Tenant and permission tests included.
- [ ] Audit/outbox behavior verified.
- [ ] Complete backend and frontend gates pass.
- [ ] Documentation reflects actual behavior.
- [ ] PR targets `main` through the approved `charan → tests → PR → main` workflow.
