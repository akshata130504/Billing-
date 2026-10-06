import { useState, useEffect, type ReactNode } from 'react';
import {
  INVOICES_COLUMN_DEFS,
  INVOICES_EMPTY_DEFAULTS,
  INVOICES_HEADER_DEFAULTS,
  INVOICES_KPI_DEFS,
  resolveList,
  visible,
} from '../../appUi/registry';
import { usePageUi, useUiEditable } from '../../appUi/UiConfigContext';
import { useNavigate } from 'react-router-dom';
import {
  FileText,
  Plus,
  Search,
  DollarSign,
  Clock,
  CheckCircle,
  AlertCircle,
  Eye,
  RefreshCw,
  AlertTriangle,
} from 'lucide-react';
import { invoiceService } from '../../services/invoiceService';
import type { Invoice, InvoiceStatus, InvoiceKPIs } from '../../types/invoices';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';

export const InvoicesListPage: React.FC = () => {
  const ui = usePageUi('invoices');
  const editable = useUiEditable();
  const { hasRole } = useAuth();
  const canCreate = hasRole('finance');
  const navigate = useNavigate();

  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters and state
  const [activeTab, setActiveTab] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [kpis, setKpis] = useState<InvoiceKPIs>({
    total_invoices: 0,
    draft_count: 0,
    sent_count: 0,
    partially_paid_count: 0,
    paid_count: 0,
    overdue_count: 0,
    total_outstanding: 0,
    total_revenue: 0,
  });

  const fetchInvoices = async () => {
    try {
      setLoading(true);
      setError(null);
      const params: any = {};
      if (activeTab !== 'all') {
        params.status = activeTab.toLowerCase();
      }
      if (searchTerm) {
        params.search = searchTerm;
      }
      const [data, summaryData] = await Promise.all([
        invoiceService.getInvoices(params),
        invoiceService.getSummary(),
      ]);
      setInvoices(data.items);
      if (summaryData) {
        setKpis({
          total_invoices: summaryData.total_invoices ?? 0,
          draft_count: summaryData.draft_count ?? 0,
          sent_count: summaryData.sent_count ?? 0,
          partially_paid_count: summaryData.partially_paid_count ?? 0,
          paid_count: summaryData.paid_count ?? 0,
          overdue_count: summaryData.overdue_count ?? 0,
          void_count: summaryData.void_count ?? 0,
          total_outstanding: Number(summaryData.total_outstanding ?? 0),
          total_revenue: Number(summaryData.total_revenue ?? 0),
        });
      }
    } catch (err) {
      setError(toApiError(err).message || 'Failed to load invoices');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInvoices();
  }, [activeTab]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchInvoices();
  };

  const getStatusBadgeVariant = (status: InvoiceStatus) => {
    const s = String(status).toUpperCase();
    switch (s) {
      case 'DRAFT':
        return 'neutral';
      case 'SENT':
        return 'primary';
      case 'PARTIALLY_PAID':
        return 'info';
      case 'PAID':
        return 'success';
      case 'OVERDUE':
        return 'danger';
      case 'VOID':
        return 'neutral';
      default:
        return 'neutral';
    }
  };

  const tabs = [
    { id: 'all', label: 'All Invoices', count: kpis.total_invoices },
    { id: 'draft', label: 'Draft', count: kpis.draft_count },
    { id: 'sent', label: 'Sent', count: kpis.sent_count },
    { id: 'partially_paid', label: 'Partially Paid', count: kpis.partially_paid_count },
    { id: 'paid', label: 'Paid', count: kpis.paid_count },
    { id: 'overdue', label: 'Overdue', count: kpis.overdue_count },
    { id: 'void', label: 'Void', count: kpis.void_count ?? 0 },
  ];

  const kpiCards: Record<string, { value: ReactNode; valueClass: string; icon: ReactNode; iconClass: string }> = {
    outstanding: {
      value: `₹${Number(kpis.total_outstanding).toLocaleString()}`,
      valueClass: 'text-gray-900',
      icon: <AlertTriangle className="w-6 h-6" />,
      iconClass: 'bg-red-50 text-red-600',
    },
    paid: {
      value: kpis.paid_count,
      valueClass: 'text-gray-900',
      icon: <CheckCircle className="w-6 h-6" />,
      iconClass: 'bg-emerald-50 text-emerald-600',
    },
    overdue: {
      value: kpis.overdue_count,
      valueClass: 'text-red-600',
      icon: <Clock className="w-6 h-6" />,
      iconClass: 'bg-amber-50 text-amber-600',
    },
    revenue: {
      value: `₹${Number(kpis.total_revenue).toLocaleString()}`,
      valueClass: 'text-emerald-600',
      icon: <DollarSign className="w-6 h-6" />,
      iconClass: 'bg-indigo-50 text-indigo-600',
    },
  };

  const columnDefs: Record<string, { align?: 'right'; cellClass: string; render: (inv: Invoice) => ReactNode }> = {
    invoice_number: { cellClass: 'font-semibold text-indigo-600', render: (inv) => inv.invoice_number },
    customer: {
      cellClass: '',
      render: (inv) => (
        <>
          <div className="font-medium text-gray-900">
            {inv.customer?.display_name || inv.customer?.displayName || inv.customer?.name || 'Customer'}
          </div>
          {inv.customer?.email && <div className="text-xs text-gray-500">{inv.customer.email}</div>}
        </>
      ),
    },
    date: { cellClass: 'text-gray-600', render: (inv) => inv.issue_date || inv.invoice_date },
    due_date: { cellClass: 'text-gray-600', render: (inv) => inv.due_date },
    total: {
      align: 'right',
      cellClass: 'text-right font-semibold text-gray-900',
      render: (inv) => `₹${Number(inv.total || inv.total_amount || 0).toLocaleString()}`,
    },
    paid: {
      align: 'right',
      cellClass: 'text-right text-emerald-600 font-medium',
      render: (inv) => `₹${Number(inv.amount_paid || inv.paid_amount || 0).toLocaleString()}`,
    },
    balance: {
      align: 'right',
      cellClass: 'text-right font-bold text-gray-900',
      render: (inv) => `₹${Number(inv.amount_due || inv.balance_due || 0).toLocaleString()}`,
    },
    status: {
      cellClass: '',
      render: (inv) => (
        <Badge variant={getStatusBadgeVariant(inv.status)}>{String(inv.status).replace(/_/g, ' ')}</Badge>
      ),
    },
    actions: {
      align: 'right',
      cellClass: 'text-right',
      render: (inv) => (
        <div className="flex justify-end items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate(`/invoices/${inv.id}`)}
            leadingIcon={<Eye className="w-3.5 h-3.5" />}
          >
            View
          </Button>
        </div>
      ),
    },
  };
  // Visual-editor configuration: column order, labels and visibility over the defaults.
  const configuredColumns = visible(resolveList(INVOICES_COLUMN_DEFS, ui.columns))
    .filter((item) => columnDefs[item.key])
    .map((item) => ({ key: item.key, label: item.label, ...columnDefs[item.key] }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div {...editable('invoices.header')} className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
            {ui.header?.title ?? INVOICES_HEADER_DEFAULTS.title}
          </h1>
          <p className="text-sm text-gray-500 mt-1">{ui.header?.subtitle ?? INVOICES_HEADER_DEFAULTS.subtitle}</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            onClick={fetchInvoices}
            disabled={loading}
            leadingIcon={<RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>
          {canCreate && (
            <Button
              variant="primary"
              onClick={() => navigate('/invoices/new')}
              leadingIcon={<Plus className="w-4 h-4" />}
            >
              New Invoice
            </Button>
          )}
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {visible(resolveList(INVOICES_KPI_DEFS, ui.kpis)).map((kpi) => {
          const card = kpiCards[kpi.key];
          if (!card) return null;
          return (
            <div
              key={kpi.key}
              {...editable(`invoices.kpi.${kpi.key}`)}
              className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between"
            >
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">{kpi.label}</p>
                <p className={`text-2xl font-bold mt-1 ${card.valueClass}`}>{card.value}</p>
              </div>
              <div className={`p-3 rounded-lg ${card.iconClass}`}>{card.icon}</div>
            </div>
          );
        })}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-6 overflow-x-auto">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors flex items-center gap-2 ${
                  isActive
                    ? 'border-indigo-600 text-indigo-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {tab.label}
                {tab.count !== undefined && (
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      isActive ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <form onSubmit={handleSearchSubmit} className="flex-1 relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search by invoice #, customer name, email..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </form>
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-gray-500">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto mb-3"></div>
            Loading invoices...
          </div>
        ) : invoices.length === 0 ? (
          <div {...editable('invoices.empty')} className="p-12 text-center text-gray-500">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <h3 className="text-base font-medium text-gray-900 mb-1">
              {ui.empty?.title ?? INVOICES_EMPTY_DEFAULTS.title}
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              {searchTerm || activeTab !== 'all'
                ? 'Try adjusting your search or tab filters.'
                : (ui.empty?.description ?? INVOICES_EMPTY_DEFAULTS.description)}
            </p>
            {canCreate && (
              <Button
                variant="primary"
                onClick={() => navigate('/invoices/new')}
                leadingIcon={<Plus className="w-4 h-4" />}
              >
                Create Invoice
              </Button>
            )}
          </div>
        ) : (
          <div {...editable('invoices.columns')} className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                <tr>
                  {configuredColumns.map((col) => (
                    <th key={col.key} className={`px-6 py-3.5 ${col.align === 'right' ? 'text-right' : ''}`}>
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white text-sm">
                {invoices.map((inv) => (
                  <tr
                    key={inv.id}
                    onClick={() => navigate(`/invoices/${inv.id}`)}
                    className="hover:bg-gray-50/75 cursor-pointer transition-colors"
                  >
                    {configuredColumns.map((col) => (
                      <td
                        key={col.key}
                        className={`px-6 py-4 ${col.cellClass}`}
                        onClick={col.key === 'actions' ? (e) => e.stopPropagation() : undefined}
                      >
                        {col.render(inv)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
