import { useState } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import {
  Download,
  Search,
  ArrowRight,
} from 'lucide-react';

interface AuditRecord {
  id: string;
  user: string;
  action: string;
  module: 'Invoices' | 'Payments' | 'Subscriptions' | 'Quotes' | 'System';
  entity: string;
  previousValue: string;
  newValue: string;
  timestamp: string;
  source: string;
}

const mockAuditRecords: AuditRecord[] = [
  {
    id: 'AUD-8801',
    user: 'Akshata Rathod',
    action: 'Modified Payment Terms',
    module: 'Invoices',
    entity: 'Invoice #INV-2026-0087',
    previousValue: 'Due upon Receipt (0 Days)',
    newValue: 'Net 30 Days',
    timestamp: 'Today, 02:45 PM',
    source: 'Web Workstation (192.168.1.42)',
  },
  {
    id: 'AUD-8802',
    user: 'Finance Manager (Approval)',
    action: 'Authorized Refund',
    module: 'Payments',
    entity: 'Refund #RF-1024',
    previousValue: 'Status: Pending Review',
    newValue: 'Status: Settled ($2,450.00)',
    timestamp: 'Today, 01:15 PM',
    source: 'Control Center Approvals',
  },
  {
    id: 'AUD-8803',
    user: 'System Automation',
    action: 'Executed Payment Retry',
    module: 'Payments',
    entity: 'Subscription #SUB-9021',
    previousValue: 'Retry Count: 1',
    newValue: 'Retry Count: 2 (Success)',
    timestamp: 'Today, 11:30 AM',
    source: 'Cron Dunning Scheduler',
  },
  {
    id: 'AUD-8804',
    user: 'Sanjay Rao',
    action: 'Overrode Price Tier',
    module: 'Quotes',
    entity: 'Quote #Q-7019',
    previousValue: 'Tier Bracket Standard ($0.05/GB)',
    newValue: 'Discounted Bracket ($0.035/GB)',
    timestamp: 'Yesterday, 04:12 PM',
    source: 'CPQ Pricing Engine',
  },
  {
    id: 'AUD-8805',
    user: 'Security Admin',
    action: 'Rotated API Webhook Secret',
    module: 'System',
    entity: 'Stripe Webhook #whsec_live',
    previousValue: 'Secret hash: ••••4920',
    newValue: 'Secret hash: ••••8819',
    timestamp: 'Sep 05, 2026',
    source: 'System Integrations',
  },
  {
    id: 'AUD-8806',
    user: 'Akshata Rathod',
    action: 'Added Seat Allowance',
    module: 'Subscriptions',
    entity: 'Account: Acme Corp (#SUB-8012)',
    previousValue: 'Allocated Seats: 25',
    newValue: 'Allocated Seats: 35 (+10)',
    timestamp: 'Sep 04, 2026',
    source: 'Web Workstation',
  },
];

export function AuditLogPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedModule, setSelectedModule] = useState<string>('all');
  const { showToast } = useToast();

  const handleExport = (format: 'CSV' | 'JSON') => {
    showToast('info', 'Export Started', `Downloading audit trail export as ${format}.`);
  };

  const filteredRecords = mockAuditRecords.filter((rec) => {
    const matchesModule = selectedModule === 'all' || rec.module === selectedModule;
    const q = searchQuery.toLowerCase();
    const matchesSearch =
      !q ||
      rec.user.toLowerCase().includes(q) ||
      rec.action.toLowerCase().includes(q) ||
      rec.entity.toLowerCase().includes(q) ||
      rec.previousValue.toLowerCase().includes(q) ||
      rec.newValue.toLowerCase().includes(q);
    return matchesModule && matchesSearch;
  });

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
              Compliance & Security
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Audit Log
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Immutable chronological audit record of critical state transitions, price modifications, invoice adjustments, permission updates, and automated system actions.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<Download className="w-3.5 h-3.5" />}
            onClick={() => handleExport('CSV')}
          >
            Export CSV
          </Button>
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<Download className="w-3.5 h-3.5" />}
            onClick={() => handleExport('JSON')}
          >
            Export JSON
          </Button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <Card>
        <CardContent className="p-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search user, entity, action, or value..."
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl outline-none focus:border-brand-500 transition-colors"
            />
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto text-xs">
            {['all', 'Invoices', 'Payments', 'Subscriptions', 'Quotes', 'System'].map((m) => (
              <button
                key={m}
                onClick={() => setSelectedModule(m)}
                className={`px-3 py-1.5 rounded-xl font-medium transition-colors cursor-pointer capitalize ${
                  selectedModule === m
                    ? 'bg-brand-600 text-white shadow-xs'
                    : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Audit Log Table */}
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-200/80 bg-slate-50/75 text-slate-500 font-semibold uppercase tracking-wider text-[11px]">
                <th className="py-3 px-4">User & Action</th>
                <th className="py-3 px-4">Module</th>
                <th className="py-3 px-4">Target Entity</th>
                <th className="py-3 px-4">State Diff (Before → After)</th>
                <th className="py-3 px-4">Source / Origin</th>
                <th className="py-3 px-4 text-right">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredRecords.map((rec) => (
                <tr key={rec.id} className="hover:bg-slate-50/60 transition-colors">
                  <td className="py-3.5 px-4">
                    <p className="font-bold text-slate-900">{rec.user}</p>
                    <p className="text-[11px] text-slate-500 mt-0.5">{rec.action}</p>
                  </td>
                  <td className="py-3.5 px-4">
                    <Badge variant="neutral" size="sm">
                      {rec.module}
                    </Badge>
                  </td>
                  <td className="py-3.5 px-4 font-semibold text-slate-800">
                    {rec.entity}
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="flex items-center gap-1.5 text-[11px]">
                      <span className="text-rose-600 bg-rose-50 px-1.5 py-0.5 rounded line-through">
                        {rec.previousValue}
                      </span>
                      <ArrowRight className="w-3 h-3 text-slate-400 shrink-0" />
                      <span className="text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded font-medium">
                        {rec.newValue}
                      </span>
                    </div>
                  </td>
                  <td className="py-3.5 px-4 text-slate-500 font-mono text-[11px]">
                    {rec.source}
                  </td>
                  <td className="py-3.5 px-4 text-right text-slate-500">
                    {rec.timestamp}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
