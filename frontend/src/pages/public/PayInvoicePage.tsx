import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CreditCard,
  Download,
  FileQuestion,
  Lock,
  Mail,
  Phone,
} from 'lucide-react';
import { Button } from '../../components/common/Button';
import { ErrorState } from '../../components/common/ErrorState';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common/Toast';
import { publicService } from '../../services/publicService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import type { ApiError, IntegrationsMeta, InvoiceStatus, RazorpayVerifyResponse } from '../../types/api';
import type { PublicInvoiceFull } from '../../types/public';
import { formatDate, formatDateTime, formatMoney, formatPercent, humanize, parseMoney, toMoneyString } from '../../utils/format';
import { PublicCard, PublicLoading, PublicMessage, PublicShell } from './PublicShell';
import {
  AddressBlock,
  ContactLink,
  InfoPanel,
  LineItemsTable,
  MetaGrid,
  NotesBlock,
  OrgHeader,
  TotalsBlock,
  joinAddress,
  type MetaItem,
  type TotalRow,
} from './DocumentParts';

// ---------------------------------------------------------------------------
// Razorpay Checkout.js loader (idempotent — guards against double injection)
// ---------------------------------------------------------------------------

const RAZORPAY_SCRIPT_SRC = 'https://checkout.razorpay.com/v1/checkout.js';
let razorpayScriptPromise: Promise<RazorpayCheckoutConstructor> | null = null;

function loadRazorpayCheckout(): Promise<RazorpayCheckoutConstructor> {
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

// ---------------------------------------------------------------------------

const OPEN_STATUSES: InvoiceStatus[] = ['sent', 'partially_paid', 'overdue'];

function isNotFound(err: ApiError): boolean {
  return err.status === 404 || err.code === 'ENTITY_NOT_FOUND';
}

export function PayInvoicePage() {
  const { token = '' } = useParams<{ token: string }>();
  const { showToast } = useToast();

  const [invoice, setInvoice] = useState<PublicInvoiceFull | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationsMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const [paying, setPaying] = useState(false);
  const [gatewayDown, setGatewayDown] = useState(false);
  const [payPartial, setPayPartial] = useState(false);
  const [partialAmount, setPartialAmount] = useState('');
  const [amountError, setAmountError] = useState<string | undefined>(undefined);
  const [lastPayment, setLastPayment] = useState<RazorpayVerifyResponse | null>(null);

  const load = useCallback(
    async (opts: { silent?: boolean } = {}) => {
      if (!opts.silent) {
        setLoading(true);
        setError(null);
      }
      try {
        const [inv, meta] = await Promise.all([
          publicService.getInvoice(token) as Promise<PublicInvoiceFull>,
          publicService.integrations().catch(() => null),
        ]);
        setInvoice(inv);
        setIntegrations(meta);
      } catch (err: any) {
        setError(toApiError(err));
      } finally {
        setLoading(false);
      }
    },
    [token]
  );

  useEffect(() => {
    void load();
  }, [load]);

  const razorpayEnabled = useMemo(() => {
    if (gatewayDown) return false;
    return Boolean(invoice?.razorpay.enabled || integrations?.razorpay.enabled);
  }, [invoice, integrations, gatewayDown]);

  const currency = invoice?.currency ?? 'INR';
  const amountDue = parseMoney(invoice?.amount_due);
  const isOpen = invoice ? OPEN_STATUSES.includes(invoice.status) : false;

  const payAmountLabel = useMemo(() => {
    if (!invoice) return '';
    if (payPartial) {
      const n = parseMoney(partialAmount);
      if (!Number.isNaN(n) && n > 0) return formatMoney(toMoneyString(n), currency);
    }
    return formatMoney(invoice.amount_due, currency);
  }, [invoice, payPartial, partialAmount, currency]);

  const finalisePayment = useCallback(
    async (resp: RazorpayCheckoutSuccess) => {
      try {
        const result = await publicService.verifyRazorpayPayment(token, {
          razorpay_order_id: resp.razorpay_order_id,
          razorpay_payment_id: resp.razorpay_payment_id,
          razorpay_signature: resp.razorpay_signature,
        });
        setLastPayment(result);
        setPayPartial(false);
        setPartialAmount('');
        showToast(
          'success',
          'Payment received',
          result.invoice_status === 'paid'
            ? `Receipt ${result.payment_number}. This invoice is now fully paid.`
            : `Receipt ${result.payment_number}. Remaining balance ${formatMoney(result.amount_due, currency)}.`
        );
      } catch (err: any) {
        showToast(
          'error',
          'Payment verification failed',
          `${toApiError(err).message} If money was debited it will be reconciled automatically — please do not pay again.`
        );
      } finally {
        await load({ silent: true });
        setPaying(false);
      }
    },
    [token, currency, load, showToast]
  );

  const handlePay = async () => {
    if (!invoice) return;
    let amount: string | undefined;
    if (payPartial) {
      const n = parseMoney(partialAmount);
      if (Number.isNaN(n) || n <= 0) {
        setAmountError('Enter an amount greater than zero.');
        return;
      }
      if (n > amountDue + 1e-9) {
        setAmountError(`Cannot exceed the amount due (${formatMoney(invoice.amount_due, currency)}).`);
        return;
      }
      amount = toMoneyString(n);
    }
    setAmountError(undefined);
    setPaying(true);
    try {
      const Razorpay = await loadRazorpayCheckout();
      const order = await publicService.createRazorpayOrder(token, amount);
      const isMobileDevice =
        typeof window !== 'undefined' &&
        (/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
          window.innerWidth < 768);

      const checkout = new Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: invoice.organization.legal_name || invoice.organization.name,
        description: `Invoice ${invoice.invoice_number}`,
        image: invoice.organization.logo_url ?? undefined,
        order_id: order.order_id,
        prefill: {
          name: order.prefill.name ?? undefined,
          email: order.prefill.email ?? undefined,
          contact: order.prefill.contact ?? undefined,
        },
        notes: { invoice_number: invoice.invoice_number, payment_id: order.payment_id },
        theme: { color: '#2563eb' },
        config: {
          display: {
            blocks: {
              upi: {
                name: 'Pay via UPI',
                instruments: [
                  {
                    method: 'upi',
                    flows: isMobileDevice ? ['intent'] : ['qr'],
                  },
                ],
              },
              other: {
                name: 'Cards, Netbanking & Wallets',
                instruments: [
                  { method: 'card' },
                  { method: 'netbanking' },
                  { method: 'wallet' },
                ],
              },
            },
            sequence: ['block.upi', 'block.other'],
            preferences: {
              show_default_blocks: true,
            },
          },
        },
        handler: (resp) => {
          void finalisePayment(resp);
        },
        modal: {
          ondismiss: () => {
            setPaying(false);
            showToast('info', 'Payment cancelled', 'Nothing was charged. You can try again whenever you are ready.');
          },
        },
      });
      checkout.on('payment.failed', (event) => {
        setPaying(false);
        showToast(
          'error',
          'Payment failed',
          event.error?.description || 'Your bank or card declined the payment. Please try again.'
        );
      });
      checkout.open();
    } catch (err: any) {
      setPaying(false);
      const apiErr = toApiError(err);
      const fields = fieldErrors(err);
      if (fields.amount) setAmountError(apiErr.message);
      if (apiErr.code === 'GATEWAY_NOT_CONFIGURED') setGatewayDown(true);
      if (apiErr.code === 'INVALID_STATE') void load({ silent: true });
      showToast('error', 'Could not start payment', apiErr.message);
    }
  };

  // ---------------------------------------------------------------- states

  if (loading) return <PublicLoading message="Loading your invoice…" />;

  if (error) {
    if (isNotFound(error)) {
      return (
        <PublicMessage
          icon={<FileQuestion className="w-6 h-6" />}
          title="This payment link isn't valid"
          message="The link may have been mistyped, or the invoice it pointed to is no longer available. Please contact the sender for an up-to-date link."
          action={
            <Button variant="outline" size="sm" onClick={() => void load()}>
              Try again
            </Button>
          }
        />
      );
    }
    return (
      <PublicShell width="md">
        <ErrorState title="Couldn't load this invoice" message={error.message} onRetry={() => void load()} />
      </PublicShell>
    );
  }

  if (!invoice) return null;

  const org = invoice.organization;
  const cust = invoice.customer;
  const succeededPayments = invoice.payments.filter((p) => p.status === 'succeeded');
  const paidDates = succeededPayments
    .map((p) => p.paid_at)
    .filter((d): d is string => Boolean(d))
    .sort();
  const lastPaidAt = paidDates.length > 0 ? paidDates[paidDates.length - 1] : undefined;

  const meta: MetaItem[] = [
    { label: 'Issue date', value: formatDate(invoice.issue_date) },
    {
      label: 'Due date',
      value:
        invoice.days_overdue > 0 && isOpen
          ? `${formatDate(invoice.due_date)} · ${invoice.days_overdue}d overdue`
          : formatDate(invoice.due_date),
      tone: invoice.days_overdue > 0 && isOpen ? 'danger' : 'default',
    },
    { label: 'Billed to', value: cust.display_name },
    invoice.period_start && invoice.period_end
      ? { label: 'Billing period', value: `${formatDate(invoice.period_start)} – ${formatDate(invoice.period_end)}` }
      : { label: 'Currency', value: invoice.currency },
  ];

  const discount = parseMoney(invoice.discount_amount);
  const paid = parseMoney(invoice.amount_paid);
  const totals: TotalRow[] = [
    { label: 'Subtotal', value: formatMoney(invoice.subtotal, currency) },
    ...(discount > 0
      ? [
          {
            label: `Discount (${formatPercent(invoice.discount_pct)})`,
            value: `− ${formatMoney(invoice.discount_amount, currency)}`,
            kind: 'muted' as const,
          },
        ]
      : []),
    // GST heads, so the customer's on-screen copy matches the tax invoice PDF.
    ...(Number(invoice.cgst_amount || 0) > 0 || Number(invoice.sgst_amount || 0) > 0
      ? [
          { label: 'CGST', value: formatMoney(invoice.cgst_amount, currency) },
          { label: 'SGST/UTGST', value: formatMoney(invoice.sgst_amount, currency) },
        ]
      : Number(invoice.igst_amount || 0) > 0
        ? [{ label: 'IGST', value: formatMoney(invoice.igst_amount, currency) }]
        : [{ label: 'Tax', value: formatMoney(invoice.tax_amount, currency) }]),
    { label: 'Total', value: formatMoney(invoice.total, currency), kind: 'total' },
    ...(paid > 0
      ? [{ label: 'Amount paid', value: `− ${formatMoney(invoice.amount_paid, currency)}`, kind: 'paid' as const }]
      : []),
    { label: 'Amount due', value: formatMoney(invoice.amount_due, currency), kind: 'due' },
  ];

  const pdfLink = (
    <a
      href={publicService.invoicePdfUrl(token)}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center justify-center gap-1.5 h-8 px-2.5 text-xs font-medium rounded-lg border border-slate-300 text-slate-700 bg-white hover:bg-slate-50 hover:text-slate-900 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
    >
      <Download className="w-3.5 h-3.5" />
      Download PDF
    </a>
  );

  return (
    <PublicShell>
      <PublicCard className="px-5 py-6 sm:px-8 sm:py-8 space-y-8">
        <OrgHeader
          orgName={org.name}
          legalName={org.legal_name}
          logoUrl={org.logo_url}
          docLabel="Invoice"
          docNumber={invoice.invoice_number}
          status={invoice.status}
          actions={pdfLink}
        />

        {/* Status / payment panel */}
        {invoice.status === 'paid' && (
          <InfoPanel
            tone="success"
            icon={<CheckCircle2 className="w-5 h-5" />}
            title={lastPayment ? 'Payment successful — thank you!' : 'This invoice is fully paid'}
          >
            {lastPayment && <p>Receipt {lastPayment.payment_number} has been recorded against this invoice.</p>}
            {lastPaidAt && <p>Last payment received on {formatDateTime(lastPaidAt)}.</p>}
            <p>No further payment is due. You can download the PDF for your records.</p>
          </InfoPanel>
        )}

        {invoice.status === 'void' && (
          <InfoPanel tone="neutral" icon={<Ban className="w-5 h-5" />} title="This invoice has been voided">
            <p>
              {org.name} cancelled this invoice, so no payment is due. If you believe this is a mistake, please
              contact them directly.
            </p>
          </InfoPanel>
        )}

        {isOpen && (
          <div className="rounded-xl border border-blue-200 bg-blue-50/60 p-5 sm:p-6">
            {lastPayment && invoice.status === 'partially_paid' && (
              <InfoPanel
                tone="success"
                icon={<CheckCircle2 className="w-5 h-5" />}
                title="Part payment received — thank you!"
                className="mb-5 bg-white"
              >
                <p>
                  Receipt {lastPayment.payment_number} recorded. The remaining balance is shown below.
                </p>
              </InfoPanel>
            )}
            <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-brand-700">Amount due</p>
                <p className="mt-1 text-3xl font-bold text-slate-900 tabular-nums tracking-tight">
                  {formatMoney(invoice.amount_due, currency)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Due {formatDate(invoice.due_date)}
                  {invoice.days_overdue > 0 && (
                    <span className="text-rose-700 font-medium"> · {invoice.days_overdue} days overdue</span>
                  )}
                  {paid > 0 && <> · {formatMoney(invoice.amount_paid, currency)} already paid</>}
                </p>
              </div>

              {razorpayEnabled ? (
                <div className="w-full sm:w-72 space-y-3">
                  {payPartial && (
                    <Input
                      label="Amount to pay"
                      type="number"
                      inputMode="decimal"
                      min="0.01"
                      step="0.01"
                      max={invoice.amount_due}
                      value={partialAmount}
                      onChange={(e) => {
                        setPartialAmount(e.target.value);
                        setAmountError(undefined);
                      }}
                      error={amountError}
                      helperText={`Any amount up to ${formatMoney(invoice.amount_due, currency)}`}
                      disabled={paying}
                    />
                  )}
                  <Button
                    size="lg"
                    className="w-full"
                    isLoading={paying}
                    onClick={() => void handlePay()}
                    leadingIcon={<CreditCard className="w-4 h-4" />}
                  >
                    Pay {payAmountLabel} now
                  </Button>
                  <div className="flex items-center justify-between gap-2">
                    <button
                      type="button"
                      className="text-xs font-medium text-brand-700 hover:text-brand-800 hover:underline"
                      disabled={paying}
                      onClick={() => {
                        setPayPartial((v) => !v);
                        setPartialAmount('');
                        setAmountError(undefined);
                      }}
                    >
                      {payPartial ? 'Pay the full amount instead' : 'Pay a different amount'}
                    </button>
                    <span className="flex items-center gap-1 text-[11px] text-slate-500">
                      <Lock className="w-3 h-3" /> Secured by Razorpay
                    </span>
                  </div>
                </div>
              ) : (
                <div className="w-full sm:max-w-sm rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <p className="flex items-center gap-2 text-sm font-semibold text-amber-900">
                    <AlertTriangle className="w-4 h-4 shrink-0" /> Online payment unavailable
                  </p>
                  <p className="mt-1 text-xs text-amber-800 leading-relaxed">
                    {org.name} has not enabled card/UPI payments for this invoice. Please contact them to arrange a
                    bank transfer or other payment, quoting invoice{' '}
                    <span className="font-semibold tabular-nums">{invoice.invoice_number}</span>.
                  </p>
                  {(org.email || org.phone) ? (
                    <div className="mt-2.5 space-y-1">
                      {org.email && (
                        <ContactLink
                          icon={<Mail className="w-3 h-3" />}
                          href={`mailto:${org.email}?subject=${encodeURIComponent(`Payment for ${invoice.invoice_number}`)}`}
                          label={org.email}
                        />
                      )}
                      {org.phone && (
                        <ContactLink
                          icon={<Phone className="w-3 h-3" />}
                          href={`tel:${org.phone.replace(/\s+/g, '')}`}
                          label={org.phone}
                        />
                      )}
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-amber-800">
                      Reply to the email this invoice arrived with to get payment instructions.
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        <MetaGrid items={meta} />

        <div className="grid gap-6 sm:grid-cols-2">
          <AddressBlock
            heading="From"
            name={org.name}
            subName={org.legal_name}
            lines={joinAddress(
              org.address_line1,
              org.address_line2,
              joinAddress(org.city, org.state, org.postal_code).join(', '),
              org.country
            )}
            email={org.email}
            phone={org.phone}
            website={org.website}
            meta={[
              { label: 'GSTIN', value: org.gstin },
              { label: 'PAN', value: org.pan },
            ]}
          />
          <AddressBlock
            heading="Bill to"
            name={cust.display_name}
            subName={cust.company_name}
            lines={joinAddress(
              cust.billing_address_line1,
              cust.billing_address_line2,
              joinAddress(cust.billing_city, cust.billing_state, cust.billing_postal_code).join(', '),
              cust.billing_country
            )}
            email={cust.email}
            phone={cust.phone}
            meta={[{ label: 'GSTIN', value: cust.gstin }]}
          />
        </div>

        <LineItemsTable items={invoice.items} currency={currency} />

        <TotalsBlock rows={totals} />

        {succeededPayments.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">Payments received</p>
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
              {succeededPayments.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-4 px-4 py-2.5 text-sm">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-900 tabular-nums">{p.payment_number}</p>
                    <p className="text-xs text-slate-500">
                      {humanize(p.method)}
                      {p.paid_at && <> · {formatDateTime(p.paid_at)}</>}
                    </p>
                  </div>
                  <p className="font-medium text-emerald-700 tabular-nums shrink-0">
                    {formatMoney(p.amount, currency)}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}

        <NotesBlock notes={invoice.notes} terms={invoice.terms} />
      </PublicCard>
    </PublicShell>
  );
}

export default PayInvoicePage;
