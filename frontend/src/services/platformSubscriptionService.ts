import { absoluteUrl, apiClient } from './apiClient';

/**
 * The organization's own Rooman plan: the published catalog, starting a checkout and confirming it.
 * Prices, seats and modules always come from the server; nothing here decides what the organization
 * may use - only the backend activates a plan, after Razorpay confirms the payment.
 */

export interface CatalogBundle {
  key: string;
  label: string;
  description: string;
}

export interface CatalogModule {
  key: string;
  label: string;
  base: boolean;
}

export interface CatalogPrice {
  /** Smallest currency unit (paise for INR). */
  amount_minor: number;
  currency: string;
  interval: string;
  interval_count: number;
}

export type TaxTreatment = 'exclusive' | 'inclusive';

export interface PublicPlan {
  code: string;
  name: string;
  description: string;
  bundles: CatalogBundle[];
  modules: CatalogModule[];
  price: CatalogPrice;
  /** Always set for published plans; null for a sandbox test plan. */
  tax_treatment: TaxTreatment | string | null;
  seat_limit: number;
  /** A sandbox TEST plan (Razorpay Test Mode only), never a commercial offer. */
  sandbox?: boolean;
  /** The server can take a checkout for this plan right now. Display hint only; checkout re-checks. */
  purchasable: boolean;
}

export interface PublicPlanCatalog {
  catalog_version: number;
  plans: PublicPlan[];
}

export interface CheckoutSession {
  checkout_attempt_id: string;
  razorpay_key_id: string;
  razorpay_subscription_id: string;
  expires_at: string;
  /** An open checkout for the same plan was handed back instead of creating another. */
  reused: boolean;
  plan: {
    code: string;
    name: string;
    description: string;
    amount_minor: number;
    currency: string;
    interval: string;
    interval_count: number;
    tax_treatment: string | null;
    seat_limit: number;
    sandbox?: boolean;
  };
  prefill: { name?: string | null; email?: string | null };
  organization_name: string;
}

/** Only the three fields Checkout.js returns; the server checks them against its own records. */
export interface CheckoutVerifyRequest {
  razorpay_payment_id: string;
  razorpay_subscription_id: string;
  razorpay_signature: string;
}

export interface CheckoutVerifyResult {
  status: 'active' | 'pending' | 'not_paid';
  message: string;
  plan_code: string | null;
}

/** A verified payment for the organization's Rooman plan. A payment receipt, never a tax invoice. */
export interface PaymentReceipt {
  id: string;
  receipt_number: string;
  document_type: 'payment_receipt';
  note: string;
  status: 'paid';
  kind: 'initial' | 'renewal';
  cycle_number: number | null;
  amount_minor: number;
  currency: string;
  method: string | null;
  paid_at: string;
  issued_at: string;
  period_start: string | null;
  period_end: string | null;
  plan_code: string;
  plan_name: string | null;
  billing_interval: string;
  billing_interval_count: number;
  sandbox: boolean;
  mode: string;
  provider_payment_id: string;
  provider_invoice_id: string | null;
  /** The organization's billing identity when the payment was recorded (not live). */
  billed_to: {
    name: string;
    legal_name: string | null;
    email: string | null;
    address_line1: string | null;
    address_line2: string | null;
    city: string | null;
    state: string | null;
    postal_code: string | null;
    country: string | null;
    gstin: string | null;
  };
}

export interface PaymentReceiptPage {
  items: PaymentReceipt[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export type CancelPlanMode = 'at_period_end' | 'immediately';

export interface CancelPlanResult {
  /** scheduled: access continues until effective_at; cancelled: access ended at effective_at. */
  status: 'scheduled' | 'cancelled';
  effective_at: string;
  /** The cancellation was already in place; nothing new was sent to Razorpay. */
  already: boolean;
  message: string;
}

export const platformSubscriptionService = {
  /** Finance, Admin and Owner: the organization's own payment receipts, newest first. */
  listReceipts: async (page = 1): Promise<PaymentReceiptPage> => {
    const { data } = await apiClient.get<PaymentReceiptPage>('/plan-subscription/receipts', { params: { page } });
    return data;
  },

  receiptPdfUrl: (receiptId: string): string =>
    absoluteUrl(`/plan-subscription/receipts/${encodeURIComponent(receiptId)}/pdf`),

  /** Owner only. Applied by the server only after Razorpay confirms; there is no undo. */
  cancelPlan: async (mode: CancelPlanMode): Promise<CancelPlanResult> => {
    const { data } = await apiClient.post<CancelPlanResult>('/plan-subscription/cancel', { mode });
    return data;
  },

  listPlans: async (): Promise<PublicPlanCatalog> => {
    const { data } = await apiClient.get<PublicPlanCatalog>('/public/plans');
    return data;
  },

  /**
   * Sandbox TEST plans: empty unless the server allows the sandbox (local environment, explicit flag,
   * Razorpay Test Mode keys). Never part of the public catalog.
   */
  listSandboxPlans: async (): Promise<PublicPlanCatalog> => {
    const { data } = await apiClient.get<PublicPlanCatalog>('/subscription-checkout/sandbox-plans');
    return data;
  },

  startCheckout: async (planCode: string): Promise<CheckoutSession> => {
    const { data } = await apiClient.post<CheckoutSession>('/subscription-checkout', { plan_code: planCode });
    return data;
  },

  verifyCheckout: async (body: CheckoutVerifyRequest): Promise<CheckoutVerifyResult> => {
    const { data } = await apiClient.post<CheckoutVerifyResult>('/subscription-checkout/verify', {
      razorpay_payment_id: body.razorpay_payment_id,
      razorpay_subscription_id: body.razorpay_subscription_id,
      razorpay_signature: body.razorpay_signature,
    });
    return data;
  },
};
