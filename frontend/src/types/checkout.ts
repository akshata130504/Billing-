// ---------------------------------------------------------------------------
// Hosted Payment Pages / Checkout — mirrors backend/app/schemas/checkout.py
// ---------------------------------------------------------------------------

export type CheckoutPurpose =
  | 'invoice_payment'
  | 'new_subscription'
  | 'update_subscription'
  | 'update_card'
  | 'one_time_addon'
  | 'add_payment_method';

export type CheckoutSessionStatus =
  | 'created'
  | 'pending'
  | 'processing'
  | 'successful'
  | 'failed'
  | 'cancelled'
  | 'expired';

export type CheckoutTemplateType = 'single_page' | 'multi_page';

export const CHECKOUT_PURPOSES: CheckoutPurpose[] = [
  'invoice_payment',
  'new_subscription',
  'update_subscription',
  'update_card',
  'one_time_addon',
  'add_payment_method',
];

export const CHECKOUT_STATUSES: CheckoutSessionStatus[] = [
  'created',
  'pending',
  'processing',
  'successful',
  'failed',
  'cancelled',
  'expired',
];

/** GET/POST /checkout/templates → CheckoutTemplateOut */
export interface CheckoutTemplate {
  id: string;
  organization_id: string;
  name: string;
  template_type: CheckoutTemplateType | string;
  primary_color: string;
  accent_color: string;
  logo_url: string | null;
  button_text: string;
  allow_quantity_edit: boolean;
  show_order_summary: boolean;
  redirect_url: string | null;
  thank_you_message: string | null;
  error_message_template: string | null;
  custom_fields: Record<string, unknown> | null;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** POST /checkout/templates body → CheckoutTemplateCreate */
export interface CheckoutTemplateCreate {
  name: string;
  template_type?: CheckoutTemplateType;
  primary_color?: string;
  accent_color?: string;
  logo_url?: string | null;
  button_text?: string;
  allow_quantity_edit?: boolean;
  show_order_summary?: boolean;
  redirect_url?: string | null;
  thank_you_message?: string | null;
  error_message_template?: string | null;
  custom_fields?: Record<string, unknown> | null;
  is_default?: boolean;
}

/** POST /checkout/sessions body → CheckoutSessionCreate */
export interface CheckoutSessionCreate {
  purpose: CheckoutPurpose;
  template_id?: string | null;
  customer_id?: string | null;
  invoice_id?: string | null;
  subscription_id?: string | null;
  plan_id?: string | null;
  /** Money string, e.g. "1500.00" (only used for one_time_addon). */
  amount?: string | null;
  currency?: string;
  /** 1–168 */
  expires_in_hours?: number;
  save_payment_method?: boolean;
  metadata_snapshot?: Record<string, unknown> | null;
}

/**
 * GET/POST /checkout/sessions → CheckoutSessionOut.
 * NOTE: `token` is the raw, shareable token ONLY on the POST (create) response.
 * The list endpoint returns a non-secret display reference (`ref_…`) and
 * `checkout_url: null` — the link cannot be recovered after creation.
 */
export interface CheckoutSession {
  id: string;
  organization_id: string;
  token: string;
  /** Backend-provided path (`/pay/<token>`) — the SPA mounts checkout at `/checkout/:token`. */
  checkout_url: string;
  purpose: CheckoutPurpose | string;
  status: CheckoutSessionStatus | string;
  amount: string;
  currency: string;
  /** Naive UTC timestamp (no `Z`). */
  expires_at: string;
  customer_id: string | null;
  invoice_id: string | null;
  subscription_id: string | null;
  plan_id: string | null;
  payment_attempt_id: string | null;
  payment_id: string | null;
  save_payment_method: boolean;
  completed_at: string | null;
  created_at: string;
}

export interface CheckoutSessionListParams {
  status?: CheckoutSessionStatus | string;
  page?: number;
  page_size?: number;
}

export interface CheckoutBranding {
  name?: string;
  primary_color?: string;
  accent_color?: string;
  logo_url?: string | null;
  button_text?: string;
  show_order_summary?: boolean;
  thank_you_message?: string | null;
}

/** GET /checkout/public/{token} → PublicCheckoutView */
export interface PublicCheckoutView {
  token: string;
  purpose: CheckoutPurpose | string;
  status: CheckoutSessionStatus | string;
  amount: string;
  currency: string;
  expires_at: string;
  is_expired: boolean;
  customer_name: string | null;
  customer_email: string | null;
  item_description: string;
  organization_name: string;
  branding: CheckoutBranding;
  save_payment_method_default: boolean;
  allow_save_payment_methods: boolean;
  prevent_deselecting_save_payment: boolean;
  /** Always "razorpay" today; the confirm body decides the adapter. */
  gateway: string;
  /** Present only when Razorpay is configured and the session has an amount > 0. */
  gateway_order_id: string | null;
  /** Razorpay public key id when the gateway is configured. */
  gateway_key_id: string | null;
  /** Razorpay customer id; pass to Checkout with `save: 1` so the card can be saved. */
  gateway_customer_id?: string | null;
  /** True when an online payment can be made for this link right now. */
  gateway_available?: boolean;
  /** Customer-facing explanation when online payment is unavailable. */
  gateway_message?: string | null;
}

export type CheckoutPaymentMethodType = 'card' | 'upi' | 'netbanking';

/** POST /checkout/public/{token}/confirm body → CheckoutConfirmIn */
export interface CheckoutConfirmIn {
  payment_method_type?: CheckoutPaymentMethodType;
  /** Only "razorpay" is accepted; the public endpoint rejects "manual" with 400. */
  gateway?: 'razorpay';
  razorpay_payment_id?: string | null;
  razorpay_order_id?: string | null;
  razorpay_signature?: string | null;
  gateway_token?: string | null;
  card_last4?: string | null;
  card_brand?: string | null;
  save_payment_method?: boolean;
}

/** POST /checkout/public/{token}/confirm → CheckoutConfirmOut */
export interface CheckoutConfirmOut {
  status: string;
  message: string;
  payment_id: string | null;
  invoice_id: string | null;
  subscription_id: string | null;
  redirect_url: string | null;
}
