import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Edit2,
  Send,
  CheckCircle,
  XCircle,
  Eye,
  Printer,
  Download,
  Trash2,
  Clock,
  AlertCircle,
  HelpCircle,
  CreditCard,
  Repeat,
} from 'lucide-react';
import { quoteService } from '../../services/quoteService';
import type { Quote } from '../../types/quotes';
import { calculateValidityDays, formatQuoteTerms, updateTermsValidity } from '../../utils/format';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Modal } from '../../components/common/Modal';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { loadPreferences } from '../settings/PreferencesTab';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';

export const QuoteDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canEdit = hasRole('finance');
  const canApprove = hasRole('admin');

  const [quote, setQuote] = useState<Quote | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [showSendConfirm, setShowSendConfirm] = useState(false);

  const validityDays = quote ? calculateValidityDays(quote.issue_date || quote.quote_date, quote.expiry_date) : null;
  const displayTerms = quote
    ? (quote.terms
        ? (validityDays ? updateTermsValidity(quote.terms, validityDays) : quote.terms)
        : (quote.terms_and_conditions || (validityDays ? formatQuoteTerms(validityDays) : null)))
    : null;

  // Modals
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [showConvertModal, setShowConvertModal] = useState(false);
  const [showSubscriptionModal, setShowSubscriptionModal] = useState(false);
  const [subTrialDays, setSubTrialDays] = useState('');
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  useEffect(() => {
    if (id) {
      fetchQuote(id);
    }
  }, [id]);

  const fetchQuote = async (quoteId: string) => {
    try {
      setLoading(true);
      setError(null);
      const data = await quoteService.getQuote(quoteId);
      setQuote(data);
    } catch (err) {
      setError(toApiError(err).message || 'Failed to load quote details');
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (actionFn: () => Promise<unknown>, successMessage?: string) => {
    try {
      setActionLoading(true);
      await actionFn();
      if (successMessage) showToast('success', successMessage);
      if (id) await fetchQuote(id);
    } catch (err) {
      showToast('error', 'Action failed', toApiError(err).message);
    } finally {
      setActionLoading(false);
    }
  };

  /** Toast for a send result: pending approval, sent, or sent without the customer email. */
  const notifySendResult = (sent: Quote) => {
    if (sent.status.toUpperCase() === 'PENDING_APPROVAL') {
      showToast('info', 'Discount approval requested', 'An admin must approve this quote before it is sent.');
    } else if (sent.email_sent === false) {
      showToast('warning', quoteService.EMAIL_NOT_SENT_MESSAGE);
    } else {
      showToast('success', 'Quote sent');
    }
  };

  const handleApprove = () => {
    if (!id) return;
    // Approving the discount sends the quote to the customer straight away.
    handleAction(() => quoteService.approveQuote(id), 'Quote approved and sent to the customer');
  };

  const handleRejectConfirm = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      await quoteService.rejectQuote(id, rejectionReason);
      setShowRejectModal(false);
      setRejectionReason('');
      showToast('success', 'Quote rejected');
      await fetchQuote(id);
    } catch (err) {
      showToast('error', 'Rejection failed', toApiError(err).message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSend = () => {
    if (!id) return;
    const prefs = loadPreferences();
    if (prefs.confirmBeforeSendInvoice) {
      setShowSendConfirm(true);
    } else {
      executeSend();
    }
  };

  const executeSend = () => {
    setShowSendConfirm(false);
    if (!id) return;
    handleAction(async () => notifySendResult(await quoteService.sendQuote(id)));
  };

  const handleMarkViewed = () => {
    if (!id) return;
    handleAction(() => quoteService.markViewed(id));
  };

  const handleAccept = () => {
    if (!id) return;
    handleAction(() => quoteService.acceptQuote(id), 'Quote marked as accepted');
  };

  const handleDecline = () => {
    if (!id) return;
    handleAction(() => quoteService.declineQuote(id), 'Quote marked as declined');
  };

  const handleConvertToInvoice = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      const invoice = await quoteService.convertToInvoice(id);
      setShowConvertModal(false);
      navigate(`/invoices/${invoice.id}`);
    } catch (err) {
      showToast('error', 'Conversion failed', toApiError(err).message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleConvertToSubscription = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      const trial = subTrialDays.trim() === '' ? undefined : Math.max(0, parseInt(subTrialDays, 10) || 0);
      const subscription = await quoteService.convertToSubscription(id, { trial_days: trial });
      setShowSubscriptionModal(false);
      showToast('success', 'Subscription created', `Subscription ${subscription.subscription_number} created from this quote.`);
      navigate(`/subscriptions/${subscription.id}`);
    } catch (err) {
      showToast('error', 'Conversion failed', toApiError(err).message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!id) return;
    try {
      setActionLoading(true);
      await quoteService.deleteQuote(id);
      showToast('success', 'Quote deleted');
      navigate('/quotes');
    } catch (err) {
      showToast('error', 'Delete failed', toApiError(err).message);
    } finally {
      setActionLoading(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const handleDownloadPdf = async () => {
    if (!id || !quote) return;
    try {
      setDownloadingPdf(true);
      await quoteService.downloadPdf(id, quote.quote_number);
    } catch (err) {
      showToast('error', 'Failed to download quote PDF', toApiError(err).message);
    } finally {
      setDownloadingPdf(false);
    }
  };

  const getStatusBadgeVariant = (status: string) => {
    const s = status.toUpperCase();
    switch (s) {
      case 'DRAFT':
        return 'neutral';
      case 'PENDING_APPROVAL':
        return 'warning';
      case 'APPROVED':
        return 'info';
      case 'SENT':
      case 'VIEWED':
        return 'primary';
      case 'ACCEPTED':
      case 'INVOICED':
      case 'CONVERTED':
        return 'success';
      case 'PARTIALLY_INVOICED':
        return 'info';
      case 'DECLINED':
      case 'EXPIRED':
        return 'danger';
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

  if (error || !quote) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <span>{error || 'Quote not found'}</span>
        </div>
        <div className="mt-4">
          <Button variant="secondary" onClick={() => navigate('/quotes')}>
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Quotes
          </Button>
        </div>
      </div>
    );
  }

  const upperStatus = quote.status.toUpperCase();
  // Only quotes whose lines reference a plan / catalog plan can become a subscription
  // (the server re-validates that each one is recurring and active).
  const hasRecurringLines =
    (quote.items || []).length > 0 && (quote.items || []).every((item) => Boolean(item.plan_id || item.offering_id));

  return (
    <div className="space-y-6">
      {/* Top Header & Breadcrumb */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 no-print">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/quotes')}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">{quote.quote_number}</h1>
              <Badge variant={getStatusBadgeVariant(quote.status)}>
                {quote.status.replace(/_/g, ' ')}
              </Badge>
            </div>
            <p className="text-sm text-gray-500 mt-0.5">
              Created on {new Date(quote.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>

        {/* Action Buttons based on Status */}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={handlePrint}>
            <Printer className="w-4 h-4 mr-1.5" /> Print
          </Button>
          <Button
            variant="secondary"
            onClick={handleDownloadPdf}
            disabled={downloadingPdf}
            title="Download backend-generated PDF"
          >
            {downloadingPdf ? (
              <>
                <div className="w-4 h-4 border-2 border-gray-500 border-t-transparent rounded-full animate-spin mr-1.5" />
                Generating...
              </>
            ) : (
              <>
                <Download className="w-4 h-4 mr-1.5" /> Download PDF
              </>
            )}
          </Button>

          {/* DRAFT */}
          {canEdit && upperStatus === 'DRAFT' && (
            <>
              <Button variant="secondary" onClick={() => navigate(`/quotes/${quote.id}/edit`)}>
                <Edit2 className="w-4 h-4 mr-1.5" /> Edit
              </Button>
              <Button
                variant="primary"
                onClick={handleSend}
                disabled={actionLoading}
                title="Sends the quote, or requests admin approval when the discount exceeds the threshold"
              >
                <Send className="w-4 h-4 mr-1.5" /> Send Quote
              </Button>
              <Button variant="danger" onClick={() => setShowDeleteModal(true)} disabled={actionLoading}>
                <Trash2 className="w-4 h-4 mr-1.5" /> Delete
              </Button>
            </>
          )}

          {/* PENDING APPROVAL (admin only; approving sends the quote immediately) */}
          {canApprove && upperStatus === 'PENDING_APPROVAL' && (
            <>
              <Button variant="primary" onClick={handleApprove} disabled={actionLoading}>
                <CheckCircle className="w-4 h-4 mr-1.5" /> Approve &amp; Send
              </Button>
              <Button variant="danger" onClick={() => setShowRejectModal(true)} disabled={actionLoading}>
                <XCircle className="w-4 h-4 mr-1.5" /> Reject Quote
              </Button>
            </>
          )}
          {!canApprove && upperStatus === 'PENDING_APPROVAL' && (
            <span className="text-sm text-amber-700">Awaiting admin approval</span>
          )}

          {/* APPROVED (legacy: approval now sends immediately, but the backend still allows sending these) */}
          {canEdit && upperStatus === 'APPROVED' && (
            <>
              <Button variant="secondary" onClick={() => navigate(`/quotes/${quote.id}/edit`)}>
                <Edit2 className="w-4 h-4 mr-1.5" /> Edit
              </Button>
              <Button variant="primary" onClick={handleSend} disabled={actionLoading}>
                <Send className="w-4 h-4 mr-1.5" /> Send to Customer
              </Button>
            </>
          )}

          {/* SENT */}
          {canEdit && upperStatus === 'SENT' && (
            <>
              <Button variant="secondary" onClick={handleMarkViewed} disabled={actionLoading}>
                <Eye className="w-4 h-4 mr-1.5" /> Mark Viewed
              </Button>
              <Button variant="primary" onClick={handleAccept} disabled={actionLoading}>
                <CheckCircle className="w-4 h-4 mr-1.5" /> Accept Quote
              </Button>
              <Button variant="danger" onClick={handleDecline} disabled={actionLoading}>
                <XCircle className="w-4 h-4 mr-1.5" /> Decline
              </Button>
            </>
          )}

          {/* VIEWED */}
          {canEdit && upperStatus === 'VIEWED' && (
            <>
              <Button variant="primary" onClick={handleAccept} disabled={actionLoading}>
                <CheckCircle className="w-4 h-4 mr-1.5" /> Accept Quote
              </Button>
              <Button variant="danger" onClick={handleDecline} disabled={actionLoading}>
                <XCircle className="w-4 h-4 mr-1.5" /> Decline
              </Button>
            </>
          )}

          {/* ACCEPTED / PARTIALLY_INVOICED */}
          {canEdit && (upperStatus === 'ACCEPTED' || upperStatus === 'PARTIALLY_INVOICED') && (
            <Button variant="primary" onClick={() => setShowConvertModal(true)} disabled={actionLoading}>
              <CreditCard className="w-4 h-4 mr-1.5" /> Convert to Invoice
            </Button>
          )}
          {canEdit && upperStatus === 'ACCEPTED' && hasRecurringLines && (
            <Button variant="secondary" onClick={() => setShowSubscriptionModal(true)} disabled={actionLoading}>
              <Repeat className="w-4 h-4 mr-1.5" /> Convert to Subscription
            </Button>
          )}
          {quote.converted_subscription_id && (
            <Button variant="secondary" onClick={() => navigate(`/subscriptions/${quote.converted_subscription_id}`)}>
              <Repeat className="w-4 h-4 mr-1.5" /> View Subscription
            </Button>
          )}
        </div>
      </div>

      {/* Main Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 print:block">
        {/* Left 2 Columns: Quote Document Details */}
        <div className="lg:col-span-2 space-y-6 print:w-full">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden p-6 sm:p-8 print:border-none print:shadow-none print:p-0">
            {/* Document Header */}
            <div className="flex flex-col sm:flex-row justify-between items-start border-b border-gray-100 pb-6 gap-4">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-indigo-600">Quote</span>
                <h2 className="text-2xl font-bold text-gray-900 mt-1">{quote.quote_number}</h2>
                {(quote.subject || quote.title) && (
                  <p className="text-gray-600 text-sm mt-1">{quote.subject || quote.title}</p>
                )}
              </div>
              <div className="text-right">
                <div className="text-xs text-gray-500 font-medium">Quote Date</div>
                <div className="text-sm font-semibold text-gray-900">{quote.issue_date || quote.quote_date}</div>
                <div className="text-xs text-gray-500 font-medium mt-2">Expiry Date</div>
                <div className="text-sm font-semibold text-gray-900">{quote.expiry_date || 'N/A'}</div>
              </div>
            </div>

            {/* Customer Information */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 py-6 border-b border-gray-100">
              <div>
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Quote For</h3>
                <div className="text-base font-semibold text-gray-900">
                  {quote.customer?.display_name || quote.customer?.displayName || quote.customer?.name || 'Customer'}
                </div>
                {quote.customer?.email && (
                  <div className="text-sm text-gray-600">{quote.customer.email}</div>
                )}
                {quote.customer?.phone && (
                  <div className="text-sm text-gray-600">{quote.customer.phone}</div>
                )}
              </div>
              <div>
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Salesperson</h3>
                <div className="text-sm font-medium text-gray-900">
                  {quote.salesperson || 'Not assigned'}
                </div>
                {quote.reference_number && (
                  <div className="text-sm text-gray-500 mt-2">
                    <span className="font-medium">Ref:</span> {quote.reference_number}
                  </div>
                )}
              </div>
            </div>

            {/* Line Items Table */}
            <div className="py-6">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">Line Items</h3>
              <div className="overflow-x-auto border border-gray-100 rounded-lg">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50 text-left text-xs font-medium text-gray-500">
                    <tr>
                      <th className="px-4 py-3">Item & Description</th>
                      <th className="px-4 py-3 text-right">Qty</th>
                      <th className="px-4 py-3 text-right">Rate</th>
                      <th className="px-4 py-3 text-right">Discount</th>
                      <th className="px-4 py-3 text-right">Tax</th>
                      <th className="px-4 py-3 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white text-sm">
                    {quote.items.map((item, idx) => (
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
                          {Number(item.discount_amount || 0) > 0 ? `₹${Number(item.discount_amount).toLocaleString()}` : '-'}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-700">
                          {Number(item.tax_amount || 0) > 0 ? `₹${Number(item.tax_amount).toLocaleString()}` : '-'}
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

            {/* Totals Breakdown */}
            <div className="flex justify-end border-t border-gray-100 pt-6">
              <div className="w-full sm:w-72 space-y-2 text-sm">
                <div className="flex justify-between text-gray-600">
                  <span>Subtotal</span>
                  <span>₹{Number(quote.subtotal || 0).toLocaleString()}</span>
                </div>
                {Number(quote.discount_amount || 0) > 0 && (
                  <div className="flex justify-between text-green-600">
                    <span>Discount</span>
                    <span>-₹{Number(quote.discount_amount || 0).toLocaleString()}</span>
                  </div>
                )}
                {Number(quote.tax_amount || 0) > 0 && (
                  <div className="flex justify-between text-gray-600">
                    <span>Tax</span>
                    <span>+₹{Number(quote.tax_amount || 0).toLocaleString()}</span>
                  </div>
                )}
                {Number(quote.adjustment || 0) !== 0 && (
                  <div className="flex justify-between text-gray-600">
                    <span>Adjustment</span>
                    <span>₹{Number(quote.adjustment || 0).toLocaleString()}</span>
                  </div>
                )}
                <div className="flex justify-between text-base font-bold text-gray-900 border-t border-gray-200 pt-2">
                  <span>Total</span>
                  <span className="text-indigo-600">
                    ₹{Number(quote.total || quote.total_amount || 0).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>

            {/* Terms and Notes */}
            {(quote.notes || quote.customer_notes || displayTerms) && (
              <div className="mt-8 border-t border-gray-100 pt-6 grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
                {(quote.notes || quote.customer_notes) && (
                  <div>
                    <h4 className="font-semibold text-gray-900 mb-1">Customer Notes</h4>
                    <p className="text-gray-600 whitespace-pre-line text-xs bg-gray-50 p-3 rounded-lg border border-gray-100">
                      {quote.notes || quote.customer_notes}
                    </p>
                  </div>
                )}
                {displayTerms && (
                  <div>
                    <h4 className="font-semibold text-gray-900 mb-1">Terms & Conditions</h4>
                    <p className="text-gray-600 whitespace-pre-line text-xs bg-gray-50 p-3 rounded-lg border border-gray-100">
                      {displayTerms}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Status & Timeline Actions */}
        <div className="space-y-6 no-print">
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
            <h3 className="text-base font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <Clock className="w-4 h-4 text-gray-500" /> Lifecycle Status
            </h3>

            <div className="space-y-4">
              <div className="flex items-center justify-between text-sm py-2 border-b border-gray-100">
                <span className="text-gray-500">Current Status</span>
                <Badge variant={getStatusBadgeVariant(quote.status)}>
                  {quote.status.replace(/_/g, ' ')}
                </Badge>
              </div>

              {quote.approved_by && (
                <div className="text-sm py-2 border-b border-gray-100">
                  <div className="text-gray-500">Approved By</div>
                  <div className="font-medium text-gray-900 mt-0.5">{quote.approved_by}</div>
                  {quote.approved_at && (
                    <div className="text-xs text-gray-400 mt-0.5">
                      {new Date(quote.approved_at).toLocaleString()}
                    </div>
                  )}
                </div>
              )}

              {quote.rejection_reason && (
                <div className="text-sm py-2 border-b border-gray-100 bg-red-50 p-3 rounded-lg">
                  <div className="text-red-700 font-medium">Rejection Reason</div>
                  <div className="text-red-600 text-xs mt-1">{quote.rejection_reason}</div>
                </div>
              )}

              {quote.invoiced_amount !== undefined && quote.invoiced_amount > 0 && (
                <div className="text-sm py-2 border-b border-gray-100">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Invoiced Amount</span>
                    <span className="font-semibold text-indigo-600">
                      ₹{Number(quote.invoiced_amount).toLocaleString()}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Quick Actions Guide */}
          <div className="bg-gradient-to-br from-indigo-50 to-blue-50 border border-indigo-100 rounded-xl p-6 text-sm">
            <h4 className="font-semibold text-indigo-950 mb-2">Quote Workflow</h4>
            <p className="text-xs text-indigo-800 leading-relaxed">
              Standard Quote Lifecycle: <br />
              <span className="font-medium">Draft → Pending Approval → Approved → Sent → Accepted → Invoiced</span>
            </p>
          </div>
        </div>
      </div>

      {/* Reject Quote Modal */}
      <Modal
        isOpen={showRejectModal}
        onClose={() => setShowRejectModal(false)}
        title="Reject Quote"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Please provide a reason for rejecting this quote. The author will be notified to make revisions.
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Reason</label>
            <textarea
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-red-500 focus:outline-none"
              placeholder="E.g. Discount too high, margin requirements not met..."
            />
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="secondary" onClick={() => setShowRejectModal(false)}>Cancel</Button>
            <Button variant="danger" onClick={handleRejectConfirm} disabled={!rejectionReason || actionLoading}>
              Reject Quote
            </Button>
          </div>
        </div>
      </Modal>

      {/* Convert to Invoice Modal */}
      <Modal
        isOpen={showConvertModal}
        onClose={() => setShowConvertModal(false)}
        title="Convert Quote to Invoice"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            This will generate a new official Invoice with all line items, customer info, pricing snapshots, and discounts carried over from this accepted quote.
          </p>
          <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 text-sm space-y-1">
            <div className="flex justify-between">
              <span className="text-gray-500">Customer:</span>
              <span className="font-medium text-gray-900">
                {quote.customer?.display_name || quote.customer?.displayName || quote.customer?.name}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Total Invoice Amount:</span>
              <span className="font-bold text-indigo-600">
                ₹{Number(quote.total || quote.total_amount || 0).toLocaleString()}
              </span>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="secondary" onClick={() => setShowConvertModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleConvertToInvoice} disabled={actionLoading}>
              Create Invoice Now
            </Button>
          </div>
        </div>
      </Modal>

      {/* Convert to Subscription Modal */}
      <Modal
        isOpen={showSubscriptionModal}
        onClose={() => setShowSubscriptionModal(false)}
        title="Convert Quote to Subscription"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Creates a recurring subscription from this quote's plan lines at the approved prices, discount, GST and
            currency. Every line must be a recurring plan (legacy plan or Plans &amp; Pricing plan); the first period
            is invoiced immediately unless a trial applies.
          </p>
          <label className="block text-sm">
            <span className="text-gray-700 font-medium">Trial days (optional)</span>
            <input
              type="number"
              min={0}
              value={subTrialDays}
              onChange={(e) => setSubTrialDays(e.target.value)}
              placeholder="Plan default"
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
          </label>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="secondary" onClick={() => setShowSubscriptionModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleConvertToSubscription} disabled={actionLoading}>
              Create Subscription
            </Button>
          </div>
        </div>
      </Modal>

      {/* Delete Modal */}
      <Modal
        isOpen={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        title="Delete Draft Quote"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Are you sure you want to permanently delete draft quote <strong>{quote.quote_number}</strong>? This action cannot be undone.
          </p>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>Cancel</Button>
            <Button variant="danger" onClick={handleDelete} disabled={actionLoading}>
              Delete Permanently
            </Button>
          </div>
        </div>
      </Modal>

      {/* Send Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showSendConfirm}
        onClose={() => setShowSendConfirm(false)}
        onConfirm={executeSend}
        title="Send Quote"
        description={`Are you sure you want to send quote ${quote?.quote_number || ''} to ${quote?.customer?.display_name || 'the customer'}? This will dispatch an email with the quote link.`}
        confirmLabel="Send Quote"
        isLoading={actionLoading}
      />
    </div>
  );
};
