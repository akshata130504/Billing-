/**
 * API contract types — mirrors docs/api-contract.md (v1) exactly.
 * Money values are strings with 2 decimals; dates are `YYYY-MM-DD`;
 * timestamps are RFC 3339 UTC strings; IDs are UUID strings.
 */

// ---------------------------------------------------------------------------
// String-literal unions (lower-case, exactly as backend/app/models/*.py)
// ---------------------------------------------------------------------------

export type MemberRole = 'owner' | 'admin' | 'finance' | 'viewer';
export type MembershipStatus = 'invited' | 'active' | 'deactivated';
export type CustomerStatus = 'active' | 'inactive';
export type ProductType = 'service' | 'goods' | 'subscription';
export type BillingInterval = 'one_time' | 'monthly' | 'quarterly' | 'semiannual' | 'yearly';
export type PricingModel = 'flat' | 'per_unit';
export type QuoteStatus =
  | 'draft'
  | 'pending_approval'
  // Internally approved, not yet sent: the customer has no link.
  | 'approved'
  | 'sent'
  // Set when the customer opens the public link; still open for accept / decline.
  | 'viewed'
  | 'accepted'
  | 'declined'
  | 'expired'
  | 'partially_invoiced'
  | 'invoiced'
  | 'converted';
export type SubscriptionStatus = 'draft' | 'pending_activation' | 'active' | 'trialing' | 'past_due' | 'paused' | 'cancelled' | 'expired';
export type InvoiceStatus = 'draft' | 'sent' | 'partially_paid' | 'paid' | 'overdue' | 'void';
/**
 * `razorpay` is only ever set by the gateway flow; manual recording accepts
 * the remaining values (see `ManualPaymentMethod`).
 */
export type PaymentMethod = 'razorpay' | 'bank_transfer' | 'upi' | 'card' | 'cash' | 'cheque' | 'other';
export type ManualPaymentMethod = Exclude<PaymentMethod, 'razorpay'>;
export type PaymentGateway = 'manual' | 'razorpay';
export type PaymentStatus = 'pending' | 'succeeded' | 'failed' | 'refunded' | 'partially_refunded';
export type ReconciliationStatus = 'auto_matched' | 'matched' | 'unmatched' | 'exception';
export type RefundStatus = 'pending' | 'processed' | 'failed';
export type ApprovalType = 'quote_discount' | 'invoice_discount' | 'refund' | 'invoice_void';
export type ApprovalStatus = 'pending' | 'approved' | 'rejected';
export type AuditStatus = 'success' | 'warning' | 'denied';
export type ImportEntity = 'customers' | 'products' | 'plans';
export type ImportStatus = 'completed' | 'completed_with_errors' | 'failed';
export type DashboardRange = 'today' | '7_days' | '30_days' | '3_months' | '12_months';
export type ActivityCategoryFilter = 'all' | 'billing' | 'customers' | 'payments' | 'system';
export type SearchCategory =
  | 'customers'
  | 'invoices'
  | 'quotes'
  | 'products'
  | 'subscriptions'
  | 'payments'
  | 'projects'
  | 'expenses';

// ---------------------------------------------------------------------------
// Envelope / shared
// ---------------------------------------------------------------------------

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface PageParams {
  page?: number;
  page_size?: number;
  sort?: string;
}

export interface ApiErrorDetails {
  fields?: Record<string, string>;
  [key: string]: unknown;
}

export interface ApiError {
  code: string;
  message: string;
  details?: ApiErrorDetails;
  /** HTTP status when the error came from a response. */
  status?: number;
}

export interface CustomerRef {
  id: string;
  customer_number: string;
  display_name: string;
  email: string | null;
}

export interface UserRef {
  id: string;
  full_name: string;
  email: string;
  avatar_url?: string | null;
}

export interface LineItemIn {
  product_id?: string | null;
  plan_id?: string | null;
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate_pct: string;
}

export interface LineItemOut extends LineItemIn {
  id: string;
  amount: string;
  /** Per-line GST split; zero for exports and pre-GST historic rows. */
  cgst_amount: string;
  sgst_amount: string;
  igst_amount: string;
  cgst_rate_pct: string;
  sgst_rate_pct: string;
  igst_rate_pct: string;
  hsn_sac_code: string | null;
  position: number;
}

// ---------------------------------------------------------------------------
// §1 Health & meta
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: 'healthy' | 'degraded';
  project_name: string;
  version: string;
  timestamp: string;
  environment: string;
  database: { status: string; dialect: string };
}

export interface IntegrationsMeta {
  razorpay: { enabled: boolean; key_id: string | null };
  email: { enabled: boolean };
}

// ---------------------------------------------------------------------------
// §2 Auth
// ---------------------------------------------------------------------------

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

export interface MeUser {
  id: string;
  email: string;
  full_name: string;
  phone?: string | null;
  avatar_url?: string | null;
  last_login_at: string | null;
  created_at: string;
  two_factor_enabled: boolean;
}

export interface MeMembership {
  id: string;
  role: MemberRole;
  status: 'active';
  joined_at: string | null;
}

export interface MeOrganizationSummary {
  id: string;
  name: string;
  slug: string;
  role: string;
}

/** What the organization may use right now. The API enforces it; the SPA only mirrors it. */
export interface OrganizationAccess {
  /** Effective status: a trial past trial_ends_at is 'trial_expired' even before the scheduler records it. */
  status: string;
  trial_started_at: string | null;
  trial_ends_at: string | null;
  module_access: 'unrestricted' | 'trial' | 'entitled';
  modules: string[];
  /** Sidebar keys (appUi/keys.json) the organization may open. */
  nav_items: string[];
  seat_limit: number | null;
  seats_used: number;
}

export interface MeResponse {
  user: MeUser;
  organization: OrganizationOut;
  membership: MeMembership;
  organizations: MeOrganizationSummary[];
  access?: OrganizationAccess | null;
}

export type SignupResponse = AuthTokens & { me: MeResponse };

export interface SignupVerificationRequest {
  organization_name: string;
  full_name: string;
  email: string;
  /** Not needed to request the code: the password is chosen after the email is verified. */
  password?: string;
}

export interface SignupConfirmEmailRequest {
  email: string;
  otp: string;
}

export interface SignupConfirmEmailResponse {
  verification_token: string;
  expires_in_seconds: number;
}

export interface SignupCompleteRequest {
  email: string;
  verification_token: string;
  organization_name: string;
  full_name: string;
  password: string;
}

export interface SignupVerifyOtpRequest {
  email: string;
  otp: string;
  /** Must match the password submitted with request-verification. */
  password: string;
}

export interface ResendOtpRequest {
  email: string;
}

export interface SignupVerificationResponse {
  message: string;
  email: string;
  expires_in_seconds: number;
  resend_cooldown_seconds: number;
}


export interface LoginRequest {
  email: string;
  password: string;
}

export interface ForgotPasswordResponse {
  message: string;
}

export interface InvitationDetails {
  email: string;
  organization_name: string;
  role: MemberRole;
  invited_by: string;
  expires_at: string;
  user_exists: boolean;
}

export interface AcceptInvitationRequest {
  token: string;
  full_name?: string;
  /** New accounts: the password to set. Existing accounts: their current password. */
  password?: string;
  /** Existing accounts with two-factor authentication on. */
  totp_code?: string;
}

// ---------------------------------------------------------------------------
// §3 Organization & team
// ---------------------------------------------------------------------------

export interface OrganizationOut {
  id: string;
  name: string;
  slug: string;
  legal_name: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  gstin: string | null;
  pan: string | null;
  default_currency: string;
  timezone: string;
  invoice_prefix: string;
  invoice_next_number: number;
  quote_prefix: string;
  quote_next_number: number;
  payment_prefix: string;
  payment_next_number: number;
  subscription_prefix: string;
  subscription_next_number: number;
  customer_prefix: string;
  customer_next_number: number;
  default_payment_terms_days: number;
  default_tax_rate_pct: string;
  discount_approval_threshold_pct: string;
  invoice_notes: string | null;
  invoice_terms: string | null;
  logo_url: string | null;
  status?: string;
  status_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export type OrganizationUpdate = Partial<
  Omit<OrganizationOut, 'id' | 'slug' | 'created_at' | 'updated_at'>
>;

export interface TeamMember {
  id: string;
  user: UserRef;
  role: MemberRole;
  status: MembershipStatus;
  invited_by: UserRef | null;
  invite_expires_at: string | null;
  accepted_at: string | null;
  created_at: string;
}

export interface InviteRequest {
  email: string;
  role: MemberRole;
  full_name?: string;
}

export type InviteResponse = TeamMember & { invite_url?: string; email_delivered?: boolean };

// ---------------------------------------------------------------------------
// §4 Customers
// ---------------------------------------------------------------------------

export interface ContactIn {
  name: string;
  email?: string | null;
  phone?: string | null;
  designation?: string | null;
  is_primary?: boolean;
}

export interface ContactOut {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  designation: string | null;
  is_primary: boolean;
}

export interface CustomerStats {
  open_invoice_count: number;
  outstanding_amount: string;
  total_billed: string;
  total_paid: string;
  active_subscriptions: number;
}

export interface CustomerOut {
  id: string;
  customer_number: string;
  display_name: string;
  company_name: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  gstin: string | null;
  pan: string | null;
  tax_exempt: boolean;
  currency: string;
  payment_terms_days: number;
  status: CustomerStatus;
  billing_address_line1: string | null;
  billing_address_line2: string | null;
  billing_city: string | null;
  billing_state: string | null;
  billing_postal_code: string | null;
  billing_country: string | null;
  notes: string | null;
  portal_url: string | null;
  contacts: ContactOut[];
  /** Only present on GET /customers/{id}. */
  stats?: CustomerStats;
  created_at: string;
  updated_at: string;
}

export interface CustomerIn {
  display_name: string;
  company_name?: string | null;
  email?: string | null;
  phone?: string | null;
  website?: string | null;
  gstin?: string | null;
  pan?: string | null;
  tax_exempt?: boolean;
  currency?: string;
  payment_terms_days?: number;
  status?: CustomerStatus;
  billing_address_line1?: string | null;
  billing_address_line2?: string | null;
  billing_city?: string | null;
  billing_state?: string | null;
  billing_postal_code?: string | null;
  billing_country?: string | null;
  notes?: string | null;
  contacts?: ContactIn[];
}

export interface CustomerListParams extends PageParams {
  search?: string;
  status?: CustomerStatus;
}

// ---------------------------------------------------------------------------
// §5 Catalog
// ---------------------------------------------------------------------------

export interface PlanOut {
  id: string;
  product_id: string;
  name: string;
  code: string;
  description: string | null;
  billing_interval: BillingInterval;
  interval_count: number;
  pricing_model: PricingModel;
  unit_amount: string;
  currency: string;
  setup_fee: string;
  trial_days: number;
  is_active: boolean;
  active_subscriptions: number;
  created_at: string;
  updated_at: string;
}

export interface PlanIn {
  product_id: string;
  name: string;
  code: string;
  description?: string | null;
  billing_interval: BillingInterval;
  interval_count?: number;
  pricing_model: PricingModel;
  unit_amount: string;
  currency?: string;
  setup_fee?: string;
  trial_days?: number;
  is_active?: boolean;
}

export interface ProductOut {
  id: string;
  name: string;
  sku: string;
  description: string | null;
  type: ProductType;
  unit: string | null;
  hsn_sac_code: string | null;
  tax_rate_pct: string;
  is_active: boolean;
  plans: PlanOut[];
  created_at: string;
  updated_at: string;
}

export interface ProductIn {
  name: string;
  /** Optional: a SKU is generated by the backend when omitted. */
  sku?: string;
  description?: string | null;
  type?: ProductType;
  unit?: string | null;
  hsn_sac_code?: string | null;
  tax_rate_pct?: string;
  is_active?: boolean;
}

export interface ProductListParams extends PageParams {
  search?: string;
  is_active?: boolean;
  type?: ProductType;
}

export interface PlanListParams extends PageParams {
  product_id?: string;
  is_active?: boolean;
  billing_interval?: BillingInterval;
}

// ---------------------------------------------------------------------------
// §6 Quotes
// ---------------------------------------------------------------------------

export interface QuoteOut {
  id: string;
  quote_number: string;
  customer: CustomerRef;
  status: QuoteStatus;
  title: string | null;
  issue_date: string;
  expiry_date: string | null;
  currency: string;
  subtotal: string;
  discount_pct: string;
  discount_amount: string;
  tax_amount: string;
  total: string;
  notes: string | null;
  terms: string | null;
  items: LineItemOut[];
  public_url: string | null;
  sent_at: string | null;
  accepted_at: string | null;
  declined_at: string | null;
  converted_invoice_id: string | null;
  converted_subscription_id?: string | null;
  approval_request_id: string | null;
  created_by: UserRef | null;
  created_at: string;
  updated_at: string;
}

export interface QuoteIn {
  customer_id: string;
  title?: string | null;
  issue_date?: string;
  expiry_date?: string | null;
  currency?: string;
  discount_pct?: string;
  notes?: string | null;
  terms?: string | null;
  items: LineItemIn[];
}

export type QuoteUpdate = Partial<QuoteIn>;

export interface QuoteListParams extends PageParams {
  search?: string;
  status?: QuoteStatus;
  customer_id?: string;
  date_from?: string;
  date_to?: string;
}

export interface QuoteConvertRequest {
  issue_date?: string;
  due_date?: string;
}

// ---------------------------------------------------------------------------
// §7 Subscriptions
// ---------------------------------------------------------------------------

export interface SubscriptionPlanRef {
  id: string;
  name: string;
  code: string;
  billing_interval: BillingInterval;
  interval_count: number;
  unit_amount: string;
  currency: string;
  product_name: string;
  pricing_model?: string | null;
  /** 'plan' = legacy plan; 'offering' = Plans & Pricing plan (billed through a linked plan). */
  source?: 'plan' | 'offering';
  offering_id?: string | null;
  offering_pricing_model?: string | null;
}

/** GET /subscriptions/plan-options entry: a legacy plan or a recurring Plans & Pricing offering. */
export interface SubscribablePlanOption {
  id: string;
  source: 'plan' | 'offering';
  plan_id: string | null;
  offering_id: string | null;
  name: string;
  code: string;
  product_name: string;
  billing_interval: BillingInterval | null;
  interval_count: number;
  pricing_model: string;
  unit_amount: string;
  currency: string;
  tax_rate_pct: string;
  trial_days: number;
  pricing_tiers: Array<Record<string, number | null>>;
  is_active: boolean;
}

export interface SubscriptionOut {
  id: string;
  subscription_number: string;
  customer: CustomerRef;
  plan: SubscriptionPlanRef;
  quantity: number;
  status: SubscriptionStatus;
  billing_frequency?: string;
  currency?: string;
  pricing_model?: string;
  unit_price?: string;
  subtotal?: string;
  discount_amount?: string;
  tax_amount?: string;
  total_amount?: string;
  auto_renewal?: boolean;
  cancellation_reason?: string | null;
  start_date: string;
  trial_start?: string | null;
  trial_end: string | null;
  current_period_start: string;
  current_period_end: string;
  next_billing_date: string | null;
  cancel_at_period_end: boolean;
  cancelled_at: string | null;
  paused_at: string | null;
  ended_at: string | null;
  notes: string | null;
  /** Monthly-normalised recurring amount. */
  mrr: string;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionIn {
  customer_id: string;
  /** Exactly one of plan_id (legacy plan) or offering_id (Plans & Pricing plan). */
  plan_id?: string;
  offering_id?: string;
  /** Offering subscriptions only. */
  price_book_id?: string;
  quantity?: number;
  status?: SubscriptionStatus;
  billing_frequency?: string;
  auto_renewal?: boolean;
  start_date?: string;
  /** null = plan default */
  trial_days?: number | null;
  notes?: string | null;
  discount_amount?: number;
  /** default true when no trial */
  generate_first_invoice?: boolean;
}

export interface SubscriptionUpdate {
  quantity?: number;
  notes?: string | null;
  auto_renewal?: boolean;
  cancel_at_period_end?: boolean;
  billing_frequency?: string;
}

export interface SubscriptionCancelRequest {
  at_period_end: boolean;
  reason?: string;
}

export interface SubscriptionListParams extends PageParams {
  search?: string;
  status?: SubscriptionStatus;
  customer_id?: string;
  plan_id?: string;
  billing_frequency?: string;
}

export interface SubscriptionSummaryOut {
  total_subscriptions: number;
  active_count: number;
  trialing_count: number;
  paused_count: number;
  past_due_count: number;
  cancelled_count: number;
  draft_count: number;
  total_mrr: string;
  total_arr: string;
  expiring_soon_count: number;
  trial_expiring_soon_count: number;
  auto_renew_enabled_count: number;
}

// ---------------------------------------------------------------------------
// §8 Invoices
// ---------------------------------------------------------------------------

export interface InvoicePaymentRef {
  id: string;
  payment_number: string;
  /** Allocated amount. */
  amount: string;
  method: PaymentMethod;
  paid_at: string | null;
  status: PaymentStatus;
}

export interface InvoiceOut {
  id: string;
  invoice_number: string;
  customer: CustomerRef;
  subscription_id: string | null;
  quote_id: string | null;
  status: InvoiceStatus;
  issue_date: string;
  due_date: string;
  currency: string;
  subtotal: string;
  discount_pct: string;
  discount_amount: string;
  tax_amount: string;
  /** GST heads. cgst+sgst+igst always reconcile to tax_amount. */
  cgst_amount: string;
  sgst_amount: string;
  igst_amount: string;
  /** intra_state | inter_state | export */
  supply_type: string | null;
  place_of_supply_code: string | null;
  place_of_supply_name: string | null;
  customer_gstin: string | null;
  supplier_gstin: string | null;
  total: string;
  amount_paid: string;
  amount_due: string;
  notes: string | null;
  terms: string | null;
  items: LineItemOut[];
  public_url: string;
  /** `${API}/public/invoices/{token}/pdf` */
  pdf_url: string;
  sent_at: string | null;
  paid_at: string | null;
  voided_at: string | null;
  void_reason: string | null;
  last_reminder_at: string | null;
  reminder_count: number;
  period_start: string | null;
  period_end: string | null;
  days_overdue: number;
  /** Only set right after /send or /send-reminder; null on a plain fetch. */
  email_delivery_failed: boolean | null;
  /** Omitted on list rows. */
  payments?: InvoicePaymentRef[];
  created_by: UserRef | null;
  created_at: string;
  updated_at: string;
}

export interface InvoiceIn {
  customer_id: string;
  issue_date?: string;
  /** default issue + payment terms */
  due_date?: string;
  currency?: string;
  discount_pct?: string;
  notes?: string | null;
  terms?: string | null;
  items: LineItemIn[];
}

export type InvoiceUpdate = Partial<InvoiceIn>;

export interface InvoiceListParams extends PageParams {
  search?: string;
  status?: InvoiceStatus;
  customer_id?: string;
  date_from?: string;
  date_to?: string;
  overdue_only?: boolean;
}

export interface RecordPaymentRequest {
  amount: string;
  method: ManualPaymentMethod;
  paid_at?: string;
  reference?: string | null;
  notes?: string | null;
}

// ---------------------------------------------------------------------------
// §9 Payments
// ---------------------------------------------------------------------------

export interface PaymentAllocation {
  id: string;
  invoice_id: string;
  invoice_number: string;
  amount: string;
}

export interface PaymentAllocationIn {
  invoice_id: string;
  amount: string;
}

export interface RefundOut {
  id: string;
  amount: string;
  status: RefundStatus;
  gateway_refund_id: string | null;
  reason: string | null;
  created_at: string;
}

export interface PaymentOut {
  id: string;
  payment_number: string;
  customer: CustomerRef | null;
  amount: string;
  currency: string;
  method: PaymentMethod;
  gateway: PaymentGateway;
  status: PaymentStatus;
  reconciliation_status: ReconciliationStatus;
  gateway_order_id: string | null;
  gateway_payment_id: string | null;
  gateway_signature_verified: boolean;
  reference: string | null;
  paid_at: string | null;
  failure_reason: string | null;
  notes: string | null;
  amount_refunded: string;
  amount_allocated: string;
  amount_unallocated: string;
  allocations: PaymentAllocation[];
  refunds: RefundOut[];
  recorded_by: UserRef | null;
  created_at: string;
  updated_at: string;
}

export interface PaymentIn {
  customer_id: string;
  amount: string;
  method: ManualPaymentMethod;
  paid_at?: string;
  reference?: string | null;
  notes?: string | null;
  allocations?: PaymentAllocationIn[];
}

export interface PaymentUpdate {
  reference?: string | null;
  notes?: string | null;
}

export interface PaymentListParams extends PageParams {
  search?: string;
  status?: PaymentStatus;
  method?: PaymentMethod;
  gateway?: PaymentGateway;
  reconciliation_status?: ReconciliationStatus;
  customer_id?: string;
  date_from?: string;
  date_to?: string;
}

export interface RefundRequest {
  amount: string;
  reason?: string;
}

/** Money totals across every payment matching the current filters (GET /payments/summary). */
export interface PaymentsSummary {
  count: number;
  total_collected: string;
  pending_amount: string;
  total_refunded: string;
  unallocated_amount: string;
}

export interface ReconciliationSummary {
  auto_matched: number;
  matched: number;
  unmatched: number;
  exception: number;
  total: number;
  unallocated_amount: string;
}

// ---------------------------------------------------------------------------
// §8/§9 Public (hosted payment page & quote page)
// ---------------------------------------------------------------------------

export interface PublicOrganization {
  name: string;
  legal_name: string | null;
  email: string | null;
  phone: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  gstin: string | null;
  logo_url: string | null;
}

export interface PublicCustomer {
  display_name: string;
  company_name: string | null;
  email: string | null;
  billing_address_line1: string | null;
  billing_address_line2: string | null;
  billing_city: string | null;
  billing_state: string | null;
  billing_postal_code: string | null;
  billing_country: string | null;
}

export interface PublicInvoice {
  invoice_number: string;
  status: InvoiceStatus;
  issue_date: string;
  due_date: string;
  currency: string;
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  cgst_amount: string;
  sgst_amount: string;
  igst_amount: string;
  supply_type: string | null;
  place_of_supply_name: string | null;
  total: string;
  amount_paid: string;
  amount_due: string;
  items: LineItemOut[];
  notes: string | null;
  terms: string | null;
  organization: PublicOrganization;
  customer: PublicCustomer;
  payments: InvoicePaymentRef[];
  /** unavailable_reason is set when the merchant cannot take payments (e.g. suspended organization). */
  razorpay: { enabled: boolean; key_id: string | null; unavailable_reason?: string | null };
}

export interface PublicQuote {
  quote_number: string;
  status: QuoteStatus;
  title: string | null;
  issue_date: string;
  expiry_date: string | null;
  currency: string;
  subtotal: string;
  discount_pct: string;
  discount_amount: string;
  tax_amount: string;
  total: string;
  items: LineItemOut[];
  notes: string | null;
  terms: string | null;
  organization: { name: string; logo_url: string | null };
  customer: { display_name: string };
  accepted_at: string | null;
  declined_at: string | null;
  /** Set when the merchant cannot take decisions right now (e.g. suspended organization). */
  actions_unavailable_reason?: string | null;
}

export interface RazorpayOrderResponse {
  order_id: string;
  /** Paise, integer. */
  amount: number;
  currency: string;
  key_id: string;
  /** Our pending Payment id. */
  payment_id: string;
  prefill: { name: string | null; email: string | null; contact: string | null };
}

export interface RazorpayVerifyRequest {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

export interface RazorpayVerifyResponse {
  status: 'succeeded';
  payment_number: string;
  invoice_status: InvoiceStatus;
  amount_due: string;
}

// ---------------------------------------------------------------------------
// §10 Control Center
// ---------------------------------------------------------------------------

export interface DashboardMetrics {
  total_revenue: string;
  revenue_change_pct: string | null;
  outstanding_amount: string;
  outstanding_count: number;
  overdue_count: number;
  active_customers: number;
  new_customers: number;
  at_risk_amount: string;
  at_risk_count: number;
}

export interface RevenueTrendPoint {
  /** e.g. "Sep 2026" */
  label: string;
  period_start: string;
  revenue: string;
  invoiced: string;
}

export interface DashboardRevenue {
  mrr: string;
  arr: string;
  mrr_change_pct: string | null;
  /** Currency of `mrr`/`arr` (the org's base currency). */
  mrr_currency?: string | null;
  /** MRR from subscriptions billed in other currencies, per currency (not summed into `mrr`). */
  mrr_other_currencies?: Record<string, string>;
  /** Last 12 months. */
  trend: RevenueTrendPoint[];
}

export interface PipelineBucket {
  count: number;
  amount: string;
}

export interface DashboardPipeline {
  draft: PipelineBucket;
  sent: PipelineBucket;
  partially_paid: PipelineBucket;
  overdue: PipelineBucket;
  paid_this_period: PipelineBucket;
}

export interface DashboardCustomerHealth {
  active: number;
  trialing: number;
  past_due: number;
  paused: number;
  cancelled_this_period: number;
  /** Logo churn for the selected range: customers lost / customers billing at period start. */
  churned_customers?: number;
  customers_at_period_start?: number;
  /** Percentage string, null when there were no customers at period start. */
  churn_rate?: string | null;
}

export interface DashboardRecovery {
  failed_payments: number;
  failed_amount: string;
  recovered_amount: string;
  reminders_sent: number;
}

export interface DashboardSummary {
  currency: string;
  metrics: DashboardMetrics;
  revenue: DashboardRevenue;
  pipeline: DashboardPipeline;
  customer_health: DashboardCustomerHealth;
  recovery: DashboardRecovery;
  /** 8 latest. */
  recent_transactions: PaymentOut[];
  /** 10 latest audit entries. */
  activity: ActivityItem[];
}

export type ActionCategory =
  | 'overdue'
  | 'failed_payment'
  | 'expiring_trial'
  | 'pending_quote'
  | 'pending_approval';

export type ActionUrgency = 'critical' | 'high' | 'medium';

export type SuggestedAction =
  | 'send_reminder'
  | 'retry_payment'
  | 'convert_trial'
  | 'review_quote'
  | 'review_approval';

export interface ActionItem {
  id: string;
  category: ActionCategory;
  title: string;
  description: string;
  amount: string | null;
  customer: CustomerRef | null;
  entity_type: string;
  entity_id: string;
  due_info: string;
  urgency: ActionUrgency;
  suggested_action: SuggestedAction;
}

export interface ActionCenterResponse {
  items: ActionItem[];
  counts: Record<ActionCategory, number>;
}

export type CalendarEventType = 'invoice_due' | 'subscription_renewal' | 'trial_ending' | 'quote_expiry';

export interface CalendarEvent {
  id: string;
  date: string;
  type: CalendarEventType;
  title: string;
  customer: CustomerRef | null;
  amount: string | null;
  entity_type: string;
  entity_id: string;
  status: string;
}

export interface CalendarResponse {
  events: CalendarEvent[];
}

export interface ApprovalOut {
  id: string;
  type: ApprovalType;
  status: ApprovalStatus;
  entity_type: string;
  entity_id: string;
  entity_label: string;
  title: string;
  justification: string | null;
  payload: Record<string, unknown>;
  requested_by: UserRef | null;
  reviewed_by: UserRef | null;
  reviewed_at: string | null;
  decision_note: string | null;
  created_at: string;
}

export interface ApprovalListParams extends PageParams {
  status?: ApprovalStatus;
  type?: ApprovalType;
}

export interface AuditLogOut {
  id: string;
  created_at: string;
  actor: UserRef | null;
  actor_label: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  entity_label: string | null;
  status: AuditStatus;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  ip_address: string | null;
}

export interface AuditLogParams extends PageParams {
  search?: string;
  action?: string;
  entity_type?: string;
  actor_user_id?: string;
  date_from?: string;
  date_to?: string;
}

export type AuditExportFormat = 'csv' | 'json';

export type ActivitySeverity = 'normal' | 'warning' | 'danger' | 'success';

export interface ActivityItem {
  id: string;
  title: string;
  description: string;
  timestamp: string;
  category: 'billing' | 'customers' | 'payments' | 'system';
  severity: ActivitySeverity;
  entity_type: string | null;
  entity_id: string | null;
}

export interface ActivityParams extends PageParams {
  category?: ActivityCategoryFilter;
}

export interface SearchResult {
  id: string;
  category: SearchCategory;
  title: string;
  subtitle: string;
  /** Frontend route, e.g. "/invoices/<id>". */
  path: string;
  badge: string | null;
}

export interface SearchResponse {
  results: SearchResult[];
}

export interface ImportRowError {
  row: number;
  error: string;
}

export interface ImportResult {
  id: string | null;
  entity: ImportEntity;
  file_name: string;
  status: ImportStatus;
  dry_run: boolean;
  total_rows: number;
  imported_rows: number;
  failed_rows: number;
  /** First 100. */
  errors: ImportRowError[];
  /** First 10 parsed rows. */
  preview: Record<string, unknown>[];
}

// ---------------------------------------------------------------------------
// Customer Lifecycle
// ---------------------------------------------------------------------------

export type CustomerLifecycleStage =
  | 'prospect'
  | 'onboarding'
  | 'active'
  | 'renewal_due'
  | 'expansion'
  | 'at_risk'
  | 'churned';

export type HealthStatus = 'healthy' | 'neutral' | 'at_risk' | 'critical';

export interface CustomerLifecycleItem {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_number: string;
  customer_email: string | null;
  company_name: string | null;
  lifecycle_stage: CustomerLifecycleStage;
  stage_entered_at: string;
  health_status: HealthStatus;
  health_score: number;
  next_action: string | null;
  next_action_due: string | null;
  notes: string | null;
  total_spent: string;
  amount_due: string;
  active_subscriptions_count: number;
  total_invoices_count: number;
  total_quotes_count: number;
  total_billable_hours: string;
  last_activity_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LifecycleKPIs {
  total_customers: number;
  new_onboarding_count: number;
  active_customers_count: number;
  renewal_due_count: number;
  at_risk_count: number;
  churned_count: number;
  expansion_count: number;
}

export interface TimelineEvent {
  id: string;
  event_type: string;
  title: string;
  description: string | null;
  timestamp: string;
  related_entity_type: string | null;
  related_entity_id: string | null;
  status: string | null;
  actor_label: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface CustomerLifecycleDetail {
  customer: {
    id: string;
    customer_number: string;
    display_name: string;
    company_name: string | null;
    email: string | null;
    phone: string | null;
    website: string | null;
    gstin: string | null;
    currency: string;
    payment_terms_days: number;
    billing_city: string | null;
    billing_state: string | null;
    billing_country: string;
    created_at: string | null;
  };
  lifecycle: CustomerLifecycleItem;
  timeline: TimelineEvent[];
  subscriptions: Array<{
    id: string;
    subscription_number: string;
    status: string;
    billing_frequency: string;
    total_amount: string;
    start_date: string | null;
    current_period_end: string | null;
    next_billing_date: string | null;
  }>;
  quotes: Array<{
    id: string;
    quote_number: string;
    status: string;
    total: string;
    issue_date: string | null;
    expiry_date: string | null;
  }>;
  invoices: Array<{
    id: string;
    invoice_number: string;
    status: string;
    total: string;
    amount_paid: string;
    amount_due: string;
    issue_date: string | null;
    due_date: string | null;
  }>;
  payments: Array<{
    id: string;
    payment_number: string;
    amount: string;
    status: string;
    payment_date: string | null;
    method: string;
    reference: string | null;
  }>;
  timesheet_summary: {
    total_entries: number;
    total_hours: string;
    billable_hours: string;
    non_billable_hours: string;
    billable_amount: string;
    unbilled_amount: string;
    billed_amount: string;
    recent_entries: Array<{
      id: string;
      date: string | null;
      project_name: string;
      duration_hours: string;
      description: string;
      billable: boolean;
      status: string;
      billable_amount: string;
    }>;
  };
}

export interface CustomerLifecycleUpdate {
  lifecycle_stage?: CustomerLifecycleStage;
  health_status?: HealthStatus;
  health_score?: number;
  next_action?: string | null;
  next_action_due?: string | null;
  notes?: string | null;
}

// ---------------------------------------------------------------------------
// Timesheets & Time Tracking
// ---------------------------------------------------------------------------

export type TimeEntryStatus = 'draft' | 'submitted' | 'approved' | 'rejected' | 'billed';

export interface TimeEntryRead {
  id: string;
  organization_id: string;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  customer_id: string | null;
  customer_name: string | null;
  customer_number: string | null;
  project_id: string | null;
  project_name: string | null;
  date: string;
  start_time: string | null;
  end_time: string | null;
  duration_hours: string;
  description: string;
  billable: boolean;
  billing_rate: string;
  billable_amount: string;
  status: TimeEntryStatus;
  invoice_id: string | null;
  invoice_number: string | null;
  rejection_reason: string | null;
  approved_by_id: string | null;
  approved_by_name: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TimeEntryCreate {
  customer_id?: string | null;
  project_id?: string | null;
  project_name?: string | null;
  date: string;
  start_time?: string | null;
  end_time?: string | null;
  duration_hours: number | string;
  description: string;
  billable?: boolean;
  billing_rate?: number | string;
}

export interface TimeEntryUpdate {
  customer_id?: string | null;
  project_id?: string | null;
  project_name?: string | null;
  date?: string;
  start_time?: string | null;
  end_time?: string | null;
  duration_hours?: number | string;
  description?: string;
  billable?: boolean;
  billing_rate?: number | string;
}

export interface TimeEntrySummaryKPIs {
  total_hours: string;
  billable_hours: string;
  non_billable_hours: string;
  billable_amount: string;
  unbilled_amount: string;
  billed_amount: string;
  pending_approval_count: number;
}

export interface WeeklyMatrixRow {
  key: string;
  user_id: string;
  user_name: string;
  customer_id: string | null;
  customer_name: string | null;
  project_id: string | null;
  project_name: string | null;
  daily_hours: Record<string, string>;
  total_hours: string;
  billable_hours: string;
  billable_amount: string;
}

export interface WeeklyTimesheetResponse {
  week_start: string;
  week_end: string;
  total_hours: string;
  billable_hours: string;
  non_billable_hours: string;
  rows: WeeklyMatrixRow[];
  day_totals: Record<string, string>;
}

export interface TimesheetInvoiceCreate {
  customer_id: string;
  time_entry_ids: string[];
  issue_date?: string | null;
  due_date?: string | null;
  notes?: string | null;
}
