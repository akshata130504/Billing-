import { useState, useEffect, useMemo } from 'react';
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
import { quoteService } from '../../services/quoteService';
import type { Quote, QuoteStatus } from '../../types/quotes';

export function QuotesListPage() {
  const navigate = useNavigate();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFilter, setDateFilter] = useState('');

  const fetchQuotes = async () => {
    setIsLoading(true);
    try {
      const res = await quoteService.listQuotes();
      setQuotes(res.items);
    } catch (err) {
      console.error('Failed to fetch quotes', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchQuotes();
  }, []);

  // Dashboard KPIs
  const kpis = useMemo(() => {
    const total = quotes.length;
    const draft = quotes.filter((q) => q.status === 'draft').length;
    const pendingApproval = quotes.filter((q) => q.status === 'pending_approval').length;
    const approved = quotes.filter((q) => q.status === 'approved').length;
    const sent = quotes.filter((q) => q.status === 'sent' || q.status === 'viewed').length;
    const accepted = quotes.filter((q) => q.status === 'accepted' || q.status === 'converted' || q.status === 'invoiced').length;
    const totalValue = quotes.reduce((acc, q) => acc + Number(q.total || 0), 0);
    return { total, draft, pendingApproval, approved, sent, accepted, totalValue };
  }, [quotes]);

  // Tab & search filtering
  const filteredQuotes = useMemo(() => {
    return quotes.filter((q) => {
      // Tab filter
      if (activeTab !== 'all') {
        if (activeTab === 'invoiced' && q.status !== 'invoiced' && q.status !== 'converted') return false;
        else if (activeTab !== 'invoiced' && q.status !== activeTab) return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchNum = q.quote_number.toLowerCase().includes(query);
        const matchCust = (q.customer?.display_name || '').toLowerCase().includes(query);
        const matchCustNo = (q.customer?.customer_number || '').toLowerCase().includes(query);
        const matchEmail = (q.customer?.email || '').toLowerCase().includes(query);
        const matchTitle = (q.title || '').toLowerCase().includes(query);
        if (!matchNum && !matchCust && !matchCustNo && !matchEmail && !matchTitle) return false;
      }

      // Date filter
      if (dateFilter && q.issue_date !== dateFilter) {
        return false;
      }

      return true;
    });
  }, [quotes, activeTab, searchQuery, dateFilter]);

  const handleSendQuote = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await quoteService.sendQuote(id);
      await fetchQuotes();
    } catch (err) {
      console.error('Failed to send quote', err);
    }
  };

  const handleApproveQuote = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await quoteService.approveQuote(id);
      await fetchQuotes();
    } catch (err) {
      console.error('Failed to approve quote', err);
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
      console.error('Failed to convert quote', err);
    }
  };

  const handleDeleteQuote = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this draft quote?')) {
      try {
        await quoteService.deleteQuote(id);
        await fetchQuotes();
      } catch (err) {
        console.error('Failed to delete quote', err);
      }
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

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 animate-in fade-in duration-150">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900">Quotes & Proposals</h1>
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
              Revenue Lifecycle
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Create, price, discount-gate, send, track customer acceptance, and automatically convert quotes to invoices.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link to="/quotes/new">
            <Button variant="primary" size="sm" leadingIcon={<Plus className="w-4 h-4" />}>
              New Quote
            </Button>
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
        <div className="bg-white p-3.5 rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Total Quotes</p>
          <p className="text-xl font-bold text-slate-900 mt-1">{kpis.total}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">All propositions</p>
        </div>

        <div className="bg-white p-3.5 rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Draft</p>
          <p className="text-xl font-bold text-slate-700 mt-1">{kpis.draft}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">In composition</p>
        </div>

        <div className="bg-white p-3.5 rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Pending Approval</p>
          <p className="text-xl font-bold text-amber-600 mt-1">{kpis.pendingApproval}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">Above discount threshold</p>
        </div>

        <div className="bg-white p-3.5 rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Sent / Viewed</p>
          <p className="text-xl font-bold text-indigo-600 mt-1">{kpis.sent}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">With customer</p>
        </div>

        <div className="bg-white p-3.5 rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Accepted</p>
          <p className="text-xl font-bold text-emerald-600 mt-1">{kpis.accepted}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">Ready for invoice</p>
        </div>

        <div className="bg-white p-3.5 rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Total Value</p>
          <p className="text-xl font-bold text-slate-900 mt-1">₹{Math.round(kpis.totalValue).toLocaleString('en-IN')}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">Pipeline pipeline</p>
        </div>
      </div>

      {/* Tabs & Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs space-y-3">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          {/* Tabs */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl text-xs font-semibold text-slate-600 overflow-x-auto">
            {[
              { id: 'all', label: 'All' },
              { id: 'draft', label: 'Draft' },
              { id: 'pending_approval', label: 'Pending Approval' },
              { id: 'approved', label: 'Approved' },
              { id: 'sent', label: 'Sent' },
              { id: 'accepted', label: 'Accepted' },
              { id: 'invoiced', label: 'Invoiced' },
              { id: 'declined', label: 'Declined' },
            ].map((tab) => (
              <button
                key={tab.id}
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
              onClick={fetchQuotes}
              title="Refresh"
              leadingIcon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
        {isLoading ? (
          <div className="py-16">
            <LoadingState message="Loading quotes and proposals..." />
          </div>
        ) : (
          <table className="w-full text-left text-xs text-slate-600 border-collapse">
            <thead className="bg-slate-50 border-b border-slate-200/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3">Quote #</th>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Quote Date</th>
                <th className="px-4 py-3">Expiry Date</th>
                <th className="px-4 py-3">Amount</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredQuotes.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-400 italic">
                    No quotes found. Click &quot;New Quote&quot; to create your first quote.
                  </td>
                </tr>
              ) : (
                filteredQuotes.map((quote) => (
                  <tr
                    key={quote.id}
                    onClick={() => navigate(`/quotes/${quote.id}`)}
                    className="hover:bg-slate-50/80 transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-3">
                      <span className="font-bold font-mono text-slate-900">{quote.quote_number}</span>
                      {quote.title && <p className="text-[10px] text-slate-400 truncate max-w-xs">{quote.title}</p>}
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-semibold text-slate-900">{quote.customer?.display_name}</p>
                      <p className="text-[10px] text-slate-400">{quote.customer?.customer_number}</p>
                    </td>
                    <td className="px-4 py-3">{quote.issue_date}</td>
                    <td className="px-4 py-3">{quote.expiry_date || '—'}</td>
                    <td className="px-4 py-3 font-semibold text-slate-900">
                      ₹{Number(quote.total).toLocaleString('en-IN')}
                      {Number(quote.discount_pct) > 0 && (
                        <span className="text-[10px] text-amber-600 block">({quote.discount_pct}% off)</span>
                      )}
                    </td>
                    <td className="px-4 py-3">{getStatusBadge(quote.status)}</td>
                    <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1.5">
                        <Link to={`/quotes/${quote.id}`}>
                          <button className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100" title="View Quote">
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                        </Link>

                        {(quote.status === 'draft' || quote.status === 'pending_approval') && (
                          <Link to={`/quotes/${quote.id}/edit`}>
                            <button className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100" title="Edit Quote">
                              <Edit2 className="w-3.5 h-3.5" />
                            </button>
                          </Link>
                        )}

                        {quote.status === 'pending_approval' && (
                          <button
                            onClick={(e) => handleApproveQuote(quote.id, e)}
                            className="p-1 rounded text-amber-600 hover:bg-amber-50"
                            title="Approve Quote Discount"
                          >
                            <CheckSquare className="w-3.5 h-3.5" />
                          </button>
                        )}

                        {(quote.status === 'draft' || quote.status === 'approved') && (
                          <button
                            onClick={(e) => handleSendQuote(quote.id, e)}
                            className="p-1 rounded text-indigo-600 hover:bg-indigo-50"
                            title="Send to Customer"
                          >
                            <Send className="w-3.5 h-3.5" />
                          </button>
                        )}

                        {quote.status === 'accepted' && (
                          <button
                            onClick={(e) => handleConvertToInvoice(quote.id, e)}
                            className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-600 text-white hover:bg-emerald-700 flex items-center gap-1"
                            title="Convert to Live Invoice"
                          >
                            <Receipt className="w-3 h-3" />
                            Invoice
                          </button>
                        )}

                        {quote.status === 'draft' && (
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
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default QuotesListPage;
