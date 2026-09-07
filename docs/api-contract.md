# Rooman Billing — API Contract (v1)

This document is the single source of truth shared by the backend and frontend.
Backend endpoints MUST match it; frontend services MUST consume exactly these shapes.
Base path: `/api/v1`. All request/response bodies are JSON.

## Conventions

- **Auth**: `Authorization: Bearer <access_token>` on every non-public route. Access tokens are JWTs (30 min).
  Refresh tokens are opaque strings (30 days, rotating). `401` → the client calls `POST /auth/refresh` once and retries.
- **Tenant scoping**: the access token carries the organization id. Every list/detail endpoint returns only rows of that organization.
- **Roles** (ascending): `viewer` < `finance` < `admin` < `owner`. Minimum role per endpoint is listed as `[role]`. `viewer` = GET only.
- **Money**: decimals are serialised as **strings** with 2 decimals (`"1250.00"`), never floats. Currency is ISO 4217 (`"INR"`).
- **Dates**: `YYYY-MM-DD` for date fields, RFC 3339 UTC for timestamps (`2026-09-07T10:15:00Z`).
- **IDs**: UUID strings.
- **Pagination**: query `page` (default 1) and `page_size` (default 20, max 100). Response:
  `{ "items": [...], "total": 123, "page": 1, "page_size": 20, "total_pages": 7 }`
- **Filtering**: `search` (free text), `status`, `customer_id`, `date_from`, `date_to` where listed. `sort` = `field` or `-field` for descending.
- **Errors** — always this envelope, with the HTTP status:
  ```json
  { "error": { "code": "VALIDATION_ERROR", "message": "…", "details": { "fields": { "email": "invalid" } } } }
  ```
  Codes: `VALIDATION_ERROR` 422, `UNAUTHORIZED` 401, `FORBIDDEN` 403, `ENTITY_NOT_FOUND` 404, `CONFLICT` 409,
  `INVALID_STATE` 409, `RATE_LIMITED` 429, `GATEWAY_NOT_CONFIGURED` 503, `GATEWAY_ERROR` 502, `INTERNAL_SERVER_ERROR` 500.
- **Audit**: every state change writes an `audit_logs` row (see §12). Reads never do.
- **Enums** are lower-case strings exactly as in `backend/app/models/*.py`.

Shared sub-objects:

```ts
interface CustomerRef { id: string; customer_number: string; display_name: string; email: string | null }
interface UserRef { id: string; full_name: string; email: string }
interface LineItemIn  { product_id?: string|null; plan_id?: string|null; description: string; quantity: string; unit_price: string; tax_rate_pct: string }
interface LineItemOut extends LineItemIn { id: string; amount: string; position: number }
```

Totals are always computed server-side: `amount = quantity*unit_price`, `subtotal = Σamount`,
`discount_amount = round(subtotal*discount_pct/100, 2)`, `tax_amount = Σ round((amount - amount*discount_pct/100) * tax_rate_pct/100, 2)`,
`total = subtotal - discount_amount + tax_amount`. Rounding: half-up to 2 dp.

---

## 1. Health & meta (public)

- `GET /health` → `{ status: "healthy"|"degraded", project_name, version, timestamp, environment, database: {status, dialect} }`
- `GET /meta/integrations` → `{ razorpay: { enabled: boolean, key_id: string|null }, email: { enabled: boolean } }` (key_id is the public key, safe to expose)

## 2. Auth (public unless noted) — rate limited 10/min per IP on signup/login/forgot/reset

```ts
interface AuthTokens { access_token: string; refresh_token: string; token_type: "bearer"; expires_in: number }
interface MeResponse {
  user: { id; email; full_name; last_login_at: string|null; created_at };
  organization: OrganizationOut;
  membership: { id; role: "owner"|"admin"|"finance"|"viewer"; status: "active"; joined_at: string|null };
  organizations: { id: string; name: string; slug: string; role: string }[]; // all active memberships
}
```

- `POST /auth/signup` body `{ organization_name, full_name, email, password }` → 201 `AuthTokens & { me: MeResponse }`. Creates org (slug from name, unique) + owner. Rejects duplicate email (409).
- `POST /auth/login` body `{ email, password }` → `AuthTokens`. 401 on bad credentials. 5 failures lock account for 15 min (401 with message).
- `POST /auth/refresh` body `{ refresh_token }` → `AuthTokens` (old refresh token is revoked and replaced; reuse of a revoked token revokes the whole chain and returns 401).
- `POST /auth/logout` [auth] body `{ refresh_token }` → 204.
- `GET /auth/me` [auth] → `MeResponse`.
- `POST /auth/switch-organization` [auth] body `{ organization_id }` → `AuthTokens` for that org (must be an active member).
- `POST /auth/change-password` [auth] body `{ current_password, new_password }` → 204. Revokes all other refresh tokens.
- `POST /auth/forgot-password` body `{ email }` → 202 `{ message, reset_url?: string }`. Always 202 even if the email is unknown. `reset_url` is only included when SMTP is NOT configured (so the flow still works in that deployment) — it is `${FRONTEND_URL}/reset-password?token=…`.
- `POST /auth/reset-password` body `{ token, new_password }` → 204.
- `GET /auth/invitations/{token}` → `{ email, organization_name, role, invited_by: string, expires_at, user_exists: boolean }` (404 if invalid/expired).
- `POST /auth/accept-invitation` body `{ token, full_name?, password? }` → `AuthTokens`. `full_name`/`password` required when `user_exists` was false.

Password policy: ≥10 chars, mixed case, at least one digit (422 `VALIDATION_ERROR` otherwise).

## 3. Organization & settings

```ts
interface OrganizationOut {
  id; name; slug; legal_name; email; phone; website;
  address_line1; address_line2; city; state; postal_code; country;      // country ISO-2
  gstin; pan; default_currency; timezone;
  invoice_prefix; invoice_next_number; quote_prefix; quote_next_number; payment_prefix; payment_next_number;
  subscription_prefix; subscription_next_number; customer_prefix; customer_next_number;
  default_payment_terms_days: number; default_tax_rate_pct: string; discount_approval_threshold_pct: string;
  invoice_notes; invoice_terms; logo_url; created_at; updated_at;
}
```

- `GET /organization` [viewer] → `OrganizationOut`
- `PATCH /organization` [admin] partial body of the editable fields (everything except id/slug/created_at/updated_at; `*_next_number` may only be increased) → `OrganizationOut`

### Team

```ts
interface TeamMember { id /*membership id*/; user: UserRef; role; status: "invited"|"active"|"deactivated"; invited_by: UserRef|null; invite_expires_at; accepted_at; created_at }
```

- `GET /team` [viewer] → `TeamMember[]`
- `POST /team/invitations` [admin] body `{ email, role, full_name? }` → 201 `TeamMember & { invite_url?: string }` (`invite_url` returned only when SMTP is not configured). Owners can only be created by an owner. Re-inviting an `invited` member regenerates the token.
- `PATCH /team/{membership_id}` [admin] body `{ role }` → `TeamMember`. Cannot change your own role; only owners may grant/revoke `owner`; an org must keep ≥1 active owner.
- `DELETE /team/{membership_id}` [admin] → 204 (sets `deactivated`, revokes that user's refresh tokens for this org). Same guards as above.

## 4. Customers

```ts
interface CustomerOut {
  id; customer_number; display_name; company_name; email; phone; website; gstin; pan; tax_exempt: boolean;
  currency; payment_terms_days: number; status: "active"|"inactive";
  billing_address_line1; billing_address_line2; billing_city; billing_state; billing_postal_code; billing_country;
  notes; portal_url: string|null;
  contacts: { id; name; email; phone; designation; is_primary }[];
  stats?: { open_invoice_count: number; outstanding_amount: string; total_billed: string; total_paid: string; active_subscriptions: number }; // only on GET /customers/{id}
  created_at; updated_at;
}
```

- `GET /customers` [viewer] query `search,status,page,page_size,sort` → paginated `CustomerOut` (without `stats`)
- `POST /customers` [finance] body: all editable fields (`display_name` required) + `contacts?: ContactIn[]` → 201 `CustomerOut`. `customer_number` is assigned from the org sequence.
- `GET /customers/{id}` [viewer] → `CustomerOut` with `stats`
- `PATCH /customers/{id}` [finance] → `CustomerOut`
- `DELETE /customers/{id}` [admin] → 204 only if the customer has no invoices/quotes/subscriptions/payments, otherwise 409 `INVALID_STATE` (use `status: inactive` instead).
- `PUT /customers/{id}/contacts` [finance] body `ContactIn[]` (replaces the list) → `CustomerOut`
- `GET /customers/{id}/invoices` [viewer] → paginated `InvoiceOut`; `GET /customers/{id}/payments` → paginated `PaymentOut`; `GET /customers/{id}/subscriptions` → paginated `SubscriptionOut`

## 5. Catalog: products & plans

```ts
interface PlanOut { id; product_id; name; code; description; billing_interval: "one_time"|"monthly"|"quarterly"|"semiannual"|"yearly"; interval_count: number; pricing_model: "flat"|"per_unit"; unit_amount: string; currency; setup_fee: string; trial_days: number; is_active: boolean; active_subscriptions: number; created_at; updated_at }
interface ProductOut { id; name; sku; description; type: "service"|"goods"|"subscription"; unit; hsn_sac_code; tax_rate_pct: string; is_active: boolean; plans: PlanOut[]; created_at; updated_at }
```

- `GET /products` [viewer] query `search,is_active,type,page,page_size` → paginated `ProductOut` (with plans)
- `POST /products` [finance] → 201; `GET /products/{id}`; `PATCH /products/{id}` [finance]; `DELETE /products/{id}` [admin] → 204 or 409 if referenced by any invoice/quote item or plan with subscriptions.
- `GET /plans` [viewer] query `product_id,is_active,billing_interval,page,page_size` → paginated `PlanOut`
- `POST /plans` [finance] body `{ product_id, name, code, description?, billing_interval, interval_count?, pricing_model, unit_amount, currency?, setup_fee?, trial_days?, is_active? }` → 201; `GET /plans/{id}`; `PATCH /plans/{id}` [finance]; `DELETE /plans/{id}` [admin] → 204 or 409 if it has subscriptions.

## 6. Quotes

```ts
interface QuoteOut {
  id; quote_number; customer: CustomerRef; status: "draft"|"pending_approval"|"sent"|"accepted"|"declined"|"expired"|"converted";
  title; issue_date; expiry_date; currency; subtotal; discount_pct; discount_amount; tax_amount; total;
  notes; terms; items: LineItemOut[]; public_url: string|null; sent_at; accepted_at; declined_at;
  converted_invoice_id: string|null; approval_request_id: string|null; created_by: UserRef|null; created_at; updated_at;
}
```

- `GET /quotes` [viewer] query `search,status,customer_id,date_from,date_to,page,page_size,sort` → paginated
- `POST /quotes` [finance] body `{ customer_id, title?, issue_date?, expiry_date?, currency?, discount_pct?, notes?, terms?, items: LineItemIn[] }` → 201 (status `draft`)
- `GET /quotes/{id}`; `PATCH /quotes/{id}` [finance] (only while `draft`|`pending_approval`; replaces items if provided); `DELETE /quotes/{id}` [finance] only while `draft` → 204
- `POST /quotes/{id}/send` [finance] → `QuoteOut`. If `discount_pct > organization.discount_approval_threshold_pct` and no approved approval exists → status becomes `pending_approval` and an `ApprovalRequest(type=quote_discount)` is created (response still 200 with the new status). Otherwise status `sent`, `sent_at` set, email sent to customer if SMTP configured.
- `POST /quotes/{id}/mark-accepted` [finance] body `{}` → `accepted` (from `sent`)
- `POST /quotes/{id}/mark-declined` [finance] body `{ reason? }` → `declined` (from `sent`)
- `POST /quotes/{id}/convert` [finance] body `{ issue_date?, due_date? }` → 201 `InvoiceOut` (from `accepted`); quote becomes `converted` with `converted_invoice_id`.
- Public: `GET /public/quotes/{token}` → `PublicQuote` (quote + organization name/logo + customer display name); `POST /public/quotes/{token}/accept` body `{ accepted_by_name }` → `{ status: "accepted" }`; `POST /public/quotes/{token}/decline` body `{ reason? }`.

## 7. Subscriptions

```ts
interface SubscriptionOut {
  id; subscription_number; customer: CustomerRef; plan: { id; name; code; billing_interval; interval_count; unit_amount; currency; product_name: string };
  quantity: number; status: "trialing"|"active"|"past_due"|"paused"|"cancelled";
  start_date; trial_end; current_period_start; current_period_end; next_billing_date; cancel_at_period_end: boolean;
  cancelled_at; paused_at; ended_at; notes; mrr: string; /* monthly-normalised recurring amount */ created_at; updated_at;
}
```

- `GET /subscriptions` [viewer] query `search,status,customer_id,plan_id,page,page_size,sort` → paginated
- `POST /subscriptions` [finance] body `{ customer_id, plan_id, quantity?, start_date?, trial_days?: number|null /* null = plan default */, notes?, generate_first_invoice?: boolean /* default true when no trial */ }` → 201. Period = start_date → start_date + interval. If trial: status `trialing`, `trial_end` set, first period starts at trial end, no invoice yet.
- `GET /subscriptions/{id}`; `PATCH /subscriptions/{id}` [finance] body `{ quantity?, notes?, cancel_at_period_end? }`
- `POST /subscriptions/{id}/pause` [finance] → `paused`; `POST /subscriptions/{id}/resume` → `active` (period restarts today); `POST /subscriptions/{id}/cancel` body `{ at_period_end: boolean, reason? }` → `cancelled` now or `cancel_at_period_end=true`.
- `POST /subscriptions/{id}/generate-invoice` [finance] → 201 `InvoiceOut` for the current period (idempotent per period: 409 if one exists).
- `GET /subscriptions/{id}/invoices` [viewer] → paginated `InvoiceOut`

Scheduler (`backend/app/services/scheduler.py`, every `SCHEDULER_INTERVAL_MINUTES`): (a) `trialing` with `trial_end <= today` → `active`, period starts, renewal invoice generated & sent; (b) `active` with `next_billing_date <= today` → advance period, generate & send invoice (or end if `cancel_at_period_end`); (c) `sent`/`partially_paid` invoices with `due_date < today` → `overdue`, owning subscription → `past_due`; (d) dunning: overdue invoices get a reminder email every `DUNNING_REMINDER_INTERVAL_DAYS` up to `DUNNING_MAX_REMINDERS`. Also exposed as `POST /admin/jobs/run` [owner] → `{ renewals: n, trials_converted: n, marked_overdue: n, reminders_sent: n }`.

## 8. Invoices

```ts
interface InvoiceOut {
  id; invoice_number; customer: CustomerRef; subscription_id; quote_id;
  status: "draft"|"sent"|"partially_paid"|"paid"|"overdue"|"void";
  issue_date; due_date; currency; subtotal; discount_pct; discount_amount; tax_amount; total; amount_paid; amount_due;
  notes; terms; items: LineItemOut[]; public_url: string; pdf_url: string;  // `${API}/public/invoices/{token}/pdf`
  sent_at; paid_at; voided_at; void_reason; last_reminder_at; reminder_count: number; period_start; period_end;
  days_overdue: number; payments: { id; payment_number; amount /*allocated*/; method; paid_at; status }[];
  created_by: UserRef|null; created_at; updated_at;
}
```

- `GET /invoices` [viewer] query `search,status,customer_id,date_from,date_to,overdue_only,page,page_size,sort` → paginated (summary row also includes `customer`, no `payments`)
- `POST /invoices` [finance] body `{ customer_id, issue_date?, due_date? /* default issue+terms */, currency?, discount_pct?, notes?, terms?, items: LineItemIn[] }` → 201 `draft`
- `GET /invoices/{id}`; `PATCH /invoices/{id}` [finance] only while `draft`; `DELETE /invoices/{id}` [finance] only while `draft` → 204
- `POST /invoices/{id}/send` [finance] → `sent` (assigns `sent_at`; emails customer with pay link + PDF if SMTP). From `draft` only.
- `POST /invoices/{id}/send-reminder` [finance] → `InvoiceOut` (open invoices; increments `reminder_count`, sets `last_reminder_at`; sends email if SMTP).
- `POST /invoices/{id}/void` [finance] body `{ reason }` → `void` (not allowed when `amount_paid > 0` → 409).
- `POST /invoices/{id}/record-payment` [finance] body `{ amount, method: "bank_transfer"|"upi"|"card"|"cash"|"cheque"|"other", paid_at?, reference?, notes? }` → 201 `PaymentOut` (creates payment + allocation, updates invoice amounts/status, `paid` when `amount_due == 0`). 422 if amount > amount_due.
- `GET /invoices/{id}/pdf` [viewer] → `application/pdf`
- Public (hosted payment page): `GET /public/invoices/{token}` → `PublicInvoice { invoice_number, status, issue_date, due_date, currency, subtotal, discount_amount, tax_amount, total, amount_paid, amount_due, items, notes, terms, organization: { name, legal_name, email, phone, address_line1.., gstin, logo_url }, customer: { display_name, company_name, email, billing_* }, payments: [...], razorpay: { enabled, key_id } }`;
  `GET /public/invoices/{token}/pdf` → PDF.

## 9. Payments

```ts
interface PaymentOut {
  id; payment_number; customer: CustomerRef|null; amount; currency; method; gateway: "manual"|"razorpay";
  status: "pending"|"succeeded"|"failed"|"refunded"|"partially_refunded";
  reconciliation_status: "auto_matched"|"matched"|"unmatched"|"exception";
  gateway_order_id; gateway_payment_id; gateway_signature_verified: boolean; reference; paid_at; failure_reason; notes;
  amount_refunded; amount_allocated: string; amount_unallocated: string;
  allocations: { id; invoice_id; invoice_number; amount }[]; refunds: { id; amount; status; gateway_refund_id; reason; created_at }[];
  recorded_by: UserRef|null; created_at; updated_at;
}
```

- `GET /payments` [viewer] query `search,status,method,gateway,reconciliation_status,customer_id,date_from,date_to,page,page_size,sort` → paginated
- `POST /payments` [finance] body `{ customer_id, amount, method, paid_at?, reference?, notes?, allocations?: { invoice_id, amount }[] }` → 201 (unallocated remainder ⇒ `unmatched`; fully allocated ⇒ `matched`).
- `GET /payments/{id}`; `PATCH /payments/{id}` [finance] body `{ reference?, notes? }`
- `PUT /payments/{id}/allocations` [finance] body `{ allocations: { invoice_id, amount }[] }` → `PaymentOut` (replaces allocations; re-computes each affected invoice; 422 if Σ > payment amount or any allocation exceeds an invoice's due).
- `POST /payments/{id}/refund` [admin] body `{ amount, reason? }` → `PaymentOut`. For `gateway=razorpay` this calls the Razorpay refund API (503 when not configured, 502 on gateway failure). Refund reverses allocations proportionally and re-opens invoices.
- `GET /payments/reconciliation/summary` [viewer] → `{ auto_matched: n, matched: n, unmatched: n, exception: n, total: n, unallocated_amount: string }`

### Online payments (Razorpay) — public, used by the hosted page

- `POST /public/invoices/{token}/razorpay-order` body `{ amount? /* default amount_due */ }` → `{ order_id, amount /*paise integer*/, currency, key_id, payment_id /*our pending Payment id*/, prefill: { name, email, contact } }`. 503 `GATEWAY_NOT_CONFIGURED` if keys are missing; 409 if invoice is not payable.
- `POST /public/invoices/{token}/razorpay-verify` body `{ razorpay_order_id, razorpay_payment_id, razorpay_signature }` → `{ status: "succeeded", payment_number, invoice_status, amount_due }`. Verifies HMAC-SHA256(order_id|payment_id, key_secret); marks Payment `succeeded`, `auto_matched`, allocates to the invoice. Idempotent.
- `POST /webhooks/razorpay` (raw body; header `X-Razorpay-Signature`, verified against `RAZORPAY_WEBHOOK_SECRET`) → `{ received: true }`. Handles `payment.captured` (same effect as verify), `payment.failed` (Payment → `failed` with reason), `refund.processed`. Stored in `webhook_events` with idempotency on event id (`x-razorpay-event-id` header).

## 10. Control Center

- `GET /dashboard/summary` [viewer] query `range: "today"|"7_days"|"30_days"|"3_months"|"12_months"` →
  ```ts
  { currency;
    metrics: { total_revenue: string; revenue_change_pct: string|null; outstanding_amount: string; outstanding_count: number; overdue_count: number;
               active_customers: number; new_customers: number; at_risk_amount: string; at_risk_count: number };
    revenue: { mrr: string; arr: string; mrr_change_pct: string|null; trend: { label: string /* "Sep 2026" */; period_start; revenue: string; invoiced: string }[] /* last 12 months */ };
    pipeline: { draft: { count, amount }; sent: {…}; partially_paid: {…}; overdue: {…}; paid_this_period: {…} };
    customer_health: { active: n; trialing: n; past_due: n; paused: n; cancelled_this_period: n };
    recovery: { failed_payments: n; failed_amount: string; recovered_amount: string; reminders_sent: n };
    recent_transactions: PaymentOut[] /* 8 latest */;
    activity: ActivityItem[] /* 10 latest audit entries */; }
  ```
- `GET /action-center` [viewer] → `{ items: ActionItem[]; counts: { overdue, failed_payment, expiring_trial, pending_quote, pending_approval } }` where
  `ActionItem { id; category: "overdue"|"failed_payment"|"expiring_trial"|"pending_quote"|"pending_approval"; title; description; amount: string|null; customer: CustomerRef|null; entity_type; entity_id; due_info: string; urgency: "critical"|"high"|"medium"; suggested_action: "send_reminder"|"retry_payment"|"convert_trial"|"review_quote"|"review_approval" }`.
  Derived live: overdue invoices (critical if >14 days), failed payments in last 30 days, trials ending within 7 days, quotes `sent` > 3 days without response / expiring within 3 days, pending approvals.
- `GET /calendar` [viewer] query `month=YYYY-MM` → `{ events: CalendarEvent[] }` with `CalendarEvent { id; date; type: "invoice_due"|"subscription_renewal"|"trial_ending"|"quote_expiry"; title; customer: CustomerRef|null; amount: string|null; entity_type; entity_id; status }`.
- `GET /approvals` [viewer] query `status,type,page,page_size` → paginated `ApprovalOut { id; type; status; entity_type; entity_id; entity_label: string; title; justification; payload: object; requested_by: UserRef|null; reviewed_by: UserRef|null; reviewed_at; decision_note; created_at }`
- `POST /approvals/{id}/approve` [admin] body `{ note? }` → `ApprovalOut` and applies the effect (quote_discount → quote becomes `sent`; refund → refund executed; invoice_void → invoice voided). Requester cannot approve their own request (403).
- `POST /approvals/{id}/reject` [admin] body `{ note }` → `ApprovalOut` (quote returns to `draft`).
- `GET /audit-logs` [admin] query `search,action,entity_type,actor_user_id,date_from,date_to,page,page_size` → paginated `AuditLogOut { id; created_at; actor: UserRef|null; actor_label; action; entity_type; entity_id; entity_label; status: "success"|"warning"|"denied"; before_state; after_state; ip_address }`
- `GET /audit-logs/export?format=csv|json&…same filters` [admin] → file download (max 10,000 rows).
- `GET /activity` [viewer] query `category: "all"|"billing"|"customers"|"payments"|"system", page, page_size` → paginated `ActivityItem { id; title; description; timestamp; category; severity: "normal"|"warning"|"danger"|"success"; entity_type; entity_id }` (derived from audit logs).
- `GET /search?q=…&limit=20` [viewer] → `{ results: SearchResult[] }` with `SearchResult { id; category: "customers"|"invoices"|"quotes"|"products"|"subscriptions"|"payments"; title; subtitle; path /* frontend route, e.g. "/invoices/<id>" */; badge: string|null }`

### Data import
- `GET /imports/templates/{entity}` (`customers|products|plans`) [viewer] → CSV file with the header row.
  Columns — customers: `display_name*,company_name,email,phone,gstin,pan,currency,payment_terms_days,billing_address_line1,billing_address_line2,billing_city,billing_state,billing_postal_code,billing_country,notes`;
  products: `name*,sku*,description,type,unit,hsn_sac_code,tax_rate_pct,is_active`;
  plans: `product_sku*,name*,code*,billing_interval*,interval_count,pricing_model,unit_amount*,currency,setup_fee,trial_days,is_active`.
- `POST /imports/{entity}` [finance] multipart `file` (CSV, ≤5 MB, ≤5,000 rows) + form field `dry_run` (`true`/`false`) → `ImportResult { id: string|null; entity; file_name; status: "completed"|"completed_with_errors"|"failed"; dry_run: boolean; total_rows; imported_rows; failed_rows; errors: { row: number; error: string }[] /* first 100 */; preview: object[] /* first 10 parsed rows */ }`. Rows are validated; duplicates (email/sku/code within the org) are reported as row errors; valid rows are committed unless `dry_run`.
- `GET /imports` [viewer] → paginated `ImportResult` (history)

## 11. Frontend module layout (owned by the frontend build)

`frontend/src/types/api.ts` exports every interface above with these exact names:
`AuthTokens, MeResponse, OrganizationOut, TeamMember, CustomerOut, CustomerRef, ContactIn, ProductOut, PlanOut, QuoteOut, SubscriptionOut, InvoiceOut, PaymentOut, LineItemIn, LineItemOut, DashboardSummary, ActionItem, ActionCenterResponse, CalendarEvent, ApprovalOut, AuditLogOut, ActivityItem, SearchResult, ImportResult, PublicInvoice, PublicQuote, Paginated<T>, ApiError, IntegrationsMeta, UserRef` plus the string-literal unions `InvoiceStatus, QuoteStatus, SubscriptionStatus, PaymentStatus, PaymentMethod, ReconciliationStatus, MemberRole, BillingInterval, PricingModel, ProductType`.

`frontend/src/services/` one file per domain, each exporting a `const xxxService = { … }` object whose functions return the parsed `data` (not the axios response):
`authService (signup, login, refresh, logout, me, switchOrganization, changePassword, forgotPassword, resetPassword, getInvitation, acceptInvitation)`,
`organizationService (get, update, listTeam, invite, updateMemberRole, deactivateMember)`,
`customerService (list, get, create, update, remove, setContacts, invoices, payments, subscriptions)`,
`catalogService (listProducts, getProduct, createProduct, updateProduct, deleteProduct, listPlans, getPlan, createPlan, updatePlan, deletePlan)`,
`quoteService (list, get, create, update, remove, send, markAccepted, markDeclined, convert)`,
`subscriptionService (list, get, create, update, pause, resume, cancel, generateInvoice, invoices)`,
`invoiceService (list, get, create, update, remove, send, sendReminder, voidInvoice, recordPayment, pdfUrl)`,
`paymentService (list, get, create, update, setAllocations, refund, reconciliationSummary)`,
`controlCenterService (dashboard, actionCenter, calendar, listApprovals, approve, reject, auditLogs, auditExportUrl, activity, search, importTemplateUrl, runImport, listImports, runJobs)`,
`publicService (getInvoice, invoicePdfUrl, createRazorpayOrder, verifyRazorpayPayment, getQuote, acceptQuote, declineQuote, integrations)`.

`frontend/src/hooks/useAuth.tsx` — `AuthProvider` + `useAuth()` returning `{ user, organization, membership, organizations, isAuthenticated, isLoading, login, signup, logout, switchOrganization, refreshMe, hasRole(min: MemberRole) }`. Tokens persist in `localStorage` under `rooman.access_token` / `rooman.refresh_token`; the axios client attaches the access token and on 401 performs one refresh + retry, then logs out.

Frontend routes (React Router):
public: `/login`, `/signup`, `/forgot-password`, `/reset-password`, `/accept-invitation`, `/pay/:token`, `/quote/:token`;
private (inside `AppLayout`): `/dashboard`, `/customers`, `/customers/new`, `/customers/:id`, `/customers/:id/edit`, `/catalog` (products+plans), `/quotes`, `/quotes/new`, `/quotes/:id`, `/quotes/:id/edit`, `/invoices`, `/invoices/new`, `/invoices/:id`, `/invoices/:id/edit`, `/payments`, `/payments/:id`, `/collections` (overdue invoices + reminders), `/subscriptions`, `/subscriptions/new`, `/subscriptions/:id`, `/trials`, `/activity`, `/control-center/action-center`, `/control-center/approvals`, `/control-center/calendar`, `/control-center/reconciliation`, `/control-center/audit-log`, `/control-center/migration`, `/settings` (tabs: organization, billing & numbering, team, integrations, security). Any module without a real implementation renders `ComingSoonPage` (no fabricated data).

## 12. Audit actions (backend)

Use these `action` strings: `USER_SIGNED_UP, USER_LOGGED_IN, LOGIN_FAILED, USER_LOGGED_OUT, PASSWORD_CHANGED, PASSWORD_RESET_REQUESTED, PASSWORD_RESET, TEAM_MEMBER_INVITED, INVITATION_ACCEPTED, TEAM_ROLE_CHANGED, TEAM_MEMBER_DEACTIVATED, ORGANIZATION_UPDATED, CUSTOMER_CREATED, CUSTOMER_UPDATED, CUSTOMER_DELETED, PRODUCT_CREATED, PRODUCT_UPDATED, PRODUCT_DELETED, PLAN_CREATED, PLAN_UPDATED, PLAN_DELETED, QUOTE_CREATED, QUOTE_UPDATED, QUOTE_DELETED, QUOTE_SENT, QUOTE_APPROVAL_REQUESTED, QUOTE_ACCEPTED, QUOTE_DECLINED, QUOTE_CONVERTED, SUBSCRIPTION_CREATED, SUBSCRIPTION_UPDATED, SUBSCRIPTION_PAUSED, SUBSCRIPTION_RESUMED, SUBSCRIPTION_CANCELLED, SUBSCRIPTION_RENEWED, TRIAL_CONVERTED, INVOICE_CREATED, INVOICE_UPDATED, INVOICE_DELETED, INVOICE_SENT, INVOICE_REMINDER_SENT, INVOICE_MARKED_OVERDUE, INVOICE_PAID, INVOICE_VOIDED, PAYMENT_RECORDED, PAYMENT_ALLOCATED, PAYMENT_ORDER_CREATED, PAYMENT_CAPTURED, PAYMENT_FAILED, PAYMENT_REFUNDED, APPROVAL_APPROVED, APPROVAL_REJECTED, IMPORT_COMPLETED, WEBHOOK_RECEIVED, WEBHOOK_REJECTED`.
`entity_type` ∈ `user, organization, membership, customer, product, plan, quote, subscription, invoice, payment, refund, approval, import, webhook`.
