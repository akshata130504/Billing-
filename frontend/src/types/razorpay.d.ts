/**
 * Minimal typings for Razorpay Checkout.js, which the hosted payment page
 * loads at runtime from https://checkout.razorpay.com/v1/checkout.js.
 *
 * This is a global declaration file (no imports/exports) so `window.Razorpay`
 * is typed everywhere without an explicit import.
 */

interface RazorpayCheckoutSuccess {
  /** Order payments (absent for a subscription authorisation). */
  razorpay_order_id: string;
  /** Subscription (mandate) authorisations. */
  razorpay_subscription_id?: string;
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
  /** Paise, integer. Not sent for a subscription (the plan sets it). */
  amount?: number;
  currency?: string;
  name: string;
  description?: string;
  image?: string;
  /** One of order_id (a payment) or subscription_id (authorise a UPI AutoPay / e-mandate). */
  order_id?: string;
  subscription_id?: string;
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

interface RazorpayPaymentFailedEvent {
  error: {
    code?: string;
    description?: string;
    reason?: string;
    step?: string;
    source?: string;
    metadata?: { order_id?: string; payment_id?: string };
  };
}

interface RazorpayCheckoutInstance {
  open(): void;
  close(): void;
  on(event: 'payment.failed', handler: (event: RazorpayPaymentFailedEvent) => void): void;
}

interface RazorpayCheckoutConstructor {
  new (options: RazorpayCheckoutOptions): RazorpayCheckoutInstance;
}

interface Window {
  Razorpay?: RazorpayCheckoutConstructor;
}
