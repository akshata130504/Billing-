import { useState } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import {
  Eye,
  FileCheck,
  Percent,
  CreditCard,
  Sliders,
  Repeat,
} from 'lucide-react';

interface ApprovalRequest {
  id: string;
  type: 'Quote Approval' | 'Large Discount' | 'Refund Request' | 'Price Override' | 'Subscription Change';
  title: string;
  requestedBy: string;
  amount: string;
  date: string;
  status: 'pending' | 'approved' | 'rejected';
  reason: string;
  impactDetails: string;
}

const initialApprovals: ApprovalRequest[] = [
  {
    id: 'APR-1041',
    type: 'Quote Approval',
    title: 'Enterprise CPQ Contract (Vanguard Tech)',
    requestedBy: 'Akash Verma (Sales Dir)',
    amount: '$94,000.00 / yr',
    date: 'Today, 11:20 AM',
    status: 'pending',
    reason: 'Multi-year commitment with 20% ramp pricing waiver.',
    impactDetails: 'Base ARR $117,500 discounted to $94,000 with 3-year upfront commitment.',
  },
  {
    id: 'APR-1042',
    type: 'Large Discount',
    title: '25% Non-Profit Waiver (Global Care Trust)',
    requestedBy: 'Meera Sen (Account Exec)',
    amount: '$12,500.00',
    date: 'Today, 09:45 AM',
    status: 'pending',
    reason: 'Exceeds standard 15% sales rep discretionary discount threshold.',
    impactDetails: 'Applies to 50 user seat licenses for 12 months.',
  },
  {
    id: 'APR-1043',
    type: 'Refund Request',
    title: 'Partial Refund for Double Gateway Charge #RF-209',
    requestedBy: 'Support Desk (Auto-Flag)',
    amount: '$2,450.00',
    date: 'Yesterday, 04:30 PM',
    status: 'pending',
    reason: 'Customer charged twice via Stripe webhook race condition.',
    impactDetails: 'Original transaction #txn_99014 verified duplicate in ledger.',
  },
  {
    id: 'APR-1044',
    type: 'Price Override',
    title: 'Custom Per-Gigabyte Metering Rate ($0.035 vs $0.050)',
    requestedBy: 'Sanjay Rao (Solutions Architect)',
    amount: 'Estimated $8,400/mo',
    date: 'Sep 05, 2026',
    status: 'pending',
    reason: 'High-volume tier commitment over 250 TB monthly egress.',
    impactDetails: 'Custom billing rule overrides default catalog tiered bracket.',
  },
  {
    id: 'APR-1045',
    type: 'Subscription Change',
    title: 'Mid-Cycle Plan Downgrade with Credit Freeze',
    requestedBy: 'Pooja Nair (Billing Ops)',
    amount: '$4,100.00 Credit',
    date: 'Sep 04, 2026',
    status: 'approved',
    reason: 'Downgrade from Enterprise to Growth per mutual contractual agreement.',
    impactDetails: 'Approved by VP of Finance. Credit memo #CM-810 issued.',
  },
];

export function ApprovalCenterPage() {
  const [requests, setRequests] = useState<ApprovalRequest[]>(initialApprovals);
  const [selectedRequest, setSelectedRequest] = useState<ApprovalRequest | null>(null);
  const [activeFilter, setActiveFilter] = useState<'all' | 'pending' | 'approved' | 'rejected'>('all');
  const { showToast } = useToast();

  const handleStatusChange = (id: string, newStatus: 'approved' | 'rejected') => {
    setRequests((prev) =>
      prev.map((r) => (r.id === id ? { ...r, status: newStatus } : r))
    );
    showToast(
      newStatus === 'approved' ? 'success' : 'info',
      `Request ${newStatus === 'approved' ? 'Approved' : 'Rejected'}`,
      `Request ${id} marked as ${newStatus}.`
    );
    if (selectedRequest?.id === id) {
      setSelectedRequest((prev) => (prev ? { ...prev, status: newStatus } : null));
    }
  };

  const filteredRequests = requests.filter(
    (r) => activeFilter === 'all' || r.status === activeFilter
  );

  const pendingCount = requests.filter((r) => r.status === 'pending').length;

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
              Authorization Inbox
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Approval Center
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Single centralized authorization inbox for financial approvals: high discounts, quote commitments, refund authorizations, and custom pricing overrides.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant={pendingCount > 0 ? 'warning' : 'success'} size="md">
            {pendingCount} Pending Authorization
          </Badge>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2">
        {(['all', 'pending', 'approved', 'rejected'] as const).map((filter) => (
          <button
            key={filter}
            onClick={() => setActiveFilter(filter)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium capitalize transition-colors cursor-pointer ${
              activeFilter === filter
                ? 'bg-brand-600 text-white shadow-xs'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            {filter} ({filter === 'all' ? requests.length : requests.filter((r) => r.status === filter).length})
          </button>
        ))}
      </div>

      {/* Approvals Table Card */}
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-200/80 bg-slate-50/75 text-slate-500 font-semibold uppercase tracking-wider text-[11px]">
                <th className="py-3 px-4">Request & Type</th>
                <th className="py-3 px-4">Requested By</th>
                <th className="py-3 px-4">Amount / Impact</th>
                <th className="py-3 px-4">Date</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredRequests.map((req) => (
                <tr key={req.id} className="hover:bg-slate-50/60 transition-colors">
                  <td className="py-3.5 px-4">
                    <div className="flex items-center gap-2.5">
                      <div className="p-2 rounded-lg bg-slate-100 text-slate-600 shrink-0">
                        {req.type === 'Quote Approval' && <FileCheck className="w-4 h-4 text-brand-600" />}
                        {req.type === 'Large Discount' && <Percent className="w-4 h-4 text-amber-600" />}
                        {req.type === 'Refund Request' && <CreditCard className="w-4 h-4 text-rose-600" />}
                        {req.type === 'Price Override' && <Sliders className="w-4 h-4 text-purple-600" />}
                        {req.type === 'Subscription Change' && <Repeat className="w-4 h-4 text-teal-600" />}
                      </div>
                      <div>
                        <p className="font-bold text-slate-900">{req.title}</p>
                        <p className="text-[11px] text-slate-500">{req.id} • {req.type}</p>
                      </div>
                    </div>
                  </td>
                  <td className="py-3.5 px-4 font-medium text-slate-700">
                    {req.requestedBy}
                  </td>
                  <td className="py-3.5 px-4 font-bold text-slate-900">
                    {req.amount}
                  </td>
                  <td className="py-3.5 px-4 text-slate-500">
                    {req.date}
                  </td>
                  <td className="py-3.5 px-4">
                    <Badge
                      variant={
                        req.status === 'approved'
                          ? 'success'
                          : req.status === 'rejected'
                          ? 'danger'
                          : 'warning'
                      }
                      size="sm"
                    >
                      {req.status}
                    </Badge>
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        onClick={() => setSelectedRequest(req)}
                        className="p-1.5 rounded-lg text-slate-500 hover:text-brand-600 hover:bg-brand-50 transition-colors"
                        title="View Details"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      {req.status === 'pending' && (
                        <>
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => handleStatusChange(req.id, 'approved')}
                            className="bg-emerald-600 hover:bg-emerald-700 h-7 text-[11px] px-2.5"
                          >
                            Approve
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleStatusChange(req.id, 'rejected')}
                            className="text-rose-600 hover:bg-rose-50 h-7 text-[11px] px-2.5"
                          >
                            Reject
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Details Modal */}
      {selectedRequest && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedRequest(null)}
          title={`Approval Details: ${selectedRequest.id}`}
          description={selectedRequest.title}
          size="md"
        >
          <div className="space-y-4 py-2 text-xs">
            <div className="grid grid-cols-2 gap-3 p-3 rounded-xl bg-slate-50 border border-slate-200/80">
              <div>
                <p className="text-slate-400 font-medium">Request Type</p>
                <p className="text-slate-900 font-bold mt-0.5">{selectedRequest.type}</p>
              </div>
              <div>
                <p className="text-slate-400 font-medium">Financial Impact</p>
                <p className="text-slate-900 font-bold mt-0.5">{selectedRequest.amount}</p>
              </div>
              <div>
                <p className="text-slate-400 font-medium">Requested By</p>
                <p className="text-slate-900 font-semibold mt-0.5">{selectedRequest.requestedBy}</p>
              </div>
              <div>
                <p className="text-slate-400 font-medium">Status</p>
                <Badge
                  variant={
                    selectedRequest.status === 'approved'
                      ? 'success'
                      : selectedRequest.status === 'rejected'
                      ? 'danger'
                      : 'warning'
                  }
                  size="sm"
                >
                  {selectedRequest.status}
                </Badge>
              </div>
            </div>

            <div>
              <h4 className="font-bold text-slate-800 uppercase tracking-wider text-[11px] mb-1">
                Justification & Reason
              </h4>
              <p className="text-slate-600 bg-slate-50 p-2.5 rounded-lg border border-slate-200/60">
                {selectedRequest.reason}
              </p>
            </div>

            <div>
              <h4 className="font-bold text-slate-800 uppercase tracking-wider text-[11px] mb-1">
                Policy & Contract Scope
              </h4>
              <p className="text-slate-600 bg-slate-50 p-2.5 rounded-lg border border-slate-200/60">
                {selectedRequest.impactDetails}
              </p>
            </div>

            {selectedRequest.status === 'pending' && (
              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleStatusChange(selectedRequest.id, 'rejected')}
                  className="text-rose-600 hover:bg-rose-50"
                >
                  Reject Request
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => handleStatusChange(selectedRequest.id, 'approved')}
                  className="bg-emerald-600 hover:bg-emerald-700"
                >
                  Authorize & Approve
                </Button>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
