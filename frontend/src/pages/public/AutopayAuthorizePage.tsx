import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { AlertCircle, CheckCircle2, Clock, Link2Off, Lock, Repeat } from 'lucide-react';
import { publicService } from '../../services/publicService';
import type { ApiError, PublicAutopay } from '../../types/api';
import { Button } from '../../components/common/Button';
import { formatDate, formatMoney } from '../../utils/format';
import { PublicCard, PublicLoading, PublicMessage, PublicShell } from './PublicShell';
import { loadRazorpayCheckout } from './razorpayLoader';
import { RoomanLogo } from '../../components/common/RoomanLogo';

/** "every month", "every 3 months", "every year" for a Razorpay plan period. */
export function cycleLabel(period: string, interval: number): string {
  const unit = period === 'yearly' ? 'year' : period === 'weekly' ? 'week' : period === 'daily' ? 'day' : 'month';
  return interval > 1 ? `every ${interval} ${unit}s` : `every ${unit}`;
}

const AUTHORISED = new Set(['authenticated', 'active']);

/**
 * /autopay/:token - the customer authorises a UPI AutoPay / e-mandate for their subscription through
 * Razorpay's own Checkout (subscription_id): Checkout offers the mandate methods the merchant account
 * supports (UPI AutoPay, cards, net-banking e-mandate). The page never decides the outcome itself:
 * the server verifies the signature and re-reads the subscription from Razorpay.
 */
export function AutopayAuthorizePage() {
  const { token = '' } = useParams<{ token: string }>();
  const [view, setView] = useState<PublicAutopay | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setLoadError(null);
    try {
      setView(await publicService.getAutopay(token));
    } catch (err) {
      setLoadError((err as ApiError).message || 'This AutoPay link could not be opened.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const authorize = useCallback(async () => {
    if (!view?.can_authorize || !view.key_id || !view.gateway_subscription_id) return;
    setError(null);
    setBusy(true);
    try {
      const Razorpay = await loadRazorpayCheckout();
      const checkout = new Razorpay({
        key: view.key_id,
        subscription_id: view.gateway_subscription_id,
        name: view.organization_name,
        description: `${view.plan_name} - AutoPay ${cycleLabel(view.period, view.interval)}`,
        prefill: {
          name: view.prefill.name || undefined,
          email: view.prefill.email || undefined,
          contact: view.prefill.contact || undefined,
        },
        handler: (response) => {
          void (async () => {
            try {
              const result = await publicService.confirmAutopay(token, {
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_subscription_id: response.razorpay_subscription_id || view.gateway_subscription_id || '',
                razorpay_signature: response.razorpay_signature,
              });
              setView(result);
              // Razorpay may confirm a moment later (e.g. a UPI approval still in flight): the webhook
              // completes it; tell the customer instead of claiming success.
              setWaiting(!AUTHORISED.has(result.status));
            } catch (err) {
              setError((err as ApiError).message || 'We could not verify the authorisation.');
            } finally {
              setBusy(false);
            }
          })();
        },
        modal: { ondismiss: () => setBusy(false) },
      });
      checkout.on('payment.failed', (event) => {
        setError(event.error?.description || 'The authorisation did not go through. Please try again.');
        setBusy(false);
      });
      checkout.open();
    } catch (err) {
      setError((err as ApiError).message || 'AutoPay could not be started.');
      setBusy(false);
    }
  }, [view, token]);

  if (loading) return <PublicLoading message="Opening your AutoPay request..." />;

  if (loadError || !view) {
    return (
      <PublicMessage
        tone="danger"
        icon={<Link2Off className="w-6 h-6" />}
        title="This AutoPay link is not available"
        message={loadError || 'The link may have expired or been replaced. Please ask for a fresh link.'}
      />
    );
  }

  const amount = formatMoney(view.amount, view.currency);
  const cycle = cycleLabel(view.period, view.interval);

  if (AUTHORISED.has(view.status)) {
    return (
      <PublicMessage
        icon={<CheckCircle2 className="w-6 h-6 text-emerald-600" />}
        title="AutoPay is set up"
        message={`${amount} will be collected ${cycle} for ${view.plan_name} (${view.subscription_number})${
          view.start_at ? `, starting ${formatDate(view.start_at)}` : ''
        }. You can close this page.`}
      />
    );
  }

  if (waiting) {
    return (
      <PublicMessage
        icon={<Clock className="w-6 h-6" />}
        title="Waiting for confirmation"
        message="Razorpay has not confirmed the mandate yet (a UPI approval can take a moment). We will email you once it is active; you can close this page."
      />
    );
  }

  if (!view.can_authorize) {
    return (
      <PublicMessage
        icon={<Clock className="w-6 h-6" />}
        title={view.status === 'created' ? 'AutoPay is unavailable right now' : `This AutoPay request is ${view.status}`}
        message={`Please contact ${view.organization_name} for a new AutoPay link.`}
      />
    );
  }

  return (
    <PublicShell width="md">
      <div className="flex justify-center mb-6">
        <RoomanLogo variant="brand" size="lg" showBillingBadge />
      </div>
      <PublicCard className="overflow-hidden">
        <div className="px-6 py-5 border-b border-slate-100 bg-brand-50/40">
          <p className="text-[11px] font-bold uppercase tracking-wider text-brand-700">UPI AutoPay / e-mandate</p>
          <h1 className="mt-1 text-lg font-bold text-slate-900 tracking-tight">{view.organization_name}</h1>
          {view.prefill.name && <p className="text-xs text-slate-500 mt-0.5">For {view.prefill.name}</p>}
        </div>
        <div className="px-6 py-6">
          <div className="rounded-xl border border-slate-200 divide-y divide-slate-100 text-sm">
            <div className="flex items-start justify-between gap-4 px-4 py-3">
              <span className="text-slate-600">
                {view.plan_name} <span className="text-slate-400">({view.subscription_number})</span>
              </span>
              <span className="font-semibold text-slate-900 whitespace-nowrap">{amount}</span>
            </div>
            <div className="flex items-center justify-between px-4 py-3 bg-slate-50/70">
              <span className="text-slate-600">Collected automatically</span>
              <span className="font-semibold text-slate-900">{cycle}</span>
            </div>
            {view.start_at && (
              <div className="flex items-center justify-between px-4 py-3">
                <span className="text-slate-600">First automatic payment</span>
                <span className="font-semibold text-slate-900">{formatDate(view.start_at)}</span>
              </div>
            )}
          </div>
          <p className="mt-4 text-xs text-slate-500">
            You approve a mandate once in your UPI app or bank. A small authorisation amount may be taken now and
            refunded. You are notified before each debit and can cancel the mandate from your UPI app at any time.
          </p>
          {error && (
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
          <Button
            className="mt-5 w-full"
            size="lg"
            isLoading={busy}
            onClick={() => void authorize()}
            leadingIcon={<Repeat className="w-4 h-4" />}
          >
            Set up AutoPay
          </Button>
          <div className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
            <Lock className="w-3 h-3" />
            Secured by Razorpay
          </div>
        </div>
      </PublicCard>
    </PublicShell>
  );
}
