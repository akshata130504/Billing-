/**
 * Razorpay Checkout.js loader shared by the hosted (no-auth) pages.
 *
 * The script is injected on demand rather than in index.html so the SPA does
 * not pull a third-party script on every page load. Idempotent: concurrent
 * callers share one promise and an already-present tag is reused.
 */

const RAZORPAY_SCRIPT_SRC = 'https://checkout.razorpay.com/v1/checkout.js';
let razorpayScriptPromise: Promise<RazorpayCheckoutConstructor> | null = null;

export function loadRazorpayCheckout(): Promise<RazorpayCheckoutConstructor> {
  if (window.Razorpay) return Promise.resolve(window.Razorpay);
  if (razorpayScriptPromise) return razorpayScriptPromise;

  razorpayScriptPromise = new Promise<RazorpayCheckoutConstructor>((resolve, reject) => {
    const settle = () => {
      if (window.Razorpay) resolve(window.Razorpay);
      else {
        razorpayScriptPromise = null;
        reject(new Error('Razorpay Checkout did not initialise. Please refresh and try again.'));
      }
    };
    const fail = () => {
      razorpayScriptPromise = null;
      reject(new Error('Could not load Razorpay Checkout. Check your connection and try again.'));
    };

    const existing = document.querySelector<HTMLScriptElement>(`script[src="${RAZORPAY_SCRIPT_SRC}"]`);
    if (existing) {
      existing.addEventListener('load', settle, { once: true });
      existing.addEventListener('error', fail, { once: true });
      return;
    }
    const script = document.createElement('script');
    script.src = RAZORPAY_SCRIPT_SRC;
    script.async = true;
    script.addEventListener('load', settle, { once: true });
    script.addEventListener('error', fail, { once: true });
    document.body.appendChild(script);
  });

  return razorpayScriptPromise;
}
