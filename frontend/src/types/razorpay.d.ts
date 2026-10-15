/**
 * Minimal typings for Razorpay Checkout.js, which the hosted payment page
 * loads at runtime from https://checkout.razorpay.com/v1/checkout.js.
 *
 * This is a global declaration file (no imports/exports) so `window.Razorpay`
 * is typed everywhere without an explicit import.
 */

interface RazorpayCheckoutSuccess {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

interface RazorpayCheckoutPrefill {
  name?: string;
  email?: string;
  contact?: string;
}

interface RazorpayCheckoutOptions {
  key: string;
  /** Paise, integer. */
  amount: number;
  currency: string;
  name: string;
  description?: string;
  image?: string;
  order_id: string;
  /** Razorpay customer (cust_...) — with `save: 1` lets the customer save the card as a reusable token. */
  customer_id?: string;
  save?: 0 | 1;
  prefill?: RazorpayCheckoutPrefill;
  notes?: Record<string, string>;
  theme?: { color?: string };
  handler: (response: RazorpayCheckoutSuccess) => void;
  modal?: {
    ondismiss?: () => void;
    escape?: boolean;
    confirm_close?: boolean;
  };
  config?: Record<string, any>;
}

/** What Checkout.js hands back after a subscription's authentication payment. */
interface RazorpaySubscriptionCheckoutSuccess {
  razorpay_payment_id: string;
  razorpay_subscription_id: string;
  razorpay_signature: string;
}

/** Checkout for a Razorpay subscription: the amount comes from the subscription's plan, not from here. */
interface RazorpaySubscriptionCheckoutOptions {
  key: string;
  subscription_id: string;
  name: string;
  description?: string;
  image?: string;
  prefill?: RazorpayCheckoutPrefill;
  notes?: Record<string, string>;
  theme?: { color?: string };
  handler: (response: RazorpaySubscriptionCheckoutSuccess) => void;
  modal?: {
    ondismiss?: () => void;
    escape?: boolean;
    confirm_close?: boolean;
  };
}

interface RazorpayPaymentFailedEvent {
  error: {
    code?: string;
    description?: string;
    reason?: string;
    step?: string;
    source?: string;
    metadata?: { order_id?: string; payment_id?: string; subscription_id?: string };
  };
}

interface RazorpayCheckoutInstance {
  open(): void;
  close(): void;
  on(event: 'payment.failed', handler: (event: RazorpayPaymentFailedEvent) => void): void;
}

interface RazorpayCheckoutConstructor {
  new (options: RazorpayCheckoutOptions): RazorpayCheckoutInstance;
  new (options: RazorpaySubscriptionCheckoutOptions): RazorpayCheckoutInstance;
}

interface Window {
  Razorpay?: RazorpayCheckoutConstructor;
}
