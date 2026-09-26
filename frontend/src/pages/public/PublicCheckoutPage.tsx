import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { AlertCircle, CheckCircle2, Clock, CreditCard, Link2Off, Lock, ShieldCheck } from 'lucide-react';
import { checkoutService } from '../../services/checkoutService';
import type {
  CheckoutConfirmIn,
  CheckoutConfirmOut,
  PublicCheckoutView,
} from '../../types/checkout';
import type { ApiError } from '../../types/api';
import { Button } from '../../components/common/Button';
import { formatDateTime, formatMoney } from '../../utils/format';
import { PublicCard, PublicLoading, PublicMessage, PublicShell } from './PublicShell';
import { loadRazorpayCheckout } from './razorpayLoader';
import { RoomanLogo } from '../../components/common/RoomanLogo';

const PURPOSE_LABELS: Record<string, string> = {
  invoice_payment: 'Invoice payment',
  new_subscription: 'New subscription',
  update_subscription: 'Subscription update',
  update_card: 'Update saved card',
  one_time_addon: 'One-time add-on',
  add_payment_method: 'Add a payment method',
};

/** Statuses that mean the session has already run its course. */
const CLOSED_STATUSES = new Set(['successful', 'cancelled', 'expired']);

export function PublicCheckoutPage() {
  const { token = '' } = useParams<{ token: string }>();

  const [view, setView] = useState<PublicCheckoutView | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);
  const [result, setResult] = useState<CheckoutConfirmOut | null>(null);
  const [savePaymentMethod, setSavePaymentMethod] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setLoadError(null);
    try {
      const data = await checkoutService.getPublic(token);
      setView(data);
      setSavePaymentMethod(data.save_payment_method_default);
    } catch (err) {
      setLoadError((err as ApiError).message || 'This payment link could not be opened.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const branding = view?.branding ?? {};
  const primaryColor = branding.primary_color || '#2563eb';
  const buttonLabel = branding.button_text || 'Pay Now';
  const amountNumber = useMemo(() => Number(view?.amount ?? 0), [view]);
  const canPayOnline = Boolean(
    (view?.gateway_available ?? true) && view?.gateway_key_id && view?.gateway_order_id && amountNumber > 0
  );

  const confirm = useCallback(
    async (body: CheckoutConfirmIn) => {
      const outcome = await checkoutService.confirmPublic(token, body);
      setResult(outcome);
      if (outcome.redirect_url) {
        window.setTimeout(() => {
          window.location.href = outcome.redirect_url as string;
        }, 2500);
      }
    },
    [token]
  );

  const handlePay = useCallback(async () => {
    if (!view) return;
    setPayError(null);
    setPaying(true);
    try {
      if (!canPayOnline) {
        // Never "confirm" without a gateway payment: an unauthenticated page must not
        // be able to mark anything paid. The customer is told to contact the merchant.
        setPayError(
          view.gateway_message ||
            `Online payment is currently unavailable for this link. Please contact ${view.organization_name} to complete your payment.`
        );
        return;
      }
      const Razorpay = await loadRazorpayCheckout();
      const checkout = new Razorpay({
        key: view.gateway_key_id as string,
        amount: Math.round(amountNumber * 100),
        currency: view.currency || 'INR',
        name: view.organization_name,
        description: view.item_description || PURPOSE_LABELS[view.purpose] || 'Payment',
        order_id: view.gateway_order_id as string,
        ...(savePaymentMethod && view.gateway_customer_id ? { customer_id: view.gateway_customer_id, save: 1 as const } : {}),
        image: branding.logo_url || undefined,
        prefill: {
          name: view.customer_name || undefined,
          email: view.customer_email || undefined,
        },
        theme: { color: primaryColor },
        handler: (response) => {
          void (async () => {
            try {
              await confirm({
                gateway: 'razorpay',
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
                save_payment_method: savePaymentMethod,
              });
            } catch (err) {
              setPayError((err as ApiError).message || 'We could not confirm your payment.');
            } finally {
              setPaying(false);
            }
          })();
        },
        modal: {
          ondismiss: () => setPaying(false),
        },
      });
      checkout.on('payment.failed', (event) => {
        setPayError(event.error?.description || 'The payment attempt failed. Please try again.');
        setPaying(false);
      });
      checkout.open();
      return; // handler/ondismiss clears `paying`
    } catch (err) {
      setPayError((err as ApiError).message || 'The payment could not be started.');
    } finally {
      if (!canPayOnline) setPaying(false);
    }
  }, [view, canPayOnline, amountNumber, branding.logo_url, primaryColor, savePaymentMethod, confirm]);

  if (loading) return <PublicLoading message="Opening your secure checkout..." />;

  if (loadError || !view) {
    return (
      <PublicMessage
        tone="danger"
        icon={<Link2Off className="w-6 h-6" />}
        title="This payment link is not available"
        message={loadError || 'The link may have expired or already been used. Please ask for a fresh link.'}
      />
    );
  }

  if (result) {
    const ok = result.status === 'successful' || result.status === 'succeeded';
    return (
      <PublicMessage
        tone={ok ? 'neutral' : 'danger'}
        icon={ok ? <CheckCircle2 className="w-6 h-6 text-emerald-600" /> : <AlertCircle className="w-6 h-6" />}
        title={ok ? 'Payment complete' : 'Payment not completed'}
        message={
          <>
            <p>{branding.thank_you_message || result.message}</p>
            {result.redirect_url && <p className="mt-2 text-xs">Redirecting you now...</p>}
          </>
        }
      />
    );
  }

  if (view.is_expired || CLOSED_STATUSES.has(view.status)) {
    const expired = view.is_expired || view.status === 'expired';
    return (
      <PublicMessage
        icon={expired ? <Clock className="w-6 h-6" /> : <CheckCircle2 className="w-6 h-6 text-emerald-600" />}
        title={
          view.status === 'successful'
            ? 'This payment has already been completed'
            : expired
              ? 'This payment link has expired'
              : 'This payment link was cancelled'
        }
        message={
          view.status === 'successful'
            ? 'No further action is needed. Contact us if you need a receipt.'
            : `Please request a new link from ${view.organization_name}.`
        }
      />
    );
  }

  return (
    <PublicShell width="md">
      <div className="flex justify-center mb-6">
        {branding.logo_url ? (
          <img src={branding.logo_url} alt={view.organization_name} className="h-10 object-contain" />
        ) : (
          <RoomanLogo variant="brand" size="lg" showBillingBadge />
        )}
      </div>

      <PublicCard className="overflow-hidden">
        <div className="px-6 py-5 border-b border-slate-100" style={{ backgroundColor: `${primaryColor}0D` }}>
          <p className="text-[11px] font-bold uppercase tracking-wider" style={{ color: primaryColor }}>
            {PURPOSE_LABELS[view.purpose] || 'Secure checkout'}
          </p>
          <h1 className="mt-1 text-lg font-bold text-slate-900 tracking-tight">{view.organization_name}</h1>
          {view.customer_name && <p className="text-xs text-slate-500 mt-0.5">Billed to {view.customer_name}</p>}
        </div>

        <div className="px-6 py-6">
          {branding.show_order_summary !== false && (
            <div className="rounded-xl border border-slate-200 divide-y divide-slate-100">
              <div className="flex items-start justify-between gap-4 px-4 py-3">
                <span className="text-sm text-slate-600">{view.item_description || 'Amount payable'}</span>
                <span className="text-sm font-semibold text-slate-900 whitespace-nowrap">
                  {formatMoney(view.amount, view.currency)}
                </span>
              </div>
              <div className="flex items-center justify-between px-4 py-3 bg-slate-50/70">
                <span className="text-sm font-semibold text-slate-700">Total due</span>
                <span className="text-xl font-bold text-slate-900">{formatMoney(view.amount, view.currency)}</span>
              </div>
            </div>
          )}

          {view.allow_save_payment_methods && (
            <label className="mt-4 flex items-start gap-2.5 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={savePaymentMethod}
                disabled={view.prevent_deselecting_save_payment}
                onChange={(e) => setSavePaymentMethod(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500 disabled:opacity-60"
              />
              <span>
                Save this payment method for future billing
                {view.prevent_deselecting_save_payment && (
                  <span className="block text-[11px] text-slate-400">Required for this subscription.</span>
                )}
              </span>
            </label>
          )}

          {!canPayOnline && (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
              {view.gateway_message ||
                `Online payment is currently unavailable for this link. Please contact ${view.organization_name} to complete your payment.`}
            </div>
          )}

          {payError && (
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{payError}</span>
            </div>
          )}

          <Button
            className="mt-5 w-full"
            size="lg"
            isLoading={paying}
            disabled={!canPayOnline}
            onClick={() => void handlePay()}
            leadingIcon={canPayOnline ? <CreditCard className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
            style={{ backgroundColor: primaryColor, borderColor: primaryColor }}
          >
            {canPayOnline ? `${buttonLabel} ${formatMoney(view.amount, view.currency)}` : 'Online payment unavailable'}
          </Button>

          <div className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
            <Lock className="w-3 h-3" />
            {canPayOnline ? 'Secured by Razorpay' : 'Secure link'}
            <span aria-hidden="true">&middot;</span>
            Expires {formatDateTime(view.expires_at)}
          </div>
        </div>
      </PublicCard>
    </PublicShell>
  );
}
