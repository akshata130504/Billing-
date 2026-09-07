import { useState, useMemo } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import {
  History,
  Search,
  Download,
  Eye,
  Lock,
} from 'lucide-react';

export interface AuditEntry {
  id: string;
  timestamp: string;
  actor: string;
  role: string;
  action: string;
  resource: string;
  resourceType: 'Invoice' | 'Subscription' | 'Quote' | 'Payment' | 'Customer' | 'System';
  ipAddress: string;
  status: 'success' | 'warning' | 'denied';
  beforeState?: Record<string, any>;
  afterState?: Record<string, any>;
}

const mockAuditLogs: AuditEntry[] = [
  {
    id: 'AUD-901',
    timestamp: '2026-09-07 14:32:10 IST',
    actor: 'Akshata R.',
    role: 'Billing Admin',
    action: 'INVOICE_VOIDED',
    resource: 'INV-2026-0082',
    resourceType: 'Invoice',
    ipAddress: '192.168.1.42',
    status: 'warning',
    beforeState: { status: 'issued', balance: '₹42,000.00', terms: 'Net 30' },
    afterState: { status: 'void', balance: '₹0.00', voidReason: 'Re-issued with updated GSTIN' },
  },
  {
    id: 'AUD-902',
    timestamp: '2026-09-07 13:15:22 IST',
    actor: 'Rahul Sharma',
    role: 'Account Exec',
    action: 'QUOTE_DISCOUNT_APPLIED',
    resource: 'QT-2026-0034',
    resourceType: 'Quote',
    ipAddress: '192.168.1.68',
    status: 'success',
    beforeState: { discountPct: 0, total: '₹1,20,000.00' },
    afterState: { discountPct: 30, total: '₹84,000.00', approvedBy: 'Akshata R.' },
  },
  {
    id: 'AUD-903',
    timestamp: '2026-09-07 11:04:19 IST',
    actor: 'System Automation Engine',
    role: 'Automated Worker',
    action: 'SUBSCRIPTION_PRORATED_UPGRADE',
    resource: 'SUB-2026-0418',
    resourceType: 'Subscription',
    ipAddress: '10.0.4.15',
    status: 'success',
    beforeState: { plan: 'Starter Monthly', seats: 5, unitPrice: '₹4,999.00' },
    afterState: { plan: 'Enterprise Scale', seats: 25, unitPrice: '₹19,999.00', prorationCredit: '₹2,450.00' },
  },
  {
    id: 'AUD-904',
    timestamp: '2026-09-07 09:40:02 IST',
    actor: 'Pooja Nair',
    role: 'Billing Specialist',
    action: 'PAYMENT_REFUND_EXECUTED',
    resource: 'PAY-2026-8920',
    resourceType: 'Payment',
    ipAddress: '192.168.1.77',
    status: 'warning',
    beforeState: { paymentStatus: 'settled', refunded: false },
    afterState: { paymentStatus: 'refunded', refundAmount: '₹18,500.00', gatewayRefundId: 'rfnd_3N8zKq' },
  },
  {
    id: 'AUD-905',
    timestamp: '2026-09-06 18:22:45 IST',
    actor: 'External Webhook (Razorpay)',
    role: 'Gateway Service',
    action: 'GATEWAY_PAYMENT_CAPTURED',
    resource: 'PAY-2026-8921',
    resourceType: 'Payment',
    ipAddress: '52.76.128.4',
    status: 'success',
    beforeState: { status: 'pending' },
    afterState: { status: 'captured', amount: '₹34,000.00', authCode: 'AUTH_99182' },
  },
  {
    id: 'AUD-906',
    timestamp: '2026-09-06 16:11:30 IST',
    actor: 'Unknown IP',
    role: 'Unauthenticated Request',
    action: 'ORG_SETTINGS_UPDATE_ATTEMPT',
    resource: 'ORGANIZATION_ROOT',
    resourceType: 'System',
    ipAddress: '203.0.113.195',
    status: 'denied',
    beforeState: { restricted: true },
    afterState: { blockedReason: 'Invalid CSRF token & 403 Forbidden' },
  },
];

export function AuditLogPage() {
  const { showToast } = useToast();
  const [logs] = useState<AuditEntry[]>(mockAuditLogs);
  const [selectedResourceType, setSelectedResourceType] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEntry, setSelectedEntry] = useState<AuditEntry | null>(null);

  const filteredLogs = useMemo(() => {
    return logs.filter((entry) => {
      const matchesType =
        selectedResourceType === 'all' || entry.resourceType === selectedResourceType;
      const matchesSearch =
        !searchQuery.trim() ||
        entry.action.toLowerCase().includes(searchQuery.toLowerCase()) ||
        entry.actor.toLowerCase().includes(searchQuery.toLowerCase()) ||
        entry.resource.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesType && matchesSearch;
    });
  }, [logs, selectedResourceType, searchQuery]);

  const handleExportCSV = () => {
    const headers = 'ID,Timestamp,Actor,Role,Action,Resource,ResourceType,Status,IPAddress\n';
    const rows = filteredLogs
      .map(
        (l) =>
          `"${l.id}","${l.timestamp}","${l.actor}","${l.role}","${l.action}","${l.resource}","${l.resourceType}","${l.status}","${l.ipAddress}"`
      )
      .join('\n');
    const blob = new Blob([headers + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `rooman_billing_audit_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('success', 'Export Complete', 'Exported immutable audit trail to CSV.');
  };

  const handleExportJSON = () => {
    const blob = new Blob([JSON.stringify(filteredLogs, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `rooman_billing_audit_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('success', 'Export Complete', 'Exported audit log events to JSON.');
  };

  const getStatusBadge = (status: AuditEntry['status']) => {
    switch (status) {
      case 'success':
        return <Badge variant="success" size="sm">Success</Badge>;
      case 'warning':
        return <Badge variant="warning" size="sm">Alert / Warning</Badge>;
      case 'denied':
        return <Badge variant="danger" size="sm">Access Denied</Badge>;
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
              SOC 2 / ISO Compliance
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <History className="w-6 h-6 text-brand-600" />
            Immutable Audit Trail
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Cryptographically sealed chronological log of all rate modifications, invoice voidings, discount approvals, and financial events.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<Download className="w-3.5 h-3.5" />}
            onClick={handleExportCSV}
          >
            Export CSV
          </Button>
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<Download className="w-3.5 h-3.5" />}
            onClick={handleExportJSON}
          >
            Export JSON
          </Button>
        </div>
      </div>

      {/* Security & Immutability Notice */}
      <div className="p-3.5 rounded-xl bg-slate-900 text-white flex items-center justify-between gap-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-white/10 text-emerald-400">
            <Lock className="w-4 h-4" />
          </div>
          <div>
            <p className="text-xs font-bold text-slate-100">
              Append-Only Financial Ledger Active
            </p>
            <p className="text-[11px] text-slate-400">
              Audit log entries are write-once and cannot be edited or deleted by any administrative account.
            </p>
          </div>
        </div>
        <span className="hidden sm:inline-flex text-[11px] font-mono text-emerald-400 font-bold bg-emerald-950/60 border border-emerald-800 px-2.5 py-1 rounded-lg">
          SHA-256 Validated
        </span>
      </div>

      {/* Filter and Search Bar */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            {/* Resource Type Filter */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 text-xs">
              {[
                { key: 'all', label: 'All Subsystems' },
                { key: 'Invoice', label: 'Invoices' },
                { key: 'Quote', label: 'Quotes' },
                { key: 'Subscription', label: 'Subscriptions' },
                { key: 'Payment', label: 'Payments' },
                { key: 'System', label: 'System' },
              ].map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setSelectedResourceType(tab.key)}
                  className={`px-3 py-1.5 rounded-lg font-medium whitespace-nowrap transition-colors cursor-pointer ${
                    selectedResourceType === tab.key
                      ? 'bg-brand-600 text-white shadow-xs'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Live Search */}
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search action, actor, resource..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 outline-none focus:bg-white transition-colors"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Audit Log Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200/80">
              <tr>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Actor</th>
                <th className="px-4 py-3">Action</th>
                <th className="px-4 py-3">Affected Resource</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">IP Address</th>
                <th className="px-4 py-3 text-right">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredLogs.map((entry) => (
                <tr key={entry.id} className="hover:bg-slate-50/70 transition-colors">
                  <td className="px-4 py-3 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                    {entry.timestamp}
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-bold text-slate-900">{entry.actor}</div>
                    <div className="text-[10px] text-slate-400">{entry.role}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono font-bold text-slate-800 text-[11px] bg-slate-100 px-1.5 py-0.5 rounded">
                      {entry.action}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-semibold text-slate-900">{entry.resource}</span>
                    <span className="text-[10px] text-slate-400 block">{entry.resourceType}</span>
                  </td>
                  <td className="px-4 py-3">
                    {getStatusBadge(entry.status)}
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-slate-500">
                    {entry.ipAddress}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      leadingIcon={<Eye className="w-3.5 h-3.5" />}
                      onClick={() => setSelectedEntry(entry)}
                    >
                      Diff
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Before / After State Diff Modal */}
      {selectedEntry && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedEntry(null)}
          title={`Audit State Diff: ${selectedEntry.action}`}
          size="lg"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-3 bg-slate-50 rounded-xl border border-slate-200">
              <div>
                <span className="text-slate-400 text-[10px] uppercase font-bold block">Log ID</span>
                <span className="font-mono font-bold text-slate-800">{selectedEntry.id}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] uppercase font-bold block">Actor</span>
                <span className="font-bold text-slate-800">{selectedEntry.actor}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] uppercase font-bold block">Resource</span>
                <span className="font-bold text-slate-800">{selectedEntry.resource}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] uppercase font-bold block">IP Origin</span>
                <span className="font-mono text-slate-800">{selectedEntry.ipAddress}</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Before State */}
              <div className="p-3 bg-rose-50/50 border border-rose-200 rounded-xl space-y-1.5">
                <span className="text-[11px] font-bold text-rose-700 uppercase tracking-wider block">
                  Prior State (Before Mutation)
                </span>
                <pre className="p-2.5 bg-white rounded-lg border border-rose-100 text-[11px] font-mono text-slate-800 overflow-x-auto">
                  {JSON.stringify(selectedEntry.beforeState || { empty: true }, null, 2)}
                </pre>
              </div>

              {/* After State */}
              <div className="p-3 bg-emerald-50/50 border border-emerald-200 rounded-xl space-y-1.5">
                <span className="text-[11px] font-bold text-emerald-700 uppercase tracking-wider block">
                  New State (Committed State)
                </span>
                <pre className="p-2.5 bg-white rounded-lg border border-emerald-100 text-[11px] font-mono text-slate-800 overflow-x-auto">
                  {JSON.stringify(selectedEntry.afterState || { empty: true }, null, 2)}
                </pre>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button variant="primary" size="sm" onClick={() => setSelectedEntry(null)}>
                Close Inspector
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
