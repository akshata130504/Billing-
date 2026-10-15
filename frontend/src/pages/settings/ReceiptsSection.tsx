import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { ErrorState } from '../../components/common/ErrorState';
import { LoadingSpinner } from '../../components/common/LoadingState';
import { Pagination } from '../../components/common/Pagination';
import { downloadAuthenticated } from '../../services/download';
import { platformSubscriptionService, type PaymentReceipt } from '../../services/platformSubscriptionService';
import { toApiError } from '../../services/apiClient';
import { formatDate, formatDateTime } from '../../utils/format';
import { formatInterval, formatPlanPrice } from './subscriptionDisplay';

export const RECEIPTS_QUERY_KEY = 'plan-receipts';

function description(r: PaymentReceipt): string {
  const plan = `${r.plan_name ?? r.plan_code} plan`;
  return r.kind === 'initial' ? `${plan} - purchase` : `${plan} - renewal${r.cycle_number ? ` (cycle ${r.cycle_number})` : ''}`;
}

/**
 * Payment receipts for the organization's Rooman plan (Finance, Admin and Owner; the server enforces it). A receipt
 * confirms a verified payment; it is not a tax invoice. Everything shown is the stored receipt snapshot.
 */
export function ReceiptsSection() {
  const [page, setPage] = useState(1);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const query = useQuery({
    queryKey: [RECEIPTS_QUERY_KEY, page],
    queryFn: () => platformSubscriptionService.listReceipts(page),
  });

  const download = async (r: PaymentReceipt) => {
    setDownloadError(null);
    setDownloading(r.id);
    try {
      await downloadAuthenticated(platformSubscriptionService.receiptPdfUrl(r.id), `${r.receipt_number}.pdf`);
    } catch (err) {
      setDownloadError(toApiError(err).message);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <section aria-labelledby="receipts-heading" className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-2xs">
      <h2 id="receipts-heading" className="text-base font-bold text-slate-900">
        Payment receipts
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Receipts for confirmed payments of your Rooman Billing plan. These are payment receipts, not tax invoices.
      </p>
      {downloadError && <p role="alert" className="mt-2 text-sm text-rose-700">{downloadError}</p>}

      <div className="mt-4">
        {query.isLoading ? (
          <p role="status" className="flex items-center gap-2 text-sm text-slate-500">
            <LoadingSpinner size="sm" /> Loading receipts...
          </p>
        ) : query.isError ? (
          <ErrorState title="Receipts could not be loaded" message={toApiError(query.error).message}
            onRetry={() => void query.refetch()} />
        ) : !query.data || query.data.items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 p-4 text-center text-sm text-slate-600">
            No payment receipts yet. A receipt appears here once a plan payment has been confirmed.
          </p>
        ) : (
          <>
            <ul className="divide-y divide-slate-100">
              {query.data.items.map((r) => (
                <li key={r.id} data-testid="receipt-row" className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900">
                      {r.receipt_number}
                      <Badge variant="success">Paid</Badge>
                      {(r.sandbox || r.mode === 'test') && <Badge variant="warning">Test mode</Badge>}
                    </p>
                    <p className="text-sm text-slate-700">{description(r)}</p>
                    <p className="text-xs text-slate-500">
                      Paid {formatDateTime(r.paid_at)}
                      {(r.period_start || r.period_end) && ` · Period ${formatDate(r.period_start)} – ${formatDate(r.period_end)}`}
                      {` · ${formatInterval(r.billing_interval, r.billing_interval_count)}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold text-slate-900">{formatPlanPrice(r.amount_minor, r.currency)}</span>
                    <Button size="sm" variant="outline" onClick={() => void download(r)} isLoading={downloading === r.id}
                      leadingIcon={<Download className="h-3.5 w-3.5" aria-hidden="true" />}
                      aria-label={`Download receipt ${r.receipt_number}`}>
                      PDF
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
            {query.data.total > query.data.page_size && (
              <Pagination page={query.data.page} pageSize={query.data.page_size} total={query.data.total}
                onPageChange={setPage} itemLabel="receipts" />
            )}
          </>
        )}
      </div>
    </section>
  );
}
