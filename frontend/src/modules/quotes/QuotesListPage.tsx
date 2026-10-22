import { Fragment, useState, useEffect, useMemo, useCallback, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Plus,
  Search,
  RefreshCw,
  Eye,
  Edit2,
  Send,
  CheckSquare,
  Receipt,
  Trash2,
} from 'lucide-react';
import { Button } from '../../components/common/Button';
import { LoadingState } from '../../components/common/LoadingState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { ErrorState } from '../../components/common/ErrorState';
import { Pagination } from '../../components/common/Pagination';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';
import { loadPreferences } from '../../pages/settings/PreferencesTab';
import { quoteService } from '../../services/quoteService';
import { dashboardSummaryService, formatPerCurrency } from '../../services/dashboardSummaryService';
import type { QuoteValueByCurrency } from '../../services/dashboardSummaryService';
import { formatMoney } from '../../utils/format';
import type { Quote, QuoteStatus } from '../../types/quotes';
import { usePageSpec } from '../../appUi/usePageSpec';
import type { EditableProps } from '../../appUi/UiConfigContext';
import type { ResolvedItem } from '../../appUi/registry';

const PAGE_SIZE = 20;

/** Tab id -> backend `status` filter value. Converting a quote sets it to `converted`. */
const TAB_STATUS: Record<string, string | undefined> = {
  all: undefined,
  invoiced: 'converted',
};

interface QuoteCounts {
  total: number;
  draft: number;
  pendingApproval: number;
  sent: number;
  accepted: number;
}

const EMPTY_COUNTS: QuoteCounts = { total: 0, draft: 0, pendingApproval: 0, sent: 0, accepted: 0 };

export function QuotesListPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canEdit = hasRole('finance');
  const canApprove = hasRole('admin');
  const ui = usePageSpec('quotes');

  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [totalQuotes, setTotalQuotes] = useState(0);
  const [counts, setCounts] = useState<QuoteCounts>(EMPTY_COUNTS);
  const [valueByCurrency, setValueByCurrency] = useState<QuoteValueByCurrency[]>([]);
  const [baseCurrency, setBaseCurrency] = useState('INR');
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [dateFilter, setDateFilter] = useState('');
  const [pendingSendQuoteId, setPendingSendQuoteId] = useState<string | null>(null);
  const [pendingDeleteQuoteId, setPendingDeleteQuoteId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Search, status and date filters are applied by the server so every quote is
  // reachable through pagination (not just the first page).
  const fetchQuotes = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const base = {
        search: debouncedSearch || undefined,
        date_from: dateFilter || undefined,
        date_to: dateFilter || undefined,
      };
      const status = activeTab in TAB_STATUS ? TAB_STATUS[activeTab] : activeTab;
      // One server-side summary replaces the per-status count() round trips. 'accepted'
      // groups accepted / partially invoiced / invoiced / converted quotes.
      const [res, summary] = await Promise.all([
        quoteService.listQuotes({ ...base, status, page, page_size: PAGE_SIZE }),
        dashboardSummaryService.quotes(base),
      ]);
      setQuotes(res.items);
      setTotalQuotes(res.total ?? res.items.length);
      setCounts({
        total: summary.total_count,
        draft: summary.groups.draft,
        pendingApproval: summary.groups.pending_approval,
        sent: summary.groups.sent,
        accepted: summary.groups.accepted,
      });
      setValueByCurrency(summary.value_by_currency || []);
      setBaseCurrency(summary.base_currency || 'INR');
    } catch (err) {
      setLoadError(toApiError(err).message);
    } finally {
      setIsLoading(false);
    }
  }, [debouncedSearch, dateFilter, activeTab, page]);

  useEffect(() => {
    void fetchQuotes();
  }, [fetchQuotes]);

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, dateFilter, activeTab]);

  // Dashboard KPIs: counts and value come from the server summary (same search/date
  // filters as the list, all statuses), value reported per currency — never summed across them.
  const kpis = useMemo(() => {
    const totalValue = formatPerCurrency(valueByCurrency, (r) => r.total, (a, c) => formatMoney(a, c), baseCurrency);
    return { ...counts, totalValue };
  }, [counts, valueByCurrency, baseCurrency]);

  const filteredQuotes = quotes;

  const handleSendQuote = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const prefs = loadPreferences();
    if (prefs.confirmBeforeSendInvoice) {
      setPendingSendQuoteId(id);
    } else {
      void executeSendQuote(id);
    }
  };

  const executeSendQuote = async (id: string) => {
    setPendingSendQuoteId(null);
    try {
      setActionLoading(true);
      const sent = await quoteService.sendQuote(id);
      if (sent.status === 'pending_approval') {
        showToast('info', 'Discount approval requested', 'An admin must approve this quote before it is sent.');
      } else if (sent.email_sent === false) {
        showToast('warning', quoteService.EMAIL_NOT_SENT_MESSAGE);
      } else {
        showToast('success', 'Quote sent');
      }
      await fetchQuotes();
    } catch (err) {
      showToast('error', 'Could not send quote', toApiError(err).message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleApproveQuote = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await quoteService.approveQuote(id);
      showToast('success', 'Quote approved', 'Send it to the customer when ready.');
      await fetchQuotes();
    } catch (err) {
      showToast('error', 'Could not approve quote', toApiError(err).message);
    }
  };

  const handleConvertToInvoice = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const inv = await quoteService.convertToInvoice(id);
      if (inv?.id) {
        navigate(`/invoices/${inv.id}`);
      } else {
        await fetchQuotes();
      }
    } catch (err) {
      showToast('error', 'Could not convert quote', toApiError(err).message);
    }
  };

  const handleDeleteQuote = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setPendingDeleteQuoteId(id);
  };

  const executeDeleteQuote = async () => {
    if (!pendingDeleteQuoteId) return;
    try {
      setActionLoading(true);
      await quoteService.deleteQuote(pendingDeleteQuoteId);
      setPendingDeleteQuoteId(null);
      showToast('success', 'Quote deleted');
      await fetchQuotes();
    } catch (err) {
      showToast('error', 'Could not delete quote', toApiError(err).message);
    } finally {
      setActionLoading(false);
    }
  };

  const getStatusBadge = (status: QuoteStatus) => {
    switch (status) {
      case 'draft':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">DRAFT</span>;
      case 'pending_approval':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">PENDING APPROVAL</span>;
      case 'approved':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">APPROVED</span>;
      case 'sent':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">SENT</span>;
      case 'viewed':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-cyan-50 text-cyan-700 border border-cyan-200">VIEWED</span>;
      case 'accepted':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">ACCEPTED</span>;
      case 'converted':
      case 'invoiced':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-teal-50 text-teal-700 border border-teal-200">INVOICED</span>;
      case 'declined':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-red-50 text-red-700 border border-red-200">DECLINED</span>;
      case 'expired':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-500">EXPIRED</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700 uppercase">{status}</span>;
    }
  };

  const columns = ui.shown('columns');
  const quoteCells: Record<string, (quote: Quote) => ReactNode> = {
    quote_number: (quote) => (
      <td className="px-4 py-3">
        <span className="font-bold font-mono text-slate-900">{quote.quote_number}</span>
        {quote.title && <p className="text-[10px] text-slate-400 truncate max-w-xs">{quote.title}</p>}
      </td>
    ),
    customer: (quote) => (
      <td className="px-4 py-3">
        <p className="font-semibold text-slate-900">{quote.customer?.display_name}</p>
        <p className="text-[10px] text-slate-400">{quote.customer?.customer_number}</p>
      </td>
    ),
    issue_date: (quote) => (
      <td className="px-4 py-3">{quote.issue_date}</td>
    ),
    expiry_date: (quote) => (
      <td className="px-4 py-3">{quote.expiry_date || '—'}</td>
    ),
    amount: (quote) => (
      <td className="px-4 py-3 font-semibold text-slate-900">
        {formatMoney(Number(quote.total), quote.currency)}
        {Number(quote.discount_pct) > 0 && (
          <span className="text-[10px] text-amber-600 block">({quote.discount_pct}% off)</span>
        )}
      </td>
    ),
    status: (quote) => (
      <td className="px-4 py-3">{getStatusBadge(quote.status)}</td>
    ),
    actions: (quote) => (
      <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-end gap-1.5">
          <Link to={`/quotes/${quote.id}`}>
            <button className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100" title="View Quote">
              <Eye className="w-3.5 h-3.5" />
            </button>
          </Link>

          {canEdit && (quote.status === 'draft' || quote.status === 'pending_approval') && (
            <Link to={`/quotes/${quote.id}/edit`}>
              <button className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100" title="Edit Quote">
                <Edit2 className="w-3.5 h-3.5" />
              </button>
            </Link>
          )}

          {canApprove && quote.status === 'pending_approval' && (
            <button
              onClick={(e) => handleApproveQuote(quote.id, e)}
              className="p-1 rounded text-amber-600 hover:bg-amber-50"
              title="Approve discount & send quote"
            >
              <CheckSquare className="w-3.5 h-3.5" />
            </button>
          )}

          {canEdit && (quote.status === 'draft' || quote.status === 'approved') && (
            <button
              onClick={(e) => handleSendQuote(quote.id, e)}
              className="p-1 rounded text-indigo-600 hover:bg-indigo-50"
              title="Send to Customer"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          )}

          {canEdit && quote.status === 'accepted' && (
            <button
              onClick={(e) => handleConvertToInvoice(quote.id, e)}
              className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-600 text-white hover:bg-emerald-700 flex items-center gap-1"
              title="Convert to Live Invoice"
            >
              <Receipt className="w-3 h-3" />
              Invoice
            </button>
          )}

          {canEdit && quote.status === 'draft' && (
            <button
              onClick={(e) => handleDeleteQuote(quote.id, e)}
              className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50"
              title="Delete Quote"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </td>
    ),
  };
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 animate-in fade-in duration-150">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div {...ui.edit('header')}>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900">{ui.text('header', 'title')}</h1>
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
              {ui.text('header', 'badge')}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            {ui.text('header', 'subtitle')}
          </p>
        </div>

        {canEdit && (
          <div className="flex items-center gap-2">
            <Link to="/quotes/new">
              <Button variant="primary" size="sm" leadingIcon={<Plus className="w-4 h-4" />}>
                New Quote
              </Button>
            </Link>
          </div>
        )}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3" {...ui.edit('kpis')}>
        {ui.render('kpis', {
          total: (item, edit) => <QuoteKpi {...edit} item={item} value={kpis.total} tone="text-slate-900" />,
          draft: (item, edit) => <QuoteKpi {...edit} item={item} value={kpis.draft} tone="text-slate-700" />,
          pending_approval: (item, edit) => <QuoteKpi {...edit} item={item} value={kpis.pendingApproval} tone="text-amber-600" />,
          sent: (item, edit) => <QuoteKpi {...edit} item={item} value={kpis.sent} tone="text-indigo-600" />,
          accepted: (item, edit) => <QuoteKpi {...edit} item={item} value={kpis.accepted} tone="text-emerald-600" />,
          total_value: (item, edit) => <QuoteKpi {...edit} item={item} value={kpis.totalValue} tone="text-slate-900" />,
        })}
      </div>

      {/* Tabs & Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs space-y-3">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          {/* Tabs */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl text-xs font-semibold text-slate-600 overflow-x-auto" {...ui.edit('tabs')}>
            {ui.shown('tabs').map((item) => ({ id: item.key, label: item.label })).map((tab) => (
              <button
                key={tab.id}
                {...ui.edit(`tabs.${tab.id}`)}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 py-1.5 rounded-lg capitalize whitespace-nowrap transition-all ${
                  activeTab === tab.id ? 'bg-white text-slate-900 shadow-2xs font-bold' : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Search & Refresh */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search quote #, customer, email..."
                className="pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-slate-50/50 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800 w-64"
              />
            </div>

            <input
              type="date"
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              className="px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 bg-slate-50/50 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800 text-slate-600"
              title="Filter by issue date"
            />

            <Button
              variant="outline"
              size="sm"
              onClick={() => void fetchQuotes()}
              title="Refresh"
              leadingIcon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
        {loadError ? (
          <ErrorState
            title="Couldn't load quotes"
            message={loadError}
            onRetry={() => void fetchQuotes()}
            className="rounded-none border-0"
          />
        ) : isLoading ? (
          <div className="py-16">
            <LoadingState message="Loading quotes and proposals..." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600 border-collapse">
            <thead className="bg-slate-50 border-b border-slate-200/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <tr {...ui.edit('columns')}>
                {columns.map((col) => (
                  <th key={col.key} className={`px-4 py-3${col.key === 'actions' ? ' text-right' : ''}`} {...ui.edit(`columns.${col.key}`)}>
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredQuotes.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} className="px-4 py-12 text-center text-slate-400 italic" {...ui.edit('empty')}>
                    {debouncedSearch || dateFilter || activeTab !== 'all'
                      ? ui.text('empty', 'filtered')
                      : canEdit
                        ? ui.text('empty', 'none')
                        : ui.text('empty', 'none_read_only')}
                  </td>
                </tr>
              ) : (
                filteredQuotes.map((quote) => (
                  <tr
                    key={quote.id}
                    onClick={() => navigate(`/quotes/${quote.id}`)}
                    className="hover:bg-slate-50/80 transition-colors cursor-pointer"
                  >
                    {columns.map((col) => <Fragment key={col.key}>{quoteCells[col.key]?.(quote)}</Fragment>)}
                  </tr>
                ))
              )}
            </tbody>
          </table>
          </div>
        )}
        {!loadError && !isLoading && (
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={totalQuotes}
            onPageChange={setPage}
            itemLabel="quotes"
          />
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={Boolean(pendingDeleteQuoteId)}
        onClose={() => setPendingDeleteQuoteId(null)}
        onConfirm={() => void executeDeleteQuote()}
        title="Delete draft quote"
        description="Are you sure you want to delete this draft quote? This cannot be undone."
        confirmLabel="Delete"
        variant="danger"
        isLoading={actionLoading}
      />

      {/* Send Confirmation Dialog */}
      <ConfirmDialog
        isOpen={Boolean(pendingSendQuoteId)}
        onClose={() => setPendingSendQuoteId(null)}
        onConfirm={() => {
          if (pendingSendQuoteId) void executeSendQuote(pendingSendQuoteId);
        }}
        title="Send Quote"
        description="Are you sure you want to send this quote to the customer? This will dispatch an email with the public quote link."
        confirmLabel="Send Quote"
        isLoading={actionLoading}
      />
    </div>
  );
}

export default QuotesListPage;

function QuoteKpi({ item, value, tone, ...edit }: { item: ResolvedItem; value: ReactNode; tone: string } & EditableProps) {
  return (
    <div className="bg-white p-3.5 rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
      <p className={`text-xl font-bold mt-1 ${tone}`}>{value}</p>
      <p className="text-[10px] text-slate-400 mt-0.5">{item.caption}</p>
    </div>
  );
}
