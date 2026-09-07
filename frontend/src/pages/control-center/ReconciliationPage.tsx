import { useState } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import {
  ArrowRight,
  RefreshCw,
  ShieldCheck,
  CreditCard,
  Building2,
  FileText,
  UserCheck,
} from 'lucide-react';

interface ReconciliationItem {
  id: string;
  paymentRef: string;
  externalTxn: string;
  invoiceRef: string;
  customer: string;
  amount: string;
  gateway: 'Stripe' | 'Razorpay' | 'HDFC Wire' | 'ICICI ACH';
  status: 'matched' | 'unmatched' | 'exception' | 'auto-reconciled';
  variance?: string;
  discrepancyNote?: string;
}

const mockReconciliations: ReconciliationItem[] = [
  {
    id: 'REC-501',
    paymentRef: 'PAY-8921',
    externalTxn: 'ch_3N8zKq2eZvKYlo2C',
    invoiceRef: 'INV-2026-0791',
    customer: 'Apex Global Logistics',
    amount: '$4,800.00',
    gateway: 'Stripe',
    status: 'auto-reconciled',
  },
  {
    id: 'REC-502',
    paymentRef: 'PAY-8922',
    externalTxn: 'pay_N9m0Lq3x89vB',
    invoiceRef: 'INV-2026-0792',
    customer: 'CloudScale Systems',
    amount: '$12,400.00',
    gateway: 'Razorpay',
    status: 'matched',
  },
  {
    id: 'REC-503',
    paymentRef: 'PAY-8923',
    externalTxn: 'UTR_HDFC002938102',
    invoiceRef: 'INV-2026-0785',
    customer: 'Starlight Media Group',
    amount: '$18,400.00',
    gateway: 'HDFC Wire',
    status: 'exception',
    variance: '+$400.00',
    discrepancyNote: 'Wire settlement amount exceeds invoice gross by bank fee charge differential.',
  },
  {
    id: 'REC-504',
    paymentRef: 'PAY-8924',
    externalTxn: 'ACH_99182348',
    invoiceRef: 'UNASSIGNED',
    customer: 'Zenith Retail India',
    amount: '$7,250.00',
    gateway: 'ICICI ACH',
    status: 'unmatched',
    discrepancyNote: 'Customer remittance slip missing matching invoice number.',
  },
  {
    id: 'REC-505',
    paymentRef: 'PAY-8925',
    externalTxn: 'ch_3N8zXv2eZvKYlo8J',
    invoiceRef: 'INV-2026-0801',
    customer: 'Vanguard Technologies',
    amount: '$22,000.00',
    gateway: 'Stripe',
    status: 'auto-reconciled',
  },
];

export function ReconciliationPage() {
  const [items, setItems] = useState<ReconciliationItem[]>(mockReconciliations);
  const [selectedException, setSelectedException] = useState<ReconciliationItem | null>(null);
  const [activeTab, setActiveTab] = useState<'all' | 'unmatched' | 'exception' | 'reconciled'>('all');
  const { showToast } = useToast();

  const handleMatch = (id: string) => {
    setItems((prev) =>
      prev.map((it) => (it.id === id ? { ...it, status: 'matched', invoiceRef: 'INV-2026-MANUAL' } : it))
    );
    showToast('success', 'Matched', `Transaction ${id} successfully reconciled with invoice.`);
  };

  const filteredItems = items.filter((item) => {
    if (activeTab === 'all') return true;
    if (activeTab === 'unmatched') return item.status === 'unmatched';
    if (activeTab === 'exception') return item.status === 'exception';
    if (activeTab === 'reconciled') return item.status === 'matched' || item.status === 'auto-reconciled';
    return true;
  });

  const matchedCount = items.filter((i) => i.status === 'matched').length;
  const autoCount = items.filter((i) => i.status === 'auto-reconciled').length;
  const unmatchedCount = items.filter((i) => i.status === 'unmatched').length;
  const exceptionCount = items.filter((i) => i.status === 'exception').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              Control Center
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              Ledger Settlement
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Reconciliation
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Automated multi-way matching linking payment receipts, external gateway settlement records, open invoices, and customer accounts.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<RefreshCw className="w-3.5 h-3.5" />}
            onClick={() => showToast('info', 'Reconciled', 'Run automated settlement matching job.')}
          >
            Run Auto-Reconcile
          </Button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 font-medium">Auto-Reconciled</p>
            <h3 className="text-xl font-bold text-emerald-600 mt-0.5">{autoCount}</h3>
            <span className="text-[10px] text-slate-400">Zero touch matching</span>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 font-medium">Manual Matched</p>
            <h3 className="text-xl font-bold text-brand-600 mt-0.5">{matchedCount}</h3>
            <span className="text-[10px] text-slate-400">Verified by finance</span>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 font-medium">Unmatched</p>
            <h3 className="text-xl font-bold text-amber-600 mt-0.5">{unmatchedCount}</h3>
            <span className="text-[10px] text-slate-400">Missing invoice link</span>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 font-medium">Exceptions</p>
            <h3 className="text-xl font-bold text-rose-600 mt-0.5">{exceptionCount}</h3>
            <span className="text-[10px] text-slate-400">Amount/currency variance</span>
          </CardContent>
        </Card>
      </div>

      {/* Flow Diagram Card */}
      <Card>
        <CardContent className="p-4 sm:p-5">
          <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-3">
            Multi-Way Matching Architecture Pipeline
          </p>
          <div className="flex items-center justify-between gap-2 overflow-x-auto text-xs py-1">
            <div className="flex items-center gap-2 p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 shrink-0">
              <CreditCard className="w-4 h-4 text-brand-600" />
              <span className="font-semibold text-slate-800">1. Payment Receipt</span>
            </div>
            <ArrowRight className="w-4 h-4 text-slate-300 shrink-0" />
            <div className="flex items-center gap-2 p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 shrink-0">
              <Building2 className="w-4 h-4 text-brand-600" />
              <span className="font-semibold text-slate-800">2. External Settlement</span>
            </div>
            <ArrowRight className="w-4 h-4 text-slate-300 shrink-0" />
            <div className="flex items-center gap-2 p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 shrink-0">
              <FileText className="w-4 h-4 text-brand-600" />
              <span className="font-semibold text-slate-800">3. Invoice Line Items</span>
            </div>
            <ArrowRight className="w-4 h-4 text-slate-300 shrink-0" />
            <div className="flex items-center gap-2 p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 shrink-0">
              <UserCheck className="w-4 h-4 text-brand-600" />
              <span className="font-semibold text-slate-800">4. Customer Ledger</span>
            </div>
            <ArrowRight className="w-4 h-4 text-slate-300 shrink-0" />
            <div className="flex items-center gap-2 p-2.5 rounded-xl bg-emerald-50 text-emerald-700 border border-emerald-200 shrink-0 font-bold">
              <ShieldCheck className="w-4 h-4" />
              <span>5. Reconciled</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2">
        {[
          { id: 'all', label: 'All Records' },
          { id: 'unmatched', label: 'Unmatched' },
          { id: 'exception', label: 'Exceptions' },
          { id: 'reconciled', label: 'Reconciled' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium capitalize transition-colors cursor-pointer ${
              activeTab === tab.id
                ? 'bg-brand-600 text-white shadow-xs'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-200/80 bg-slate-50/75 text-slate-500 font-semibold uppercase tracking-wider text-[11px]">
                <th className="py-3 px-4">Payment Ref</th>
                <th className="py-3 px-4">External Txn</th>
                <th className="py-3 px-4">Invoice Ref</th>
                <th className="py-3 px-4">Customer</th>
                <th className="py-3 px-4">Amount</th>
                <th className="py-3 px-4">Gateway</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredItems.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50/60 transition-colors">
                  <td className="py-3 px-4 font-bold text-slate-900">{item.paymentRef}</td>
                  <td className="py-3 px-4 font-mono text-[11px] text-slate-600">{item.externalTxn}</td>
                  <td className="py-3 px-4">
                    {item.invoiceRef === 'UNASSIGNED' ? (
                      <span className="text-amber-600 font-semibold italic">Unassigned</span>
                    ) : (
                      <span className="font-semibold text-slate-800">{item.invoiceRef}</span>
                    )}
                  </td>
                  <td className="py-3 px-4 font-medium text-slate-700">{item.customer}</td>
                  <td className="py-3 px-4 font-bold text-slate-900">{item.amount}</td>
                  <td className="py-3 px-4 text-slate-600">{item.gateway}</td>
                  <td className="py-3 px-4">
                    <Badge
                      variant={
                        item.status === 'auto-reconciled' || item.status === 'matched'
                          ? 'success'
                          : item.status === 'exception'
                          ? 'danger'
                          : 'warning'
                      }
                      size="sm"
                    >
                      {item.status}
                    </Badge>
                  </td>
                  <td className="py-3 px-4 text-right">
                    {item.status === 'unmatched' && (
                      <Button
                        variant="primary"
                        size="sm"
                        className="h-7 text-[11px] px-2.5"
                        onClick={() => handleMatch(item.id)}
                      >
                        Match Transaction
                      </Button>
                    )}
                    {item.status === 'exception' && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-[11px] px-2.5 text-rose-600 hover:bg-rose-50"
                        onClick={() => setSelectedException(item)}
                      >
                        Review Exception
                      </Button>
                    )}
                    {(item.status === 'matched' || item.status === 'auto-reconciled') && (
                      <span className="text-[11px] text-emerald-600 font-medium">Reconciled ✓</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Exception Modal */}
      {selectedException && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedException(null)}
          title={`Reconciliation Exception: ${selectedException.paymentRef}`}
          description={`Gateway: ${selectedException.gateway} • Amount: ${selectedException.amount}`}
          size="md"
        >
          <div className="space-y-4 py-2 text-xs">
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-800 leading-relaxed">
              <p className="font-bold">Discrepancy Detail:</p>
              <p className="mt-1">{selectedException.discrepancyNote}</p>
              {selectedException.variance && (
                <p className="mt-2 font-semibold">
                  Detected Variance: <span className="font-mono">{selectedException.variance}</span>
                </p>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectedException(null)}
              >
                Dismiss
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  handleMatch(selectedException.id);
                  setSelectedException(null);
                }}
              >
                Accept Variance & Reconcile
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
