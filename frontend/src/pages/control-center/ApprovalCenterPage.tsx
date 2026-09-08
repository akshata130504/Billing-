import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { controlCenterService, toApiError } from '../../services';
import { queryKeys } from '../../hooks/queries';
import { useAuth } from '../../hooks/useAuth';
import { formatDateTime } from '../../utils/format';
import type { ApprovalOut, ApprovalStatus, ApprovalType } from '../../types/api';
import {
  FileCheck,
  CheckCircle2,
  Clock,
  User,
  Percent,
  Receipt,
  Tag,
  ShieldCheck,
  ShieldAlert,
  Eye,
  XCircle,
} from 'lucide-react';

const TYPE_LABELS: Record<ApprovalType, string> = {
  quote_discount: 'Quote Discount',
  invoice_discount: 'Invoice Discount',
  refund: 'Refund',
  invoice_void: 'Invoice Void',
};

const TYPE_BADGE_STYLES: Record<ApprovalType, string> = {
  quote_discount: 'bg-blue-50 text-blue-700 border-blue-200',
  invoice_discount: 'bg-amber-50 text-amber-700 border-amber-200',
  refund: 'bg-rose-50 text-rose-700 border-rose-200',
  invoice_void: 'bg-purple-50 text-purple-700 border-purple-200',
};

const TYPE_ICONS: Record<ApprovalType, React.ComponentType<{ className?: string }>> = {
  quote_discount: FileCheck,
  invoice_discount: Percent,
  refund: Receipt,
  invoice_void: Tag,
};

function TypeBadge({ type }: { type: ApprovalType }) {
  const Icon = TYPE_ICONS[type];
  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${TYPE_BADGE_STYLES[type]}`}
    >
      <Icon className="w-3 h-3" />
      {TYPE_LABELS[type]}
    </span>
  );
}

/** Renders a flat JSON object's fields as a small key/value list; falls back to raw JSON. */
function PayloadPreview({ payload }: { payload: Record<string, unknown> }) {
  const entries = Object.entries(payload ?? {});
  if (entries.length === 0) return null;

  const isFlat = entries.every(([, v]) => v === null || typeof v !== 'object');
  if (isFlat) {
    return (
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
        {entries.map(([key, value]) => (
          <div key={key} className="flex items-center justify-between gap-2 text-xs">
            <dt className="text-slate-500 font-medium">{key.replace(/_/g, ' ')}</dt>
            <dd className="text-slate-900 font-semibold tabular-nums truncate">
              {value === null || value === undefined || value === '' ? '—' : String(value)}
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  return (
    <pre className="text-[11px] text-slate-700 bg-slate-50 border border-slate-200 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-words">
      {JSON.stringify(payload, null, 2)}
    </pre>
  );
}

export function ApprovalCenterPage() {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const { hasRole } = useAuth();
  const canDecide = hasRole('admin');

  const [statusFilter, setStatusFilter] = useState<'all' | ApprovalStatus>('pending');
  const [selectedApproval, setSelectedApproval] = useState<ApprovalOut | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [rejectNote, setRejectNote] = useState('');

  const filterParams = { status: statusFilter === 'all' ? undefined : statusFilter };

  const approvalsQuery = useQuery({
    queryKey: queryKeys.controlCenter.approvals(filterParams),
    queryFn: () => controlCenterService.listApprovals(filterParams),
  });

  const approvals = approvalsQuery.data?.items ?? [];

  const pendingQuery = useQuery({
    queryKey: queryKeys.controlCenter.approvals({ status: 'pending' }),
    queryFn: () => controlCenterService.listApprovals({ status: 'pending' }),
  });
  const pendingCount = pendingQuery.data?.total ?? 0;

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.controlCenter.all });
  };

  const approveMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) => controlCenterService.approve(id, note),
    onSuccess: (approval) => {
      invalidate();
      setSelectedApproval(null);
      showToast('success', 'Request approved', `${approval.title} was approved.`);
    },
    onError: (err) => showToast('error', 'Could not approve', toApiError(err).message),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => controlCenterService.reject(id, note),
    onSuccess: (approval) => {
      invalidate();
      setSelectedApproval(null);
      setRejecting(false);
      setRejectNote('');
      showToast('info', 'Request rejected', `${approval.title} was rejected.`);
    },
    onError: (err) => showToast('error', 'Could not reject', toApiError(err).message),
  });

  const openReview = (item: ApprovalOut) => {
    setSelectedApproval(item);
    setRejecting(false);
    setRejectNote('');
  };

  const closeReview = () => {
    setSelectedApproval(null);
    setRejecting(false);
    setRejectNote('');
  };

  const submitReject = (id: string) => {
    if (!rejectNote.trim()) return;
    rejectMutation.mutate({ id, note: rejectNote.trim() });
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
            Authorize quote discounts, invoice discounts, refunds, and invoice voids requiring manager sign-off.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-50 border border-amber-200/80 text-amber-800 text-xs font-bold">
            <Clock className="w-3.5 h-3.5 text-amber-600" />
            {pendingCount} Pending Decisions
          </span>
        </div>
      </div>

      {!canDecide && (
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 flex items-start gap-2.5 text-xs text-slate-600">
          <ShieldAlert className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
          <span>Only Admins and Owners can approve or reject requests. You can still review request details.</span>
        </div>
      )}

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
      {approvalsQuery.isPending ? (
        <LoadingState message="Loading approval requests..." className="py-16" />
      ) : approvalsQuery.isError ? (
        <ErrorState message={toApiError(approvalsQuery.error).message} onRetry={() => void approvalsQuery.refetch()} />
      ) : (
        <div className="space-y-3">
          {approvals.length === 0 ? (
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
            approvals.map((item) => (
              <Card key={item.id} className="hover:border-slate-300 transition-colors">
                <CardContent className="p-4 sm:p-5">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    {/* Left Info */}
                    <div className="space-y-1.5 flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-mono font-bold text-slate-500">
                          {item.entity_label}
                        </span>
                        <span className="text-slate-300">•</span>
                        <TypeBadge type={item.type} />
                        <span className="text-slate-300">•</span>
                        <span className="text-[11px] text-slate-400 font-medium">
                          Requested {formatDateTime(item.created_at)}
                        </span>
                      </div>

                      <h4 className="text-sm font-semibold text-slate-900 leading-snug">
                        {item.title}
                      </h4>

                      {item.justification && (
                        <p className="text-xs text-slate-600 line-clamp-2">
                          <span className="font-semibold text-slate-700">Justification: </span>
                          {item.justification}
                        </p>
                      )}

                      {item.requested_by && (
                        <div className="flex items-center gap-2 pt-1 text-[11px] text-slate-500">
                          <User className="w-3.5 h-3.5 text-slate-400" />
                          <span>
                            Requester: <strong>{item.requested_by.full_name}</strong> ({item.requested_by.email})
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Right Actions */}
                    <div className="flex items-center justify-between lg:justify-end gap-4 border-t lg:border-t-0 pt-3 lg:pt-0 border-slate-100 shrink-0">
                      {item.status === 'pending' ? (
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            leadingIcon={<Eye className="w-3.5 h-3.5" />}
                            onClick={() => openReview(item)}
                          >
                            Review
                          </Button>
                          {canDecide && (
                            <>
                              <Button
                                variant="primary"
                                size="sm"
                                leadingIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
                                isLoading={approveMutation.isPending && approveMutation.variables?.id === item.id}
                                onClick={() => approveMutation.mutate({ id: item.id })}
                              >
                                Approve
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                                onClick={() => openReview(item)}
                              >
                                Reject
                              </Button>
                            </>
                          )}
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
                          {item.reviewed_by && (
                            <span className="text-[10px] text-slate-400 block mt-1">
                              By {item.reviewed_by.full_name}
                            </span>
                          )}
                          {item.reviewed_at && (
                            <span className="text-[10px] text-slate-400 block">
                              {formatDateTime(item.reviewed_at)}
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
      )}

      {/* Review Modal */}
      {selectedApproval && (
        <Modal
          isOpen={true}
          onClose={closeReview}
          title={`Review Approval Request: ${selectedApproval.entity_label}`}
          size="lg"
        >
          <div className="space-y-4">
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500">Entity</span>
                <span className="text-xs font-bold text-slate-900">
                  {selectedApproval.entity_label} ({selectedApproval.entity_type})
                </span>
              </div>
              {selectedApproval.requested_by && (
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-500">Requester</span>
                  <span className="text-xs font-medium text-slate-700">
                    {selectedApproval.requested_by.full_name} ({selectedApproval.requested_by.email})
                  </span>
                </div>
              )}
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500">Request Type</span>
                <div>
                  <TypeBadge type={selectedApproval.type} />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500">Requested</span>
                <span className="text-xs font-medium text-slate-700">
                  {formatDateTime(selectedApproval.created_at)}
                </span>
              </div>
              {selectedApproval.status !== 'pending' && (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-500">Status</span>
                    <Badge variant={selectedApproval.status === 'approved' ? 'success' : 'danger'} size="sm">
                      {selectedApproval.status}
                    </Badge>
                  </div>
                  {selectedApproval.reviewed_by && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-500">Reviewed by</span>
                      <span className="text-xs font-medium text-slate-700">
                        {selectedApproval.reviewed_by.full_name}
                        {selectedApproval.reviewed_at ? ` · ${formatDateTime(selectedApproval.reviewed_at)}` : ''}
                      </span>
                    </div>
                  )}
                </>
              )}
            </div>

            {selectedApproval.justification && (
              <div>
                <h5 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-1">
                  Business Justification
                </h5>
                <p className="text-xs text-slate-700 bg-white p-3 rounded-lg border border-slate-200 leading-relaxed">
                  {selectedApproval.justification}
                </p>
              </div>
            )}

            {Object.keys(selectedApproval.payload ?? {}).length > 0 && (
              <div>
                <h5 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-1">
                  Request Details
                </h5>
                <PayloadPreview payload={selectedApproval.payload} />
              </div>
            )}

            {selectedApproval.decision_note && (
              <div>
                <h5 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-1">
                  Decision Note
                </h5>
                <p className="text-xs text-slate-700 bg-white p-3 rounded-lg border border-slate-200 leading-relaxed">
                  {selectedApproval.decision_note}
                </p>
              </div>
            )}

            {selectedApproval.status === 'pending' && (
              <div className="p-3 rounded-xl bg-blue-50/70 border border-blue-100 flex items-start gap-2.5 text-xs text-brand-800">
                <ShieldCheck className="w-4 h-4 text-brand-600 shrink-0 mt-0.5" />
                <span>
                  Approval will generate an audit log record and notify the requester and billing lifecycle automation engine.
                </span>
              </div>
            )}

            {selectedApproval.status === 'pending' && !canDecide && (
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 flex items-start gap-2.5 text-xs text-slate-600">
                <ShieldAlert className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                <span>Only Admins and Owners can approve or reject requests.</span>
              </div>
            )}

            {selectedApproval.status === 'pending' && canDecide && rejecting && (
              <div className="space-y-1.5">
                <label className="block text-xs font-bold text-slate-900 uppercase tracking-wider">
                  Reason for rejection <span className="text-rose-500">*</span>
                </label>
                <textarea
                  rows={3}
                  autoFocus
                  value={rejectNote}
                  onChange={(e) => setRejectNote(e.target.value)}
                  placeholder="Explain why this request is being declined..."
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
                />
                {rejectMutation.isError && (
                  <p className="text-xs text-rose-600 font-medium">{toApiError(rejectMutation.error).message}</p>
                )}
              </div>
            )}

            {selectedApproval.status === 'pending' && canDecide && (
              <div className="flex items-center justify-end gap-2.5 pt-2">
                {rejecting ? (
                  <>
                    <Button variant="outline" size="sm" onClick={() => setRejecting(false)}>
                      Back
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      leadingIcon={<XCircle className="w-3.5 h-3.5" />}
                      disabled={!rejectNote.trim()}
                      isLoading={rejectMutation.isPending}
                      onClick={() => submitReject(selectedApproval.id)}
                    >
                      Confirm Rejection
                    </Button>
                  </>
                ) : (
                  <>
                    <Button variant="outline" size="sm" onClick={closeReview}>
                      Cancel
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                      onClick={() => setRejecting(true)}
                    >
                      Reject Request
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      leadingIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
                      isLoading={approveMutation.isPending}
                      onClick={() => approveMutation.mutate({ id: selectedApproval.id })}
                    >
                      Approve Request
                    </Button>
                  </>
                )}
              </div>
            )}

            {selectedApproval.status !== 'pending' && (
              <div className="flex items-center justify-end pt-2">
                <Button variant="outline" size="sm" onClick={closeReview}>
                  Close
                </Button>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
