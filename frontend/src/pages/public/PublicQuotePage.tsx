import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  CheckCircle2,
  Clock,
  FileCheck2,
  FileQuestion,
  Hourglass,
  Mail,
  Phone,
  ThumbsDown,
  XCircle,
} from 'lucide-react';
import { Button } from '../../components/common/Button';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { ErrorState } from '../../components/common/ErrorState';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common/Toast';
import { publicService } from '../../services/publicService';
import { fieldErrors, toApiError } from '../../services/apiClient';
import type { ApiError } from '../../types/api';
import type { PublicQuoteFull } from '../../types/public';
import { formatDate, formatDateTime, formatMoney, formatPercent, parseMoney, todayIso } from '../../utils/format';
import { PublicCard, PublicLoading, PublicMessage, PublicShell } from './PublicShell';
import { isQuoteOpenForCustomer } from './quoteStatus';
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

const DECLINE_REASON_MAX = 500;

function isNotFound(err: ApiError): boolean {
  return err.status === 404 || err.code === 'ENTITY_NOT_FOUND';
}

export function PublicQuotePage() {
  const { token = '' } = useParams<{ token: string }>();
  const { showToast } = useToast();

  const [quote, setQuote] = useState<PublicQuoteFull | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const [acceptName, setAcceptName] = useState('');
  const [nameError, setNameError] = useState<string | undefined>(undefined);
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [declineOpen, setDeclineOpen] = useState(false);
  const [declineReason, setDeclineReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  /** Set right after the visitor acts, so the result panel can thank them by name. */
  const [justActed, setJustActed] = useState<'accepted' | 'declined' | null>(null);

  const load = useCallback(
    async (opts: { silent?: boolean } = {}) => {
      if (!opts.silent) {
        setLoading(true);
        setError(null);
      }
      try {
        const q = (await publicService.getQuote(token)) as PublicQuoteFull;
        setQuote(q);
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

  const openAccept = () => {
    const name = acceptName.trim();
    if (!name) {
      setNameError('Please enter your full name to accept this quote.');
      return;
    }
    setNameError(undefined);
    setAcceptOpen(true);
  };

  const confirmAccept = async () => {
    if (!quote) return;
    const name = acceptName.trim();
    setSubmitting(true);
    try {
      await publicService.acceptQuote(token, name);
      setJustActed('accepted');
      setAcceptOpen(false);
      showToast('success', 'Quote accepted', `Thank you, ${name}. ${quote.organization.name} has been notified.`);
      await load({ silent: true });
    } catch (err: any) {
      const apiErr = toApiError(err);
      const fields = fieldErrors(err);
      if (fields.accepted_by_name) setNameError(fields.accepted_by_name);
      setAcceptOpen(false);
      showToast('error', 'Could not accept quote', apiErr.message);
      if (apiErr.code === 'INVALID_STATE') await load({ silent: true });
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDecline = async () => {
    if (!quote) return;
    const reason = declineReason.trim();
    setSubmitting(true);
    try {
      await publicService.declineQuote(token, reason ? reason : undefined);
      setJustActed('declined');
      setDeclineOpen(false);
      showToast('success', 'Quote declined', `${quote.organization.name} has been notified of your decision.`);
      await load({ silent: true });
    } catch (err: any) {
      const apiErr = toApiError(err);
      setDeclineOpen(false);
      showToast('error', 'Could not decline quote', apiErr.message);
      if (apiErr.code === 'INVALID_STATE') await load({ silent: true });
    } finally {
      setSubmitting(false);
    }
  };

  // ---------------------------------------------------------------- states

  if (loading) return <PublicLoading message="Loading your quote…" />;

  if (error) {
    if (isNotFound(error)) {
      return (
        <PublicMessage
          icon={<FileQuestion className="w-6 h-6" />}
          title="This quote link isn't valid"
          message="The link may have been mistyped, or the quote it pointed to is no longer available. Please contact the sender for an up-to-date link."
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
        <ErrorState title="Couldn't load this quote" message={error.message} onRetry={() => void load()} />
      </PublicShell>
    );
  }

  if (!quote) return null;

  const org = quote.organization;
  const cust = quote.customer;
  const currency = quote.currency;
  const expiredByDate = Boolean(quote.expiry_date && quote.expiry_date < todayIso());
  // Opening this link moves a sent quote to "viewed"; both are open for the customer's answer
  // (backend OPEN_FOR_CUSTOMER_STATUSES). Treating only "sent" as open meant every customer saw
  // "This quote isn't ready yet" with no Accept / Decline buttons.
  const openForCustomer = isQuoteOpenForCustomer(quote.status);
  // The backend flips sent -> expired on read, but guard client-side too.
  // A suspended merchant's quote stays viewable but cannot be accepted or declined (backend 403).
  const merchantUnavailable = quote.actions_unavailable_reason ?? null;
  const actionable = openForCustomer && !expiredByDate && !merchantUnavailable;

  const meta: MetaItem[] = [
    { label: 'Issue date', value: formatDate(quote.issue_date) },
    {
      label: 'Valid until',
      value: quote.expiry_date ? formatDate(quote.expiry_date) : 'No expiry',
      tone: quote.expiry_date && expiredByDate && quote.status !== 'accepted' && quote.status !== 'converted' ? 'danger' : 'default',
    },
    { label: 'Prepared for', value: cust.display_name },
    { label: 'Currency', value: currency },
  ];

  const discount = parseMoney(quote.discount_amount);
  const totals: TotalRow[] = [
    { label: 'Subtotal', value: formatMoney(quote.subtotal, currency) },
    ...(discount > 0
      ? [
          {
            label: `Discount (${formatPercent(quote.discount_pct)})`,
            value: `− ${formatMoney(quote.discount_amount, currency)}`,
            kind: 'muted' as const,
          },
        ]
      : []),
    { label: 'Tax', value: formatMoney(quote.tax_amount, currency) },
    { label: 'Total', value: formatMoney(quote.total, currency), kind: 'due' },
  ];

  const contactLinks =
    org.email || org.phone ? (
      <div className="mt-2 space-y-1">
        {org.email && (
          <ContactLink
            icon={<Mail className="w-3 h-3" />}
            href={`mailto:${org.email}?subject=${encodeURIComponent(`Quote ${quote.quote_number}`)}`}
            label={org.email}
          />
        )}
        {org.phone && (
          <ContactLink icon={<Phone className="w-3 h-3" />} href={`tel:${org.phone.replace(/\s+/g, '')}`} label={org.phone} />
        )}
      </div>
    ) : null;

  const renderStatusPanel = () => {
    switch (quote.status) {
      case 'accepted':
        return (
          <InfoPanel
            tone="success"
            icon={<CheckCircle2 className="w-5 h-5" />}
            title={justActed === 'accepted' ? 'Quote accepted — thank you!' : 'This quote has been accepted'}
          >
            {quote.accepted_at && <p>Accepted on {formatDateTime(quote.accepted_at)}.</p>}
            <p>{org.name} will follow up with an invoice and next steps.</p>
            {contactLinks}
          </InfoPanel>
        );
      case 'converted':
      case 'invoiced':
      case 'partially_invoiced':
        return (
          <InfoPanel tone="success" icon={<FileCheck2 className="w-5 h-5" />} title="Accepted and invoiced">
            {quote.accepted_at && <p>Accepted on {formatDateTime(quote.accepted_at)}.</p>}
            <p>An invoice has been raised for this quote. Check your email for the payment link.</p>
            {contactLinks}
          </InfoPanel>
        );
      case 'declined':
        return (
          <InfoPanel
            tone="neutral"
            icon={<XCircle className="w-5 h-5" />}
            title={justActed === 'declined' ? 'Quote declined' : 'This quote was declined'}
          >
            {quote.declined_at && <p>Declined on {formatDateTime(quote.declined_at)}.</p>}
            <p>If you change your mind, contact {org.name} and they can issue a fresh quote.</p>
            {contactLinks}
          </InfoPanel>
        );
      case 'expired':
        return (
          <InfoPanel tone="warning" icon={<Hourglass className="w-5 h-5" />} title="This quote has expired">
            <p>
              It was valid until {formatDate(quote.expiry_date)} and can no longer be accepted online. Contact{' '}
              {org.name} to request an updated quote.
            </p>
            {contactLinks}
          </InfoPanel>
        );
      case 'sent':
      case 'viewed':
        if (merchantUnavailable && !expiredByDate) {
          return (
            <InfoPanel tone="warning" icon={<Clock className="w-5 h-5" />} title="Responses are temporarily unavailable">
              <p>{merchantUnavailable}</p>
              {contactLinks}
            </InfoPanel>
          );
        }
        if (expiredByDate) {
          return (
            <InfoPanel tone="warning" icon={<Hourglass className="w-5 h-5" />} title="This quote has expired">
              <p>
                It was valid until {formatDate(quote.expiry_date)} and can no longer be accepted online. Contact{' '}
                {org.name} to request an updated quote.
              </p>
              {contactLinks}
            </InfoPanel>
          );
        }
        return null;
      default:
        // Only draft / pending_approval / approved land here. The customer link is minted when the
        // quote is sent, so a normally-sent quote never shows this.
        return (
          <InfoPanel tone="info" icon={<Clock className="w-5 h-5" />} title="This quote isn't ready yet">
            <p>{org.name} is still finalising it. You'll be notified when it is ready to review.</p>
          </InfoPanel>
        );
    }
  };

  return (
    <PublicShell>
      <PublicCard className="px-5 py-6 sm:px-8 sm:py-8 space-y-8">
        <OrgHeader
          orgName={org.name}
          legalName={org.legal_name}
          logoUrl={org.logo_url}
          docLabel="Quote"
          docNumber={quote.quote_number}
          status={expiredByDate && openForCustomer ? 'expired' : quote.status}
        />

        {quote.title && (
          <h1 className="text-xl font-bold text-slate-900 tracking-tight -mt-3">{quote.title}</h1>
        )}

        {renderStatusPanel()}

        {actionable && (
          <div className="rounded-xl border border-blue-200 bg-blue-50/60 p-5 sm:p-6">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-brand-700">Quote total</p>
                <p className="mt-1 text-3xl font-bold text-slate-900 tabular-nums tracking-tight">
                  {formatMoney(quote.total, currency)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {quote.expiry_date ? `Valid until ${formatDate(quote.expiry_date)}` : 'No expiry date'}
                  {' · '}includes {formatMoney(quote.tax_amount, currency)} tax
                </p>
              </div>
              <div className="w-full sm:w-80 space-y-3">
                <Input
                  label="Your full name"
                  placeholder="e.g. Priya Sharma"
                  autoComplete="name"
                  value={acceptName}
                  onChange={(e) => {
                    setAcceptName(e.target.value);
                    setNameError(undefined);
                  }}
                  error={nameError}
                  helperText="Recorded with your acceptance."
                  maxLength={200}
                  disabled={submitting}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') openAccept();
                  }}
                />
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setDeclineOpen(true)}
                    disabled={submitting}
                    leadingIcon={<ThumbsDown className="w-4 h-4" />}
                  >
                    Decline
                  </Button>
                  <Button
                    onClick={openAccept}
                    disabled={submitting}
                    leadingIcon={<CheckCircle2 className="w-4 h-4" />}
                    aria-label="Accept quote"
                  >
                    {/* The full label is truncated in the half-width button on phones. */}
                    <span className="sm:hidden">Accept</span>
                    <span className="hidden sm:inline">Accept quote</span>
                  </Button>
                </div>
              </div>
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
            meta={[{ label: 'GSTIN', value: org.gstin }]}
          />
          <AddressBlock
            heading="Prepared for"
            name={cust.display_name}
            subName={cust.company_name}
            lines={joinAddress(
              cust.billing_address_line1,
              cust.billing_address_line2,
              joinAddress(cust.billing_city, cust.billing_state, cust.billing_postal_code).join(', '),
              cust.billing_country
            )}
            email={cust.email}
          />
        </div>

        <LineItemsTable items={quote.items} currency={currency} />

        <TotalsBlock rows={totals} />

        <NotesBlock notes={quote.notes} terms={quote.terms} />

        {quote.sent_at && (
          <p className="text-xs text-slate-400">Sent {formatDateTime(quote.sent_at)}</p>
        )}
      </PublicCard>

      <ConfirmDialog
        isOpen={acceptOpen}
        onClose={() => !submitting && setAcceptOpen(false)}
        onConfirm={confirmAccept}
        title={`Accept quote ${quote.quote_number}?`}
        description={`You are accepting ${formatMoney(quote.total, currency)} (including tax) on behalf of ${cust.display_name} as ${acceptName.trim()}. ${org.name} will be notified and may raise an invoice.`}
        confirmLabel="Yes, accept"
        isLoading={submitting}
      />

      <ConfirmDialog
        isOpen={declineOpen}
        onClose={() => !submitting && setDeclineOpen(false)}
        onConfirm={confirmDecline}
        title={`Decline quote ${quote.quote_number}?`}
        description={`${org.name} will be notified. You can optionally tell them why.`}
        confirmLabel="Decline quote"
        variant="danger"
        isLoading={submitting}
      >
        <div>
          <label htmlFor="decline-reason" className="block text-xs font-semibold text-slate-700 mb-1">
            Reason <span className="font-normal text-slate-400">(optional)</span>
          </label>
          <textarea
            id="decline-reason"
            rows={3}
            value={declineReason}
            maxLength={DECLINE_REASON_MAX}
            onChange={(e) => setDeclineReason(e.target.value)}
            placeholder="e.g. Budget approved for a smaller scope this quarter."
            disabled={submitting}
            className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 disabled:opacity-50"
          />
          <p className="mt-1 text-right text-[11px] text-slate-400 tabular-nums">
            {declineReason.length}/{DECLINE_REASON_MAX}
          </p>
        </div>
      </ConfirmDialog>
    </PublicShell>
  );
}

export default PublicQuotePage;
