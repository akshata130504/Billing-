import { useCallback, useEffect, useRef, useState } from 'react';
import { toApiError } from '../../services/apiClient';
import { platformSubscriptionService, type PublicPlan } from '../../services/platformSubscriptionService';
import { loadRazorpayCheckout } from '../public/razorpayLoader';
import type { ApiError } from '../../types/api';
import { formatDateTime } from '../../utils/format';

export type CheckoutPhase = 'idle' | 'starting' | 'open' | 'verifying';

export interface CheckoutNotice {
  tone: 'success' | 'info' | 'warning' | 'error';
  title: string;
  message: string;
}

interface Options {
  /** Re-read /auth/me: the only way the page learns that a plan is active. */
  refreshMe: () => Promise<unknown>;
  /** Re-read the catalog after the server says a plan or checkout is not available. */
  refreshPlans: () => void;
}

/** The specific reason: conflicts carry it in details.code under a generic top-level CONFLICT. */
export function checkoutErrorCode(error: ApiError): string {
  const detail = error.details?.code;
  return typeof detail === 'string' ? detail : error.code;
}

const UNAVAILABLE_CODES = new Set([
  'CHECKOUT_UNAVAILABLE',
  'CHECKOUT_NOT_READY',
  'GATEWAY_NOT_CONFIGURED',
  'LIVE_CHECKOUT_DISABLED',
]);

function startFailure(error: ApiError): CheckoutNotice {
  const code = checkoutErrorCode(error);
  switch (code) {
    case 'PLAN_NOT_AVAILABLE':
      return { tone: 'warning', title: 'Plan not available', message: 'This plan is no longer available. The list of plans has been refreshed.' };
    case 'SUBSCRIPTION_ALREADY_ACTIVE':
      return { tone: 'info', title: 'You already have a plan', message: error.message };
    case 'SEATS_EXCEED_PLAN':
      return { tone: 'warning', title: 'Too many users for this plan', message: error.message };
    case 'CHECKOUT_IN_PROGRESS': {
      const until = typeof error.details?.expires_at === 'string' ? formatDateTime(error.details.expires_at) : null;
      return {
        tone: 'warning',
        title: 'Another checkout is open',
        message: until
          ? `A checkout for another plan is still open. Complete it, or choose again after ${until}.`
          : error.message,
      };
    }
    case 'PAYMENT_IN_PROGRESS':
      return { tone: 'info', title: 'Payment being confirmed', message: error.message };
    case 'GATEWAY_ERROR':
      return { tone: 'error', title: 'Razorpay is not responding', message: 'Razorpay could not be reached. Nothing was charged. Please try again in a moment.' };
    case 'FORBIDDEN':
      return { tone: 'error', title: 'Owner only', message: 'Only the organization Owner can choose a plan.' };
    default:
      if (UNAVAILABLE_CODES.has(code)) {
        return { tone: 'warning', title: 'Checkout unavailable', message: 'Plan checkout is not available right now. Nothing was charged. Please try again later.' };
      }
      return { tone: 'error', title: 'Could not start checkout', message: error.message };
  }
}

function verifyFailure(error: ApiError): CheckoutNotice {
  switch (checkoutErrorCode(error)) {
    case 'PAYMENT_CONFIRMATION_DELAYED':
      return {
        tone: 'info',
        title: 'Waiting for Razorpay',
        message: 'Razorpay has not confirmed the payment yet. Your plan starts as soon as it does - check back here in a few minutes.',
      };
    case 'PAYMENT_NEEDS_REVIEW':
      return { tone: 'warning', title: 'Payment under review', message: error.message };
    case 'PAYMENT_SIGNATURE_INVALID':
    case 'CHECKOUT_NOT_FOUND':
      return {
        tone: 'error',
        title: 'Payment could not be confirmed',
        message: 'We could not match this payment to your checkout. Your plan has not changed. If you were charged, contact Rooman support.',
      };
    case 'NETWORK_ERROR':
    case 'TIMEOUT':
      return {
        tone: 'warning',
        title: 'Confirmation not received',
        message: 'We could not reach the server to confirm the payment. If it went through, your plan starts once Razorpay confirms it - check back here shortly.',
      };
    default:
      return { tone: 'error', title: 'Payment could not be confirmed', message: error.message };
  }
}

/**
 * Owner checkout for a Rooman plan. The flow only ever asks the server: start a checkout, open Razorpay
 * with the subscription it created, send Razorpay's three callback fields back for verification, then
 * re-read /auth/me. Nothing is unlocked from the callback itself, and a closed or failed window grants
 * nothing. One checkout at a time: a second click while one is in flight is ignored.
 */
export function useSubscriptionCheckout({ refreshMe, refreshPlans }: Options) {
  const [phase, setPhase] = useState<CheckoutPhase>('idle');
  const [planCode, setPlanCode] = useState<string | null>(null);
  const [notice, setNotice] = useState<CheckoutNotice | null>(null);
  const busy = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const finish = useCallback((next: CheckoutNotice | null) => {
    busy.current = false;
    if (!mounted.current) return;
    setPhase('idle');
    setPlanCode(null);
    if (next) setNotice(next);
  }, []);

  const verify = useCallback(
    async (response: RazorpaySubscriptionCheckoutSuccess) => {
      if (mounted.current) setPhase('verifying');
      try {
        const result = await platformSubscriptionService.verifyCheckout({
          razorpay_payment_id: response.razorpay_payment_id,
          razorpay_subscription_id: response.razorpay_subscription_id,
          razorpay_signature: response.razorpay_signature,
        });
        await refreshMe().catch(() => undefined);
        if (result.status === 'active') finish({ tone: 'success', title: 'Plan active', message: result.message });
        else if (result.status === 'pending') finish({ tone: 'info', title: 'Waiting for Razorpay', message: result.message });
        else finish({ tone: 'warning', title: 'No payment completed', message: result.message });
      } catch (err) {
        finish(verifyFailure(toApiError(err)));
      }
    },
    [finish, refreshMe]
  );

  const choosePlan = useCallback(
    async (plan: PublicPlan) => {
      if (busy.current) return;
      busy.current = true;
      setPhase('starting');
      setPlanCode(plan.code);
      setNotice(null);

      let session;
      try {
        session = await platformSubscriptionService.startCheckout(plan.code);
      } catch (err) {
        const error = toApiError(err);
        const code = checkoutErrorCode(error);
        if (code === 'PLAN_NOT_AVAILABLE' || UNAVAILABLE_CODES.has(code)) refreshPlans();
        if (code === 'SUBSCRIPTION_ALREADY_ACTIVE') void refreshMe().catch(() => undefined);
        finish(startFailure(error));
        return;
      }

      let Razorpay: RazorpayCheckoutConstructor;
      try {
        Razorpay = await loadRazorpayCheckout();
      } catch (err) {
        finish({ tone: 'error', title: 'Could not open Razorpay', message: toApiError(err).message });
        return;
      }
      if (!mounted.current) {
        busy.current = false;
        return;
      }

      const until = formatDateTime(session.expires_at);
      let settled = false;
      const checkout = new Razorpay({
        key: session.razorpay_key_id,
        subscription_id: session.razorpay_subscription_id,
        name: 'Rooman Billing',
        description: `${session.plan.name} plan`,
        prefill: { name: session.prefill.name ?? undefined, email: session.prefill.email ?? undefined },
        theme: { color: '#2563eb' },
        handler: (response) => {
          if (settled) return;
          settled = true;
          void verify(response);
        },
        modal: {
          ondismiss: () => {
            if (settled) return;
            settled = true;
            finish({
              tone: 'info',
              title: 'Checkout closed',
              message: `No payment was confirmed, so your plan has not changed. You can reopen this checkout until ${until}.`,
            });
          },
        },
      });
      checkout.on('payment.failed', (event) => {
        // Razorpay keeps its window open so the customer can retry; nothing is granted either way.
        if (!mounted.current) return;
        setNotice({
          tone: 'warning',
          title: 'Payment did not go through',
          message: event.error.description || 'Razorpay declined the payment. You can try again in the Razorpay window.',
        });
      });
      setPhase('open');
      checkout.open();
    },
    [finish, refreshMe, refreshPlans, verify]
  );

  return {
    phase,
    planCode,
    notice,
    busy: phase !== 'idle',
    choosePlan,
    dismissNotice: () => setNotice(null),
    /** Other plan actions on the page (cancellation) report through the same notice. */
    showNotice: setNotice,
  };
}
