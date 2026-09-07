import { useState, useMemo } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import {
  ArrowLeftRight,
  ArrowRight,
  RefreshCw,
  ShieldCheck,
  CreditCard,
  Building2,
  FileText,
  UserCheck,
} from 'lucide-react';

export type ReconStatus = 'auto-reconciled' | 'matched' | 'unmatched' | 'exception';

export interface ReconciliationRecord {
  id: string;
  paymentRef: string;
  externalTxn: string;
  invoiceRef: string;
  customer: string;
  amount: string;
  gateway: 'Razorpay' | 'Stripe' | 'HDFC Wire' | 'ICICI ACH';
  status: ReconStatus;
  variance?: string;
  discrepancyNote?: string;
  date: string;
}

const initialReconciliations: ReconciliationRecord[] = [
  {
    id: 'REC-501',
    paymentRef: 'PAY-2026-8921',
    externalTxn: 'pay_N9m0Lq3x89vB',
    invoiceRef: 'INV-2026-0089',
    customer: 'Acme Cloud Dynamics',
    amount: '₹34,000.00',
    gateway: 'Razorpay',
    status: 'auto-reconciled',
    date: 'Sep 7, 2026',
  },
  {
    id: 'REC-502',
    paymentRef: 'PAY-2026-8922',
    externalTxn: 'ch_3N8zKq2eZvKYlo2C',
    invoiceRef: 'INV-2026-0088',
    customer: 'Solaria Robotics Corp',
    amount: '₹18,500.00',
    gateway: 'Stripe',
    status: 'matched',
    date: 'Sep 6, 2026',
  },
  {
    id: 'REC-503',
    paymentRef: 'PAY-2026-8923',
    externalTxn: 'UTR_HDFC002938102',
    invoiceRef: 'INV-2026-0087',
    customer: 'Hyperion FinTech Ltd',
    amount: '₹42,000.00',
    gateway: 'HDFC Wire',
    status: 'exception',
    variance: '+₹500.00',
    discrepancyNote: 'Customer added wire bank transfer fee allowance of ₹500 above invoice total.',
    date: 'Sep 6, 2026',
  },
  {
    id: 'REC-504',
    paymentRef: 'PAY-2026-8924',
    externalTxn: 'pay_P1k8Jq4w12zC',
    invoiceRef: 'Pending Match',
    customer: 'Unidentified Depositor',
    amount: '₹15,000.00',
    gateway: 'Razorpay',
    status: 'unmatched',
    discrepancyNote: 'Gateway direct deposit received without customer metadata reference.',
    date: 'Sep 5, 2026',
  },
  {
    id: 'REC-505',
    paymentRef: 'PAY-2026-8925',
    externalTxn: 'ACH_ICICI_889210',
    invoiceRef: 'INV-2026-0084',
    customer: 'Vanguard Biometrics',
    amount: '₹84,000.00',
    gateway: 'ICICI ACH',
    status: 'auto-reconciled',
    date: 'Sep 4, 2026',
  },
  {
    id: 'REC-506',
    paymentRef: 'PAY-2026-8926',
    externalTxn: 'UTR_HDFC002939881',
    invoiceRef: 'INV-2026-0083',
    customer: 'Nexus Global Logistics',
    amount: '₹26,750.00',
    gateway: 'HDFC Wire',
    status: 'exception',
    variance: '-₹1,200.00',
    discrepancyNote: 'Client deducted TDS (Tax Deducted at Source) without attaching 16A TDS certificate.',
    date: 'Sep 3, 2026',
  },
];

export function ReconciliationPage() {
  const { showToast } = useToast();
  const [records, setRecords] = useState<ReconciliationRecord[]>(initialReconciliations);
  const [statusFilter, setStatusFilter] = useState<'all' | ReconStatus>('all');
  const [isReconciling, setIsReconciling] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<ReconciliationRecord | null>(null);

  const filteredRecords = useMemo(() => {
    if (statusFilter === 'all') return records;
    return records.filter((r) => r.status === statusFilter);
  }, [records, statusFilter]);

  const stats = useMemo(() => {
    const auto = records.filter((r) => r.status === 'auto-reconciled').length;
    const matched = records.filter((r) => r.status === 'matched').length;
    const unmatched = records.filter((r) => r.status === 'unmatched').length;
    const exceptions = records.filter((r) => r.status === 'exception').length;
    return { auto, matched, unmatched, exceptions, total: records.length };
  }, [records]);

  const handleRunReconciliation = () => {
    setIsReconciling(true);
    setTimeout(() => {
      setIsReconciling(false);
      setRecords((prev) =>
        prev.map((r) => (r.status === 'unmatched' ? { ...r, status: 'matched', customer: 'Resolved Customer (Matched)' } : r))
      );
      showToast('success', 'Reconciliation Completed', 'All settlement batches matched against ledger.');
    }, 750);
  };

  const handleManualMatch = (id: string) => {
    setRecords((prev) =>
      prev.map((r) =>
        r.id === id
          ? { ...r, status: 'matched', invoiceRef: 'INV-2026-0092', customer: 'Orbit Retail India' }
          : r
      )
    );
    setSelectedRecord(null);
    showToast('success', 'Manual Match Saved', 'Transaction linked to Invoice #INV-2026-0092.');
  };

  const handleResolveException = (id: string) => {
    setRecords((prev) =>
      prev.map((r) =>
        r.id === id
          ? { ...r, status: 'matched', discrepancyNote: 'Resolved via TDS adjustment ledger entry' }
          : r
      )
    );
    setSelectedRecord(null);
    showToast('success', 'Exception Resolved', 'Adjustment entry posted to ledger.');
  };

  const getStatusBadge = (status: ReconStatus) => {
    switch (status) {
      case 'auto-reconciled':
        return <Badge variant="success" size="sm">Auto-Reconciled</Badge>;
      case 'matched':
        return <Badge variant="primary" size="sm">Matched</Badge>;
      case 'unmatched':
        return <Badge variant="warning" size="sm">Unmatched</Badge>;
      case 'exception':
        return <Badge variant="danger" size="sm">Exception</Badge>;
    }
  };

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
              Financial Integrity
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <ArrowLeftRight className="w-6 h-6 text-brand-600" />
            Reconciliation Workspace
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Match bank transactions, gateway payouts, and external provider settlements against issued invoices and customer balances.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button
            variant="primary"
            size="sm"
            isLoading={isReconciling}
            leadingIcon={<RefreshCw className="w-3.5 h-3.5" />}
            onClick={handleRunReconciliation}
          >
            Run Auto-Reconciliation
          </Button>
        </div>
      </div>

      {/* Matching Flow Banner */}
      <Card className="bg-gradient-to-r from-blue-50/70 via-slate-50 to-indigo-50/70 border-blue-200/70">
        <CardContent className="p-4 sm:p-5">
          <div className="flex items-center justify-between gap-2 overflow-x-auto pb-1 text-xs">
            <div className="flex items-center gap-2 shrink-0">
              <span className="p-2 rounded-lg bg-white border border-blue-200 text-brand-600 shadow-2xs">
                <CreditCard className="w-4 h-4" />
              </span>
              <div>
                <p className="font-bold text-slate-900">1. Inward Payment</p>
                <p className="text-[10px] text-slate-500">Gateway or Bank UTR</p>
              </div>
            </div>

            <ArrowRight className="w-4 h-4 text-slate-400 shrink-0" />

            <div className="flex items-center gap-2 shrink-0">
              <span className="p-2 rounded-lg bg-white border border-blue-200 text-brand-600 shadow-2xs">
                <Building2 className="w-4 h-4" />
              </span>
              <div>
                <p className="font-bold text-slate-900">2. External Txn</p>
                <p className="text-[10px] text-slate-500">Bank Statement / Settlement</p>
              </div>
            </div>

            <ArrowRight className="w-4 h-4 text-slate-400 shrink-0" />

            <div className="flex items-center gap-2 shrink-0">
              <span className="p-2 rounded-lg bg-white border border-blue-200 text-brand-600 shadow-2xs">
                <FileText className="w-4 h-4" />
              </span>
              <div>
                <p className="font-bold text-slate-900">3. Invoice</p>
                <p className="text-[10px] text-slate-500">Matched Open AR</p>
              </div>
            </div>

            <ArrowRight className="w-4 h-4 text-slate-400 shrink-0" />

            <div className="flex items-center gap-2 shrink-0">
              <span className="p-2 rounded-lg bg-white border border-blue-200 text-brand-600 shadow-2xs">
                <UserCheck className="w-4 h-4" />
              </span>
              <div>
                <p className="font-bold text-slate-900">4. Customer</p>
                <p className="text-[10px] text-slate-500">Credit Ledger Offset</p>
              </div>
            </div>

            <ArrowRight className="w-4 h-4 text-slate-400 shrink-0" />

            <div className="flex items-center gap-2 shrink-0">
              <span className="p-2 rounded-lg bg-emerald-500 text-white shadow-2xs">
                <ShieldCheck className="w-4 h-4" />
              </span>
              <div>
                <p className="font-bold text-emerald-900">5. Reconciled</p>
                <p className="text-[10px] text-emerald-700">Audit Proof Logged</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Metric Counters */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
        <div
          onClick={() => setStatusFilter('auto-reconciled')}
          className="p-3.5 bg-white rounded-xl border border-slate-200/90 shadow-2xs cursor-pointer hover:border-emerald-300"
        >
          <span className="text-xs text-slate-500 font-medium">Auto-Reconciled</span>
          <p className="text-xl font-bold text-emerald-600 mt-1">{stats.auto}</p>
          <span className="text-[10px] text-slate-400">100% matched via webhook</span>
        </div>
        <div
          onClick={() => setStatusFilter('matched')}
          className="p-3.5 bg-white rounded-xl border border-slate-200/90 shadow-2xs cursor-pointer hover:border-blue-300"
        >
          <span className="text-xs text-slate-500 font-medium">Manual Matched</span>
          <p className="text-xl font-bold text-brand-600 mt-1">{stats.matched}</p>
          <span className="text-[10px] text-slate-400">Audited & approved</span>
        </div>
        <div
          onClick={() => setStatusFilter('unmatched')}
          className="p-3.5 bg-white rounded-xl border border-slate-200/90 shadow-2xs cursor-pointer hover:border-amber-300"
        >
          <span className="text-xs text-slate-500 font-medium">Unmatched Records</span>
          <p className="text-xl font-bold text-amber-600 mt-1">{stats.unmatched}</p>
          <span className="text-[10px] text-slate-400">Pending customer link</span>
        </div>
        <div
          onClick={() => setStatusFilter('exception')}
          className="p-3.5 bg-white rounded-xl border border-slate-200/90 shadow-2xs cursor-pointer hover:border-rose-300"
        >
          <span className="text-xs text-slate-500 font-medium">Discrepancy Exceptions</span>
          <p className="text-xl font-bold text-rose-600 mt-1">{stats.exceptions}</p>
          <span className="text-[10px] text-slate-400">Fee variance or TDS notes</span>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-slate-200/90">
        {[
          { key: 'all', label: `All Transactions (${stats.total})` },
          { key: 'auto-reconciled', label: `Auto-Reconciled (${stats.auto})` },
          { key: 'matched', label: `Matched (${stats.matched})` },
          { key: 'unmatched', label: `Unmatched (${stats.unmatched})` },
          { key: 'exception', label: `Exceptions (${stats.exceptions})` },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setStatusFilter(tab.key as typeof statusFilter)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer ${
              statusFilter === tab.key
                ? 'bg-slate-900 text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Records Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200/80">
              <tr>
                <th className="px-4 py-3">Internal Ref</th>
                <th className="px-4 py-3">Gateway / Ext Txn</th>
                <th className="px-4 py-3">Invoice & Customer</th>
                <th className="px-4 py-3 text-right">Amount</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredRecords.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50/70 transition-colors">
                  <td className="px-4 py-3 font-mono font-bold text-slate-700">
                    <div>{item.paymentRef}</div>
                    <div className="text-[10px] text-slate-400 font-normal">{item.date}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-semibold text-slate-900 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-brand-500" />
                      {item.gateway}
                    </div>
                    <div className="text-[11px] font-mono text-slate-500 truncate max-w-[170px]">
                      {item.externalTxn}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-bold text-slate-900">{item.customer}</div>
                    <div className="text-[11px] text-slate-500">{item.invoiceRef}</div>
                  </td>
                  <td className="px-4 py-3 text-right font-bold text-slate-900 tabular-nums">
                    {item.amount}
                    {item.variance && (
                      <span className="block text-[10px] text-rose-600 font-medium">
                        Var: {item.variance}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {getStatusBadge(item.status)}
                    {item.discrepancyNote && (
                      <span className="block text-[10px] text-slate-500 truncate max-w-[180px] mt-0.5" title={item.discrepancyNote}>
                        {item.discrepancyNote}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setSelectedRecord(item)}
                    >
                      Inspect
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Inspect Modal */}
      {selectedRecord && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedRecord(null)}
          title={`Reconciliation Record: ${selectedRecord.paymentRef}`}
          size="lg"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3 p-3.5 bg-slate-50 rounded-xl border border-slate-200">
              <div>
                <span className="text-slate-500 block font-medium">External Gateway</span>
                <span className="font-bold text-slate-900">{selectedRecord.gateway}</span>
              </div>
              <div>
                <span className="text-slate-500 block font-medium">Gateway Txn ID</span>
                <span className="font-mono text-slate-800">{selectedRecord.externalTxn}</span>
              </div>
              <div>
                <span className="text-slate-500 block font-medium">Customer Account</span>
                <span className="font-bold text-slate-900">{selectedRecord.customer}</span>
              </div>
              <div>
                <span className="text-slate-500 block font-medium">Matched Invoice</span>
                <span className="font-bold text-slate-900">{selectedRecord.invoiceRef}</span>
              </div>
              <div>
                <span className="text-slate-500 block font-medium">Transaction Amount</span>
                <span className="font-bold text-slate-900 text-sm tabular-nums">
                  {selectedRecord.amount}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block font-medium">Reconciliation State</span>
                <div>{getStatusBadge(selectedRecord.status)}</div>
              </div>
            </div>

            {selectedRecord.discrepancyNote && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-900">
                <span className="font-bold block mb-0.5">Discrepancy Analysis:</span>
                {selectedRecord.discrepancyNote}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setSelectedRecord(null)}>
                Close
              </Button>
              {selectedRecord.status === 'unmatched' && (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => handleManualMatch(selectedRecord.id)}
                >
                  Link to Invoice
                </Button>
              )}
              {selectedRecord.status === 'exception' && (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => handleResolveException(selectedRecord.id)}
                >
                  Post Ledger Adjustment
                </Button>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
