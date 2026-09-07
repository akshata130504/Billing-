import { useState, useMemo } from 'react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import {
  FileCheck,
  CheckCircle2,
  Clock,
  User,
  Percent,
  Receipt,
  Tag,
  ShieldCheck,
  Eye,
} from 'lucide-react';

export type ApprovalType = 'quote_commitment' | 'high_discount' | 'refund_authorization' | 'price_override';
export type ApprovalStatus = 'pending' | 'approved' | 'rejected';

export interface ApprovalRequest {
  id: string;
  type: ApprovalType;
  title: string;
  requester: string;
  role: string;
  customer: string;
  amount: string;
  originalAmount?: string;
  discountPercentage?: string;
  justification: string;
  requestedAt: string;
  status: ApprovalStatus;
  reviewedBy?: string;
  reviewedAt?: string;
}

const initialApprovals: ApprovalRequest[] = [
  {
    id: 'APR-2026-0081',
    type: 'high_discount',
    title: '30% Annual Commitment Discount for Enterprise Plan',
    requester: 'Rahul Sharma',
    role: 'Account Executive',
    customer: 'Acme Cloud Dynamics',
    amount: '₹84,000.00 / yr',
    originalAmount: '₹1,20,000.00 / yr',
    discountPercentage: '30%',
    justification: 'Customer is committing to a 3-year multi-tenant rollout with 50 seats. Standard VP discount limit is 20%.',
    requestedAt: '2 hours ago',
    status: 'pending',
  },
  {
    id: 'APR-2026-0082',
    type: 'refund_authorization',
    title: 'Full Refund Authorization for Duplicate Mandate Debit',
    requester: 'Pooja Nair',
    role: 'Billing Specialist',
    customer: 'Solaria Robotics Corp',
    amount: '₹18,500.00',
    justification: 'Gateway webhook timed out causing customer to re-attempt checkout. Customer charged twice in error.',
    requestedAt: '4 hours ago',
    status: 'pending',
  },
  {
    id: 'APR-2026-0083',
    type: 'quote_commitment',
    title: 'Custom Payment Terms: Net-60 Extension',
    requester: 'Siddharth Roy',
    role: 'Enterprise Director',
    customer: 'Vanguard Biometrics',
    amount: '₹2,40,000.00',
    justification: 'Government vendor security clearance requires extended invoice settlement cycle from standard Net 30 to Net 60.',
    requestedAt: 'Yesterday',
    status: 'pending',
  },
  {
    id: 'APR-2026-0084',
    type: 'price_override',
    title: 'Custom Per-Unit API Metering Price Override',
    requester: 'Neha Gupta',
    role: 'Sales Engineer',
    customer: 'Hyperion FinTech Ltd',
    amount: '₹0.08 / event',
    originalAmount: '₹0.15 / event',
    discountPercentage: '46%',
    justification: 'Scale customer projecting >10M monthly meter telemetry events. Custom bracket approved by Product VP.',
    requestedAt: '2 days ago',
    status: 'pending',
  },
  {
    id: 'APR-2026-0079',
    type: 'high_discount',
    title: 'Early Bird 25% Discount for Scale Migration',
    requester: 'Rahul Sharma',
    role: 'Account Executive',
    customer: 'Apex Global Logistics',
    amount: '₹54,000.00',
    originalAmount: '₹72,000.00',
    discountPercentage: '25%',
    justification: 'Competitor replacement opportunity. Migration completed.',
    requestedAt: '3 days ago',
    status: 'approved',
    reviewedBy: 'Akshata R. (Admin)',
    reviewedAt: '2 days ago',
  },
  {
    id: 'APR-2026-0078',
    type: 'refund_authorization',
    title: 'Goodwill Credit Note Exception',
    requester: 'Pooja Nair',
    role: 'Billing Specialist',
    customer: 'Zeta Health Systems',
    amount: '₹45,000.00',
    justification: 'Service downtime compensation request exceeding Tier 1 support limits.',
    requestedAt: '4 days ago',
    status: 'rejected',
    reviewedBy: 'Akshata R. (Admin)',
    reviewedAt: '3 days ago',
  },
];

export function ApprovalCenterPage() {
  const { showToast } = useToast();
  const [approvals, setApprovals] = useState<ApprovalRequest[]>(initialApprovals);
  const [statusFilter, setStatusFilter] = useState<'all' | ApprovalStatus>('pending');
  const [selectedApproval, setSelectedApproval] = useState<ApprovalRequest | null>(null);

  const filteredApprovals = useMemo(() => {
    return approvals.filter((item) => {
      if (statusFilter === 'all') return true;
      return item.status === statusFilter;
    });
  }, [approvals, statusFilter]);

  const pendingCount = useMemo(() => {
    return approvals.filter((a) => a.status === 'pending').length;
  }, [approvals]);

  const handleApprove = (id: string, customer: string) => {
    setApprovals((prev) =>
      prev.map((item) =>
        item.id === id
          ? { ...item, status: 'approved', reviewedBy: 'Akshata R. (Admin)', reviewedAt: 'Just now' }
          : item
      )
    );
    setSelectedApproval(null);
    showToast('success', 'Request Approved', `Authorized billing request for ${customer}.`);
  };

  const handleReject = (id: string, customer: string) => {
    setApprovals((prev) =>
      prev.map((item) =>
        item.id === id
          ? { ...item, status: 'rejected', reviewedBy: 'Akshata R. (Admin)', reviewedAt: 'Just now' }
          : item
      )
    );
    setSelectedApproval(null);
    showToast('info', 'Request Rejected', `Declined billing request for ${customer}.`);
  };

  const getTypeBadge = (type: ApprovalType) => {
    switch (type) {
      case 'high_discount':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
            <Percent className="w-3 h-3" />
            High Discount
          </span>
        );
      case 'refund_authorization':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
            <Receipt className="w-3 h-3" />
            Refund Authorization
          </span>
        );
      case 'quote_commitment':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
            <FileCheck className="w-3 h-3" />
            Quote Commitment
          </span>
        );
      case 'price_override':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200">
            <Tag className="w-3 h-3" />
            Price Override
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-brand-600">
              Control Center
            </span>
            <span className="text-slate-300">•</span>
            <Badge variant="primary" size="sm">
              Governance & Compliance
            </Badge>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <FileCheck className="w-6 h-6 text-brand-600" />
            Approval Center
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
            Authorize high discounts, custom quote terms, refund payouts, and pricing overrides requiring manager sign-off.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-50 border border-amber-200/80 text-amber-800 text-xs font-bold">
            <Clock className="w-3.5 h-3.5 text-amber-600" />
            {pendingCount} Pending Decisions
          </span>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 border-b border-slate-200/90 pb-2">
        {[
          { key: 'pending', label: `Pending Review (${pendingCount})` },
          { key: 'approved', label: 'Approved' },
          { key: 'rejected', label: 'Rejected' },
          { key: 'all', label: 'All Requests' },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setStatusFilter(tab.key as typeof statusFilter)}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${
              statusFilter === tab.key
                ? 'bg-brand-600 text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Approval Requests List */}
      <div className="space-y-3">
        {filteredApprovals.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-500 flex items-center justify-center mx-auto mb-3">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">
                {statusFilter === 'all' ? 'No approval requests' : `No ${statusFilter} approvals`}
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                There are no approval requests matching this criteria.
              </p>
            </CardContent>
          </Card>
        ) : (
          filteredApprovals.map((item) => (
            <Card key={item.id} className="hover:border-slate-300 transition-colors">
              <CardContent className="p-4 sm:p-5">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  {/* Left Info */}
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-mono font-bold text-slate-500">
                        {item.id}
                      </span>
                      <span className="text-slate-300">•</span>
                      {getTypeBadge(item.type)}
                      <span className="text-slate-300">•</span>
                      <span className="text-xs font-bold text-slate-900">{item.customer}</span>
                      <span className="text-slate-300">•</span>
                      <span className="text-[11px] text-slate-400 font-medium">
                        Requested {item.requestedAt}
                      </span>
                    </div>

                    <h4 className="text-sm font-semibold text-slate-900 leading-snug">
                      {item.title}
                    </h4>

                    <p className="text-xs text-slate-600 line-clamp-2">
                      <span className="font-semibold text-slate-700">Justification: </span>
                      {item.justification}
                    </p>

                    <div className="flex items-center gap-2 pt-1 text-[11px] text-slate-500">
                      <User className="w-3.5 h-3.5 text-slate-400" />
                      <span>
                        Requester: <strong>{item.requester}</strong> ({item.role})
                      </span>
                    </div>
                  </div>

                  {/* Right Value & Actions */}
                  <div className="flex items-center justify-between lg:justify-end gap-4 border-t lg:border-t-0 pt-3 lg:pt-0 border-slate-100 shrink-0">
                    <div className="text-left lg:text-right">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                        Requested Value
                      </span>
                      <span className="text-base font-bold text-slate-900 tabular-nums block">
                        {item.amount}
                      </span>
                      {item.originalAmount && (
                        <span className="text-[10px] text-slate-400 line-through block">
                          List: {item.originalAmount}
                        </span>
                      )}
                    </div>

                    {item.status === 'pending' ? (
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          leadingIcon={<Eye className="w-3.5 h-3.5" />}
                          onClick={() => setSelectedApproval(item)}
                        >
                          Review
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          leadingIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
                          onClick={() => handleApprove(item.id, item.customer)}
                        >
                          Approve
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                          onClick={() => handleReject(item.id, item.customer)}
                        >
                          Reject
                        </Button>
                      </div>
                    ) : (
                      <div className="text-right">
                        {item.status === 'approved' ? (
                          <Badge variant="success" size="md">
                            Approved
                          </Badge>
                        ) : (
                          <Badge variant="danger" size="md">
                            Rejected
                          </Badge>
                        )}
                        {item.reviewedBy && (
                          <span className="text-[10px] text-slate-400 block mt-1">
                            By {item.reviewedBy}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Review Modal */}
      {selectedApproval && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedApproval(null)}
          title={`Review Approval Request: ${selectedApproval.id}`}
          size="lg"
        >
          <div className="space-y-4">
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500">Customer Account</span>
                <span className="text-xs font-bold text-slate-900">{selectedApproval.customer}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500">Requester</span>
                <span className="text-xs font-medium text-slate-700">
                  {selectedApproval.requester} ({selectedApproval.role})
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500">Request Type</span>
                <div>{getTypeBadge(selectedApproval.type)}</div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500">Financial Impact</span>
                <span className="text-sm font-bold text-slate-900 tabular-nums">
                  {selectedApproval.amount}
                </span>
              </div>
            </div>

            <div>
              <h5 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-1">
                Business Justification
              </h5>
              <p className="text-xs text-slate-700 bg-white p-3 rounded-lg border border-slate-200 leading-relaxed">
                {selectedApproval.justification}
              </p>
            </div>

            <div className="p-3 rounded-xl bg-blue-50/70 border border-blue-100 flex items-start gap-2.5 text-xs text-brand-800">
              <ShieldCheck className="w-4 h-4 text-brand-600 shrink-0 mt-0.5" />
              <span>
                Approval will generate an audit log record and notify the requester and billing lifecycle automation engine.
              </span>
            </div>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectedApproval(null)}
              >
                Cancel
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                onClick={() => handleReject(selectedApproval.id, selectedApproval.customer)}
              >
                Reject Request
              </Button>
              <Button
                variant="primary"
                size="sm"
                leadingIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
                onClick={() => handleApprove(selectedApproval.id, selectedApproval.customer)}
              >
                Approve Request
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
