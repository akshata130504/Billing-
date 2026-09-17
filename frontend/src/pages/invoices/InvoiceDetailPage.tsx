import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Edit2,
  Send,
  CreditCard,
  Ban,
  Printer,
  AlertCircle,
  HelpCircle,
  Clock,
  Copy,
  Check,
  ExternalLink,
  Globe,
} from 'lucide-react';
import { invoiceService } from '../../services/invoiceService';
import type { Invoice, InvoiceStatus, PaymentRecordIn } from '../../types/invoices';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Modal } from '../../components/common/Modal';
import { validateDateNotFuture } from '../../utils/validation';

export const InvoiceDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [payments, setPayments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Record Payment Modal State
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [paymentAmount, setPaymentAmount] = useState<number>(0);
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().split('T')[0]);
  const [paymentMethod, setPaymentMethod] = useState<string>('bank_transfer');
  const [paymentRef, setPaymentRef] = useState('');
  const [paymentNotes, setPaymentNotes] = useState('');

  // Void Modal State
  const [showVoidModal, setShowVoidModal] = useState(false);
  const [voidReason, setVoidReason] = useState('');

  // Hosted Payment Link State
  const [copied, setCopied] = useState(false);
  const handleCopyPaymentLink = (url: string) => {
    if (!url) return;
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const fetchInvoiceData = async (invoiceId: string) => {
    try {
      setLoading(true);
      setError(null);
      const [invData, paymentsData] = await Promise.all([
        invoiceService.getInvoice(invoiceId),
        invoiceService.getInvoicePayments(invoiceId).catch(() => []),
      ]);
      setInvoice(invData);
      setPayments(paymentsData || invData.payments || []);
      setPaymentAmount(Number(invData.amount_due || invData.balance_due || 0));
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load invoice');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) {
      fetchInvoiceData(id);
    }
  }, [id]);

  const handleSend = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      await invoiceService.sendInvoice(id);
      await fetchInvoiceData(id);
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Send failed');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRecordPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !invoice) return;

    if (Number(paymentAmount) <= 0) {
      alert('Payment amount must be greater than zero');
      return;
    }

    const dateErr = validateDateNotFuture(paymentDate, 'Payment date', { required: true });
    if (dateErr) {
      alert(dateErr);
      return;
    }

    try {
      setActionLoading(true);
      const payload: PaymentRecordIn = {
        amount: Number(paymentAmount),
        payment_date: paymentDate,
        payment_method: paymentMethod,
        reference_number: paymentRef,
        notes: paymentNotes,
      };
      await invoiceService.recordPayment(id, payload);
      setShowPaymentModal(false);
      setPaymentRef('');
      setPaymentNotes('');
      await fetchInvoiceData(id);
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to record payment');
    } finally {
      setActionLoading(false);
    }
  };

  const handleVoidInvoice = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      await invoiceService.voidInvoice(id, voidReason.trim() || 'Voided by user');
      setShowVoidModal(false);
      setVoidReason('');
      await fetchInvoiceData(id);
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to void invoice');
    } finally {
      setActionLoading(false);
    }
  };

  const handlePrint = () => {
    window.print();
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

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (error || !invoice) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <span>{error || 'Invoice not found'}</span>
        </div>
        <div className="mt-4">
          <Button variant="secondary" onClick={() => navigate('/invoices')}>
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Invoices
          </Button>
        </div>
      </div>
    );
  }

  const upperStatus = String(invoice.status).toUpperCase();
  const isPaid = upperStatus === 'PAID';
  const isVoid = upperStatus === 'VOID';
  const balanceDue = Number(invoice.amount_due || invoice.balance_due || 0);
  const paymentUrl =
    invoice.public_url ||
    (invoice.public_token ? `${window.location.origin}/pay/${invoice.public_token}` : null);

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/invoices')}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">{invoice.invoice_number}</h1>
              <Badge variant={getStatusBadgeVariant(invoice.status)}>
                {String(invoice.status).replace(/_/g, ' ')}
              </Badge>
            </div>
            <p className="text-sm text-gray-500 mt-0.5">
              Issued on {invoice.issue_date || invoice.invoice_date} • Due on {invoice.due_date}
            </p>
          </div>
        </div>

        {/* Top Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={handlePrint}>
            <Printer className="w-4 h-4 mr-1.5" /> Print
          </Button>

          {paymentUrl && (
            <>
              <Button
                variant="outline"
                onClick={() => handleCopyPaymentLink(paymentUrl)}
                title="Copy secure customer payment link"
              >
                {copied ? <Check className="w-4 h-4 mr-1.5 text-emerald-600" /> : <Copy className="w-4 h-4 mr-1.5" />}
                {copied ? 'Link Copied' : 'Copy Payment Link'}
              </Button>
              <Button
                variant="secondary"
                onClick={() => window.open(paymentUrl, '_blank')}
                title="Open hosted invoice payment page in a new tab"
              >
                <ExternalLink className="w-4 h-4 mr-1.5" /> View Payment Page
              </Button>
            </>
          )}

          {upperStatus === 'DRAFT' && (
            <>
              <Button variant="secondary" onClick={() => navigate(`/invoices/${invoice.id}/edit`)}>
                <Edit2 className="w-4 h-4 mr-1.5" /> Edit
              </Button>
              <Button variant="primary" onClick={handleSend} disabled={actionLoading}>
                <Send className="w-4 h-4 mr-1.5" /> Send Invoice
              </Button>
            </>
          )}

          {!isPaid && !isVoid && (
            <Button
              variant="primary"
              onClick={() => {
                setPaymentAmount(balanceDue);
                setShowPaymentModal(true);
              }}
              disabled={actionLoading}
            >
              <CreditCard className="w-4 h-4 mr-1.5" /> Record Payment
            </Button>
          )}

          {!isVoid && upperStatus !== 'PAID' && (
            <Button variant="danger" onClick={() => setShowVoidModal(true)} disabled={actionLoading}>
              <Ban className="w-4 h-4 mr-1.5" /> Void
            </Button>
          )}
        </div>
      </div>

      {/* Main Grid: Document View & Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Printable Invoice Card */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 sm:p-8">
            {/* Header info */}
            <div className="flex flex-col sm:flex-row justify-between items-start border-b border-gray-100 pb-6 gap-4">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-indigo-600">
                  Tax Invoice
                </span>
                <h2 className="text-2xl font-extrabold text-gray-900 mt-1">
                  {invoice.invoice_number}
                </h2>
                {invoice.reference && (
                  <p className="text-gray-500 text-xs mt-1">
                    <span className="font-medium">Ref / PO:</span> {invoice.reference}
                  </p>
                )}
              </div>
              <div className="text-right space-y-1 text-sm">
                <div>
                  <span className="text-xs text-gray-500">Invoice Date: </span>
                  <span className="font-semibold text-gray-900">{invoice.issue_date || invoice.invoice_date}</span>
                </div>
                <div>
                  <span className="text-xs text-gray-500">Due Date: </span>
                  <span className="font-semibold text-gray-900">{invoice.due_date}</span>
                </div>
                <div>
                  <span className="text-xs text-gray-500">Terms: </span>
                  <span className="font-medium text-gray-700">{invoice.payment_terms || 'Net 30'}</span>
                </div>
              </div>
            </div>

            {/* Billed To / From */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 py-6 border-b border-gray-100">
              <div>
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                  Billed To
                </h3>
                <div className="text-base font-bold text-gray-900">
                  {invoice.customer?.display_name || invoice.customer?.displayName || invoice.customer?.name || 'Customer'}
                </div>
                {invoice.customer?.email && (
                  <div className="text-sm text-gray-600">{invoice.customer.email}</div>
                )}
                {invoice.customer?.phone && (
                  <div className="text-sm text-gray-600">{invoice.customer.phone}</div>
                )}
                {/* Mandatory fields on a GST tax invoice. */}
                {invoice.customer_gstin && (
                  <div className="text-sm text-gray-600">GSTIN: {invoice.customer_gstin}</div>
                )}
                {invoice.place_of_supply_name && (
                  <div className="text-sm text-gray-600">
                    Place of supply: {invoice.place_of_supply_name}
                    {invoice.place_of_supply_code ? ` (${invoice.place_of_supply_code})` : ''}
                  </div>
                )}
              </div>
              <div>
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                  Payment Details
                </h3>
                <div className="text-sm text-gray-700">
                  <span className="font-medium">Status:</span>{' '}
                  <span className="font-semibold">{String(invoice.status).replace(/_/g, ' ')}</span>
                </div>
                {invoice.salesperson && (
                  <div className="text-sm text-gray-700 mt-1">
                    <span className="font-medium">Salesperson:</span> {invoice.salesperson}
                  </div>
                )}
              </div>
            </div>

            {/* Line Items Table */}
            <div className="py-6">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">Items & Services</h3>
              <div className="overflow-x-auto border border-gray-100 rounded-lg">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50 text-left text-xs font-semibold text-gray-500">
                    <tr>
                      <th className="px-4 py-3">Item</th>
                      <th className="px-4 py-3 text-right">Qty</th>
                      <th className="px-4 py-3 text-right">Rate</th>
                      <th className="px-4 py-3 text-right">Discount</th>
                      <th className="px-4 py-3 text-right">Tax</th>
                      <th className="px-4 py-3 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {invoice.items.map((item, idx) => (
                      <tr key={idx} className="hover:bg-gray-50/50">
                        <td className="px-4 py-3">
                          <div className="font-medium text-gray-900">{item.name || item.description}</div>
                          {item.description && item.name && item.description !== item.name && (
                            <div className="text-xs text-gray-500 mt-0.5">{item.description}</div>
                          )}
                          {item.pricing_explanation && (
                            <div className="mt-1 flex items-center gap-1 text-xs text-indigo-600 bg-indigo-50/70 px-2 py-0.5 rounded w-fit">
                              <HelpCircle className="w-3.5 h-3.5" />
                              <span>{item.pricing_explanation}</span>
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-700">{item.quantity}</td>
                        <td className="px-4 py-3 text-right text-gray-700">
                          ₹{Number(item.rate || item.unit_price || 0).toLocaleString()}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-700">
                          {Number(item.discount_amount || 0) > 0
                            ? `₹${Number(item.discount_amount).toLocaleString()}`
                            : '-'}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-700">
                          {Number(item.tax_amount || 0) > 0
                            ? `₹${Number(item.tax_amount).toLocaleString()}`
                            : '-'}
                        </td>
                        <td className="px-4 py-3 text-right font-medium text-gray-900">
                          ₹{Number(item.amount || item.total_amount || 0).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Financial Summary */}
            <div className="flex justify-end border-t border-gray-100 pt-6">
              <div className="w-full sm:w-80 space-y-2 text-sm">
                <div className="flex justify-between text-gray-600">
                  <span>Subtotal</span>
                  <span>₹{Number(invoice.subtotal || 0).toLocaleString()}</span>
                </div>
                {Number(invoice.discount_amount || 0) > 0 && (
                  <div className="flex justify-between text-emerald-600">
                    <span>Discount</span>
                    <span>-₹{Number(invoice.discount_amount || 0).toLocaleString()}</span>
                  </div>
                )}
                {/* GST heads, matching the tax invoice PDF. Falls back to a single
                    "Tax" row for exports and documents predating the GST split. */}
                {Number(invoice.cgst_amount || 0) > 0 || Number(invoice.sgst_amount || 0) > 0 ? (
                  <>
                    <div className="flex justify-between text-gray-600">
                      <span>CGST</span>
                      <span>+₹{Number(invoice.cgst_amount || 0).toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between text-gray-600">
                      <span>SGST/UTGST</span>
                      <span>+₹{Number(invoice.sgst_amount || 0).toLocaleString()}</span>
                    </div>
                  </>
                ) : Number(invoice.igst_amount || 0) > 0 ? (
                  <div className="flex justify-between text-gray-600">
                    <span>IGST</span>
                    <span>+₹{Number(invoice.igst_amount || 0).toLocaleString()}</span>
                  </div>
                ) : Number(invoice.tax_amount || 0) > 0 ? (
                  <div className="flex justify-between text-gray-600">
                    <span>Tax</span>
                    <span>+₹{Number(invoice.tax_amount || 0).toLocaleString()}</span>
                  </div>
                ) : null}
                {Number(invoice.adjustment || 0) !== 0 && (
                  <div className="flex justify-between text-gray-600">
                    <span>Adjustment</span>
                    <span>₹{Number(invoice.adjustment || 0).toLocaleString()}</span>
                  </div>
                )}
                <div className="flex justify-between text-base font-bold text-gray-900 border-t border-gray-200 pt-2">
                  <span>Total Amount</span>
                  <span>₹{Number(invoice.total || invoice.total_amount || 0).toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-sm text-emerald-600 font-semibold">
                  <span>Paid to Date</span>
                  <span>₹{Number(invoice.amount_paid || invoice.paid_amount || 0).toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-lg font-extrabold text-indigo-700 border-t border-gray-100 pt-2">
                  <span>Balance Due</span>
                  <span>₹{balanceDue.toLocaleString()}</span>
                </div>
              </div>
            </div>

            {/* Notes & Terms */}
            {(invoice.notes || invoice.customer_notes || invoice.terms || invoice.terms_and_conditions) && (
              <div className="mt-8 border-t border-gray-100 pt-6 grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
                {(invoice.notes || invoice.customer_notes) && (
                  <div>
                    <h4 className="font-semibold text-gray-900 mb-1">Customer Notes</h4>
                    <p className="text-gray-600 whitespace-pre-line text-xs bg-gray-50 p-3 rounded-lg border border-gray-100">
                      {invoice.notes || invoice.customer_notes}
                    </p>
                  </div>
                )}
                {(invoice.terms || invoice.terms_and_conditions) && (
                  <div>
                    <h4 className="font-semibold text-gray-900 mb-1">Terms & Conditions</h4>
                    <p className="text-gray-600 whitespace-pre-line text-xs bg-gray-50 p-3 rounded-lg border border-gray-100">
                      {invoice.terms || invoice.terms_and_conditions}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right 1 Col: Payments History & Lifecycle */}
        <div className="space-y-6">
          {/* Payments Received Card */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
                <CreditCard className="w-4 h-4 text-indigo-600" /> Payments Received
              </h3>
              {!isPaid && !isVoid && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setPaymentAmount(balanceDue);
                    setShowPaymentModal(true);
                  }}
                >
                  + Record
                </Button>
              )}
            </div>

            {payments.length === 0 ? (
              <div className="p-6 text-center text-gray-400 text-sm bg-gray-50 rounded-lg border border-dashed border-gray-200">
                No payments recorded yet.
              </div>
            ) : (
              <div className="space-y-3">
                {payments.map((p, idx) => (
                  <div
                    key={p.id || idx}
                    className="p-3.5 bg-emerald-50/60 border border-emerald-100 rounded-lg text-sm space-y-1"
                  >
                    <div className="flex justify-between items-center font-bold text-emerald-900">
                      <span>₹{Number(p.amount || 0).toLocaleString()}</span>
                      <span className="text-xs px-2 py-0.5 bg-emerald-200/60 text-emerald-800 rounded font-semibold">
                        {p.payment_method || p.method || 'BANK'}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs text-gray-500">
                      <span>{p.payment_date || p.paid_at || new Date().toISOString().split('T')[0]}</span>
                      {p.reference_number && <span>Ref: {p.reference_number}</span>}
                    </div>
                    {p.notes && <div className="text-xs text-gray-600 pt-1">{p.notes}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Payment Status */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
            <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
              <Clock className="w-4 h-4 text-gray-500" /> Billing Status
            </h3>

            <div className="space-y-2 text-sm">
              <div className="flex justify-between py-1.5 border-b border-gray-100">
                <span className="text-gray-500">Total Invoiced</span>
                <span className="font-semibold text-gray-900">
                  ₹{Number(invoice.total || invoice.total_amount || 0).toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-gray-100 text-emerald-600">
                <span>Amount Paid</span>
                <span className="font-semibold">
                  ₹{Number(invoice.amount_paid || invoice.paid_amount || 0).toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between py-1.5 text-indigo-700 font-bold">
                <span>Remaining Balance</span>
                <span>₹{balanceDue.toLocaleString()}</span>
              </div>
            </div>
          </div>

          {/* Hosted Payment Page Card */}
          {paymentUrl && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-3">
              <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
                <Globe className="w-4 h-4 text-emerald-600" /> Hosted Payment Page
              </h3>
              <p className="text-xs text-gray-500 leading-relaxed">
                Share this secure self-service link with the customer to view this invoice and pay online via Razorpay.
              </p>
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-2.5 text-xs text-gray-600 font-mono truncate select-all">
                {paymentUrl}
              </div>
              <div className="flex items-center gap-2 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1"
                  onClick={() => handleCopyPaymentLink(paymentUrl)}
                >
                  {copied ? <Check className="w-3.5 h-3.5 mr-1 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 mr-1" />}
                  {copied ? 'Copied!' : 'Copy Link'}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  className="flex-1"
                  onClick={() => window.open(paymentUrl, '_blank')}
                >
                  <ExternalLink className="w-3.5 h-3.5 mr-1" /> View Page
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Record Payment Modal */}
      <Modal
        isOpen={showPaymentModal}
        onClose={() => setShowPaymentModal(false)}
        title="Record Payment"
      >
        <form onSubmit={handleRecordPayment} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Payment Amount (₹) <span className="text-red-500">*</span>
            </label>
            <input
              type="number"
              step="0.01"
              max={balanceDue}
              value={paymentAmount}
              onChange={(e) => setPaymentAmount(Number(e.target.value))}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-semibold focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            />
            <p className="text-xs text-gray-500 mt-1">
              Max balance payable: ₹{balanceDue.toLocaleString()}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Payment Date</label>
              <input
                type="date"
                value={paymentDate}
                max={new Date().toISOString().split('T')[0]}
                onChange={(e) => setPaymentDate(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Payment Mode</label>
              <select
                value={paymentMethod}
                onChange={(e: any) => setPaymentMethod(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              >
                <option value="bank_transfer">Bank Transfer / NEFT</option>
                <option value="upi">UPI</option>
                <option value="card">Credit / Debit Card</option>
                <option value="cheque">Cheque</option>
                <option value="cash">Cash</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Reference / Transaction ID</label>
            <input
              type="text"
              placeholder="e.g. TXN987213894"
              value={paymentRef}
              onChange={(e) => setPaymentRef(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Payment Notes</label>
            <textarea
              rows={2}
              placeholder="Additional remarks..."
              value={paymentNotes}
              onChange={(e) => setPaymentNotes(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            />
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button type="button" variant="secondary" onClick={() => setShowPaymentModal(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={actionLoading}>
              Save Payment
            </Button>
          </div>
        </form>
      </Modal>

      {/* Void Invoice Modal */}
      <Modal
        isOpen={showVoidModal}
        onClose={() => setShowVoidModal(false)}
        title="Void Invoice"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Are you sure you want to void invoice <strong>{invoice.invoice_number}</strong>? Voiding is irreversible.
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Reason for voiding</label>
            <textarea
              rows={3}
              placeholder="e.g. Created by mistake / client cancelled order..."
              value={voidReason}
              onChange={(e) => setVoidReason(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-red-500 focus:outline-none"
            />
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="secondary" onClick={() => setShowVoidModal(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleVoidInvoice} disabled={actionLoading}>
              Void Invoice
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
