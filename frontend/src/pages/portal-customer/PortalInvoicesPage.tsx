import React, { useState, useEffect } from 'react';
import {
  Download,
  CreditCard,
  Eye,
  Search,
} from 'lucide-react';
import {
  portalCustomerService,
  type PortalInvoice,
  type PortalInvoiceDetail,
} from '../../services/portalCustomerService';
import { LoadingState } from '../../components/common/LoadingState';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';

export const PortalInvoicesPage: React.FC = () => {
  const [invoices, setInvoices] = useState<PortalInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'unpaid' | 'paid'>('all');
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // Modal State
  const [selectedInvoice, setSelectedInvoice] = useState<PortalInvoiceDetail | null>(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  useEffect(() => {
    loadInvoices();
  }, []);

  const loadInvoices = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await portalCustomerService.getInvoices();
      setInvoices(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load invoices.');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPdf = async (invoiceId: string, invoiceNumber: string) => {
    try {
      setDownloadingId(invoiceId);
      await portalCustomerService.downloadInvoicePdf(invoiceId, invoiceNumber);
    } catch (err: any) {
      alert(err?.message || 'Failed to download invoice PDF.');
    } finally {
      setDownloadingId(null);
    }
  };

  const handleViewDetails = async (invoiceId: string) => {
    try {
      setModalLoading(true);
      setModalError(null);
      setSelectedInvoice(null);
      const detail = await portalCustomerService.getInvoice(invoiceId);
      setSelectedInvoice(detail);
    } catch (err: any) {
      setModalError(err?.message || 'Failed to load invoice details.');
    } finally {
      setModalLoading(false);
    }
  };

  const filtered = invoices.filter((inv) => {
    const matchesSearch =
      inv.invoice_number.toLowerCase().includes(search.toLowerCase()) ||
      inv.issue_date.includes(search);

    const due = Number(inv.amount_due);
    if (statusFilter === 'unpaid') {
      return matchesSearch && due > 0 && inv.status !== 'void';
    }
    if (statusFilter === 'paid') {
      return matchesSearch && inv.status === 'paid';
    }
    return matchesSearch;
  });

  if (loading) {
    return <LoadingState message="Loading your invoices..." />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Invoices</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Review and download your billing invoices and make payments online
          </p>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search invoice #..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-3 py-1.5 text-xs rounded-lg border border-slate-300 bg-white focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div className="flex items-center rounded-lg border border-slate-200 bg-white p-0.5 text-xs font-medium">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-3 py-1 rounded-md transition-colors ${
                statusFilter === 'all'
                  ? 'bg-indigo-50 text-indigo-700 font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setStatusFilter('unpaid')}
              className={`px-3 py-1 rounded-md transition-colors ${
                statusFilter === 'unpaid'
                  ? 'bg-indigo-50 text-indigo-700 font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Unpaid
            </button>
            <button
              onClick={() => setStatusFilter('paid')}
              className={`px-3 py-1 rounded-md transition-colors ${
                statusFilter === 'paid'
                  ? 'bg-indigo-50 text-indigo-700 font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Paid
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700">
          {error}
        </div>
      )}

      {/* Invoices Table Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            No invoices found matching your criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="px-5 py-3">Invoice #</th>
                  <th className="px-5 py-3">Issue Date</th>
                  <th className="px-5 py-3">Due Date</th>
                  <th className="px-5 py-3">Total Amount</th>
                  <th className="px-5 py-3">Balance Due</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((inv) => {
                  const due = Number(inv.amount_due);
                  const isUnpaid = due > 0 && inv.status !== 'void';
                  return (
                    <tr key={inv.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-5 py-3.5 font-semibold text-slate-900">
                        {inv.invoice_number}
                      </td>
                      <td className="px-5 py-3.5 text-slate-600">{inv.issue_date}</td>
                      <td className="px-5 py-3.5 text-slate-600">{inv.due_date}</td>
                      <td className="px-5 py-3.5 font-medium text-slate-900">
                        ₹{Number(inv.total).toLocaleString()}
                      </td>
                      <td className="px-5 py-3.5 font-semibold text-indigo-700">
                        ₹{due.toLocaleString()}
                      </td>
                      <td className="px-5 py-3.5">
                        <Badge
                          variant={
                            inv.status === 'paid'
                              ? 'success'
                              : inv.status === 'partially_paid'
                              ? 'warning'
                              : inv.status === 'overdue'
                              ? 'danger'
                              : 'neutral'
                          }
                        >
                          {inv.status.replace(/_/g, ' ')}
                        </Badge>
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleViewDetails(inv.id)}
                            title="View invoice line items and details"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={downloadingId === inv.id}
                            onClick={() => handleDownloadPdf(inv.id, inv.invoice_number)}
                            title="Download PDF"
                          >
                            <Download className="w-3.5 h-3.5" />
                          </Button>
                          {isUnpaid && inv.public_token && (
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => window.open(`/pay/${inv.public_token}`, '_blank')}
                            >
                              <CreditCard className="w-3.5 h-3.5 mr-1" /> Pay Now
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Invoice Details Modal */}
      {(selectedInvoice || modalLoading || modalError) && (
        <Modal
          isOpen={Boolean(selectedInvoice || modalLoading || modalError)}
          onClose={() => {
            setSelectedInvoice(null);
            setModalError(null);
          }}
          title={selectedInvoice ? `Invoice ${selectedInvoice.invoice_number}` : 'Invoice Details'}
        >
          {modalLoading && <LoadingState message="Loading invoice details..." />}
          {modalError && (
            <div className="p-4 bg-rose-50 text-rose-700 text-xs rounded-lg">{modalError}</div>
          )}
          {selectedInvoice && (
            <div className="space-y-6 text-slate-800">
              {/* Summary Header */}
              <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl border border-slate-100">
                <div>
                  <span className="text-xs text-slate-500 uppercase font-semibold">Total Amount</span>
                  <p className="text-xl font-bold text-slate-900">
                    ₹{Number(selectedInvoice.total).toLocaleString()}
                  </p>
                </div>
                <div className="text-right">
                  <span className="text-xs text-slate-500 uppercase font-semibold">Balance Due</span>
                  <p className="text-xl font-bold text-indigo-700">
                    ₹{Number(selectedInvoice.amount_due).toLocaleString()}
                  </p>
                </div>
              </div>

              {/* Line Items Table */}
              <div>
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                  Line Items
                </h4>
                <div className="border border-slate-200 rounded-lg overflow-hidden">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase">
                      <tr>
                        <th className="p-2.5 text-left">Description</th>
                        <th className="p-2.5 text-right">Qty</th>
                        <th className="p-2.5 text-right">Rate</th>
                        <th className="p-2.5 text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {selectedInvoice.items.map((item) => (
                        <tr key={item.id}>
                          <td className="p-2.5 font-medium text-slate-900">{item.description}</td>
                          <td className="p-2.5 text-right text-slate-600">{item.quantity}</td>
                          <td className="p-2.5 text-right text-slate-600">₹{item.unit_price}</td>
                          <td className="p-2.5 text-right font-semibold text-slate-900">
                            ₹{item.amount.toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Breakdown */}
              <div className="text-xs space-y-1.5 border-t border-slate-100 pt-3">
                <div className="flex justify-between text-slate-600">
                  <span>Subtotal</span>
                  <span>₹{Number(selectedInvoice.subtotal).toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Tax Amount</span>
                  <span>₹{Number(selectedInvoice.tax_amount).toLocaleString()}</span>
                </div>
                <div className="flex justify-between font-bold text-slate-900 text-sm pt-1 border-t border-slate-100">
                  <span>Total</span>
                  <span>₹{Number(selectedInvoice.total).toLocaleString()}</span>
                </div>
              </div>

              {/* Actions Footer */}
              <div className="flex items-center justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    handleDownloadPdf(selectedInvoice.id, selectedInvoice.invoice_number)
                  }
                >
                  <Download className="w-4 h-4 mr-1.5" /> Download PDF
                </Button>
                {Number(selectedInvoice.amount_due) > 0 && selectedInvoice.public_token && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => window.open(`/pay/${selectedInvoice.public_token}`, '_blank')}
                  >
                    <CreditCard className="w-4 h-4 mr-1.5" /> Pay Online
                  </Button>
                )}
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
};
