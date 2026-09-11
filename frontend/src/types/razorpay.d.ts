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
