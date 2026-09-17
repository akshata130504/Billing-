import { useState, useEffect } from 'react';
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

export const InvoicesListPage: React.FC = () => {
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
        params.status = activeTab.toUpperCase();
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
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load invoices');
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Invoices</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage billing, track client balances, and collect payments
          </p>
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
          <Button
            variant="primary"
            onClick={() => navigate('/invoices/new')}
            leadingIcon={<Plus className="w-4 h-4" />}
          >
            New Invoice
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Total Outstanding</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">₹{Number(kpis.total_outstanding).toLocaleString()}</p>
          </div>
          <div className="p-3 bg-red-50 text-red-600 rounded-lg">
            <AlertTriangle className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Paid Invoices</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{kpis.paid_count}</p>
          </div>
          <div className="p-3 bg-emerald-50 text-emerald-600 rounded-lg">
            <CheckCircle className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Overdue</p>
            <p className="text-2xl font-bold text-red-600 mt-1">{kpis.overdue_count}</p>
          </div>
          <div className="p-3 bg-amber-50 text-amber-600 rounded-lg">
            <Clock className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Total Revenue</p>
            <p className="text-2xl font-bold text-emerald-600 mt-1">₹{Number(kpis.total_revenue).toLocaleString()}</p>
          </div>
          <div className="p-3 bg-indigo-50 text-indigo-600 rounded-lg">
            <DollarSign className="w-6 h-6" />
          </div>
        </div>
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
          <div className="p-12 text-center text-gray-500">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <h3 className="text-base font-medium text-gray-900 mb-1">No invoices found</h3>
            <p className="text-sm text-gray-500 mb-4">
              {searchTerm || activeTab !== 'all'
                ? 'Try adjusting your search or tab filters.'
                : 'Create your first invoice to start billing your customers.'}
            </p>
            <Button
              variant="primary"
              onClick={() => navigate('/invoices/new')}
              leadingIcon={<Plus className="w-4 h-4" />}
            >
              Create Invoice
            </Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                <tr>
                  <th className="px-6 py-3.5">Invoice #</th>
                  <th className="px-6 py-3.5">Customer</th>
                  <th className="px-6 py-3.5">Date</th>
                  <th className="px-6 py-3.5">Due Date</th>
                  <th className="px-6 py-3.5 text-right">Total</th>
                  <th className="px-6 py-3.5 text-right">Paid</th>
                  <th className="px-6 py-3.5 text-right">Balance</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white text-sm">
                {invoices.map((inv) => (
                  <tr
                    key={inv.id}
                    onClick={() => navigate(`/invoices/${inv.id}`)}
                    className="hover:bg-gray-50/75 cursor-pointer transition-colors"
                  >
                    <td className="px-6 py-4 font-semibold text-indigo-600">
                      {inv.invoice_number}
                    </td>
                    <td className="px-6 py-4">
                      <div className="font-medium text-gray-900">
                        {inv.customer?.display_name || inv.customer?.displayName || inv.customer?.name || 'Customer'}
                      </div>
                      {inv.customer?.email && (
                        <div className="text-xs text-gray-500">{inv.customer.email}</div>
                      )}
                    </td>
                    <td className="px-6 py-4 text-gray-600">{inv.issue_date || inv.invoice_date}</td>
                    <td className="px-6 py-4 text-gray-600">{inv.due_date}</td>
                    <td className="px-6 py-4 text-right font-semibold text-gray-900">
                      ₹{Number(inv.total || inv.total_amount || 0).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-right text-emerald-600 font-medium">
                      ₹{Number(inv.amount_paid || inv.paid_amount || 0).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-right font-bold text-gray-900">
                      ₹{Number(inv.amount_due || inv.balance_due || 0).toLocaleString()}
                    </td>
                    <td className="px-6 py-4">
                      <Badge variant={getStatusBadgeVariant(inv.status)}>
                        {String(inv.status).replace(/_/g, ' ')}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-right" onClick={(e) => e.stopPropagation()}>
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
                    </td>
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
