import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Bell,
  Calendar,
  CreditCard,
  Eye,
  FileText,
  HandCoins,
  Megaphone,
  Plus,
  ScrollText,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { EmptyState } from '../../components/common/EmptyState';
import { PageHeader } from '../../components/common/PageHeader';
import { useToast } from '../../components/common/Toast';
import { collectionsService } from '../../services/collectionsService';
import { toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { useAuth } from '../../hooks/useAuth';
import { formatDate, formatDateTime, formatMoney, todayIso } from '../../utils/format';
import type {
  CollectionActivityType,
  CollectionStatus,
  PromiseToPayStatus,
} from '../../types/collections';
import {
  ACTIVITY_TYPE_LABELS,
  AGING_BUCKET_LABELS,
  COLLECTION_STATUS_LABELS,
  COLLECTION_STATUS_VARIANTS,
  PROMISE_STATUS_LABELS,
  PROMISE_STATUS_VARIANTS,
} from './collectionsUi';

const ACTIVITY_TYPE_OPTIONS = (Object.keys(ACTIVITY_TYPE_LABELS) as CollectionActivityType[]).map((type) => ({
  value: type,
  label: ACTIVITY_TYPE_LABELS[type],
}));

export function CollectionsInvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const canManage = hasRole('finance');
  const { showToast } = useToast();
  const queryClient = useQueryClient();

  const [activityModal, setActivityModal] = useState<null | { defaultType: CollectionActivityType }>(null);
  const [promiseModalOpen, setPromiseModalOpen] = useState(false);
  const [statusAction, setStatusAction] = useState<null | { status: CollectionStatus; label: string }>(null);

  const detailQuery = useQuery({
    queryKey: queryKeys.collections.detail(id ?? ''),
    queryFn: () => collectionsService.get(id as string),
    enabled: !!id,
  });

  const invalidateDetail = () => {
    // Invalidating the whole `collections` domain also refreshes the list/dashboard
    // queries, since amounts and statuses on this invoice can shift both.
    void queryClient.invalidateQueries({ queryKey: queryKeys.collections.all });
  };

  const reminderMutation = useMutation({
    mutationFn: () => collectionsService.sendReminder(id as string),
    onSuccess: () => {
      showToast('success', 'Reminder sent', 'The customer has been emailed a payment reminder.');
      invalidateDetail();
    },
    onError: (err) => showToast('error', 'Could not send reminder', toApiError(err).message),
  });

  const statusMutation = useMutation({
    mutationFn: (status: CollectionStatus) => collectionsService.updateStatus(id as string, { status: status as Exclude<CollectionStatus, 'collected'> }),
    onSuccess: (_data, status) => {
      showToast('success', 'Status updated', `Invoice marked as ${COLLECTION_STATUS_LABELS[status]}.`);
      invalidateDetail();
      setStatusAction(null);
    },
    onError: (err) => showToast('error', 'Could not update status', toApiError(err).message),
  });

  const promiseStatusMutation = useMutation({
    mutationFn: ({ promiseId, status }: { promiseId: string; status: Exclude<PromiseToPayStatus, 'pending'> }) =>
      collectionsService.updatePromise(promiseId, { status }),
    onSuccess: () => {
      showToast('success', 'Promise updated');
      invalidateDetail();
    },
    onError: (err) => showToast('error', 'Could not update promise', toApiError(err).message),
  });

  if (!id) {
    return <ErrorState message="Missing invoice id." />;
  }

  if (detailQuery.isPending) {
    return <LoadingState message="Loading invoice..." className="py-16" />;
  }

  if (detailQuery.isError) {
    return (
      <ErrorState
        message={toApiError(detailQuery.error).message}
        onRetry={() => void detailQuery.refetch()}
      />
    );
  }

  const invoice = detailQuery.data;
  const activities = [...invoice.activities].sort(
    (a, b) => new Date(b.activity_at).getTime() - new Date(a.activity_at).getTime()
  );

  return (
    <div className="space-y-6">
      <PageHeader
        backTo={{ to: '/collections/invoices', label: 'Back to Collection Invoices' }}
        eyebrow="Revenue · Collections"
        title={
          <span className="inline-flex items-center gap-2.5">
            {invoice.invoice_number}
            <Badge variant={COLLECTION_STATUS_VARIANTS[invoice.collection_status]}>
              {COLLECTION_STATUS_LABELS[invoice.collection_status]}
            </Badge>
          </span>
        }
        subtitle={`${invoice.customer.display_name} · Due ${formatDate(invoice.due_date)}`}
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              leadingIcon={<Eye className="w-3.5 h-3.5" />}
              onClick={() => navigate(`/invoices/${invoice.id}`)}
            >
              View Invoice
            </Button>
            {canManage && (
              <Button
                variant="outline"
                size="sm"
                leadingIcon={<CreditCard className="w-3.5 h-3.5" />}
                onClick={() => navigate(`/invoices/${invoice.id}`)}
              >
                Record Payment
              </Button>
            )}
            {canManage && (
              <Button
                variant="primary"
                size="sm"
                leadingIcon={<Bell className="w-3.5 h-3.5" />}
                isLoading={reminderMutation.isPending}
                onClick={() => reminderMutation.mutate()}
              >
                Send Reminder
              </Button>
            )}
          </>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: summary + timeline */}
        <div className="lg:col-span-2 space-y-6">
          {/* Invoice summary */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-brand-600" /> Invoice Summary
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs">
                <SummaryField label="Customer" value={invoice.customer.display_name} />
                <SummaryField label="Invoice Status" value={invoice.invoice_status.replace(/_/g, ' ')} />
                <SummaryField label="Aging Bucket" value={AGING_BUCKET_LABELS[invoice.aging_bucket]} />
                <SummaryField label="Issue Date" value={formatDate(invoice.issue_date)} />
                <SummaryField label="Due Date" value={formatDate(invoice.due_date)} />
                <SummaryField
                  label="Days Overdue"
                  value={invoice.days_overdue > 0 ? String(invoice.days_overdue) : '—'}
                  emphasize={invoice.days_overdue > 0 ? 'danger' : undefined}
                />
                <SummaryField label="Invoice Total" value={formatMoney(invoice.total, invoice.currency)} />
                <SummaryField label="Amount Paid" value={formatMoney(invoice.amount_paid, invoice.currency)} emphasize="success" />
                <SummaryField label="Outstanding" value={formatMoney(invoice.amount_due, invoice.currency)} emphasize="danger" />
                <SummaryField label="Last Contact" value={formatDate(invoice.last_contact_at)} />
                <SummaryField label="Next Follow-up" value={formatDate(invoice.next_follow_up_at)} />
              </div>
            </CardContent>
          </Card>

          {/* Activity timeline */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ScrollText className="w-4 h-4 text-brand-600" /> Activity Timeline
              </CardTitle>
              {canManage && (
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    leadingIcon={<Calendar className="w-3.5 h-3.5" />}
                    onClick={() => setActivityModal({ defaultType: 'reminder' })}
                  >
                    Add Follow-up
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    leadingIcon={<Plus className="w-3.5 h-3.5" />}
                    onClick={() => setActivityModal({ defaultType: 'internal_note' })}
                  >
                    Add Activity
                  </Button>
                </div>
              )}
            </CardHeader>
            <CardContent className="p-0">
              {activities.length === 0 ? (
                <EmptyState
                  className="border-0 rounded-none"
                  title="No activity logged yet"
                  description="Calls, emails, reminders and notes for this invoice will appear here."
                />
              ) : (
                <div className="divide-y divide-slate-100">
                  {activities.map((activity) => (
                    <div key={activity.id} className="px-5 py-3.5">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <Badge variant="neutral" size="sm">
                            {ACTIVITY_TYPE_LABELS[activity.activity_type]}
                          </Badge>
                          {activity.created_by && (
                            <span className="text-[11px] text-slate-400">by {activity.created_by.full_name}</span>
                          )}
                        </div>
                        <span className="text-[11px] text-slate-400 whitespace-nowrap">
                          {formatDateTime(activity.activity_at)}
                        </span>
                      </div>
                      {activity.note && <p className="text-xs text-slate-600 mt-1.5">{activity.note}</p>}
                      {activity.next_follow_up_at && (
                        <p className="text-[11px] text-brand-600 mt-1 font-medium">
                          Follow up on {formatDate(activity.next_follow_up_at)}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: promises + status actions */}
        <div className="space-y-6">
          {/* Promise to pay */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <HandCoins className="w-4 h-4 text-brand-600" /> Promises to Pay
              </CardTitle>
              {canManage && (
                <Button variant="outline" size="sm" leadingIcon={<Plus className="w-3.5 h-3.5" />} onClick={() => setPromiseModalOpen(true)}>
                  Add
                </Button>
              )}
            </CardHeader>
            <CardContent className="p-0">
              {invoice.promises.length === 0 ? (
                <EmptyState
                  className="border-0 rounded-none"
                  title="No promises logged"
                  description="Record a customer's promise to pay to track it here."
                />
              ) : (
                <div className="divide-y divide-slate-100">
                  {invoice.promises.map((promise) => (
                    <div key={promise.id} className="px-5 py-3.5 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-bold text-slate-900 tabular-nums">
                          {formatMoney(promise.promised_amount, invoice.currency)}
                        </span>
                        <Badge variant={PROMISE_STATUS_VARIANTS[promise.status]} size="sm">
                          {PROMISE_STATUS_LABELS[promise.status]}
                        </Badge>
                      </div>
                      <p className="text-[11px] text-slate-500">Promised for {formatDate(promise.promised_date)}</p>
                      {promise.note && <p className="text-xs text-slate-600">{promise.note}</p>}
                      {canManage && promise.status === 'pending' && (
                        <div className="flex items-center gap-1.5 pt-1">
                          <Button
                            variant="outline"
                            size="sm"
                            isLoading={promiseStatusMutation.isPending && promiseStatusMutation.variables?.promiseId === promise.id && promiseStatusMutation.variables?.status === 'kept'}
                            onClick={() => promiseStatusMutation.mutate({ promiseId: promise.id, status: 'kept' })}
                          >
                            Kept
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            isLoading={promiseStatusMutation.isPending && promiseStatusMutation.variables?.promiseId === promise.id && promiseStatusMutation.variables?.status === 'broken'}
                            onClick={() => promiseStatusMutation.mutate({ promiseId: promise.id, status: 'broken' })}
                          >
                            Broken
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            isLoading={promiseStatusMutation.isPending && promiseStatusMutation.variables?.promiseId === promise.id && promiseStatusMutation.variables?.status === 'cancelled'}
                            onClick={() => promiseStatusMutation.mutate({ promiseId: promise.id, status: 'cancelled' })}
                          >
                            Cancel
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Status actions */}
          {canManage && invoice.collection_status !== 'written_off' && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-brand-600" /> Status Actions
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2.5">
                {invoice.collection_status !== 'disputed' && (
                  <Button
                    variant="outline"
                    size="sm"
                    leadingIcon={<AlertTriangle className="w-3.5 h-3.5" />}
                    onClick={() => setStatusAction({ status: 'disputed', label: 'Mark Disputed' })}
                  >
                    Mark Disputed
                  </Button>
                )}
                {invoice.collection_status !== 'escalated' && (
                  <Button
                    variant="outline"
                    size="sm"
                    leadingIcon={<Megaphone className="w-3.5 h-3.5" />}
                    onClick={() => setStatusAction({ status: 'escalated', label: 'Escalate' })}
                  >
                    Escalate
                  </Button>
                )}
                {invoice.collection_status !== 'in_follow_up' && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setStatusAction({ status: 'in_follow_up', label: 'Start Follow-up' })}
                  >
                    Start Follow-up
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setStatusAction({ status: 'written_off', label: 'Write Off' })}
                >
                  Write Off
                </Button>
                {invoice.collection_status !== 'current' && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setStatusAction({ status: 'current', label: 'Clear to Current' })}
                  >
                    Clear to Current
                  </Button>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Add Activity / Follow-up modal */}
      {activityModal && (
        <ActivityModal
          invoiceId={invoice.id}
          defaultType={activityModal.defaultType}
          onClose={() => setActivityModal(null)}
          onDone={invalidateDetail}
        />
      )}

      {/* Add Promise to Pay modal */}
      {promiseModalOpen && (
        <PromiseModal
          invoiceId={invoice.id}
          amountDue={invoice.amount_due}
          onClose={() => setPromiseModalOpen(false)}
          onDone={invalidateDetail}
        />
      )}

      {/* Status change confirm */}
      {statusAction && (
        <ConfirmDialog
          isOpen={true}
          onClose={() => setStatusAction(null)}
          onConfirm={() => statusMutation.mutate(statusAction.status)}
          title={statusAction.label}
          description={`This changes the collection status of ${invoice.invoice_number} to "${COLLECTION_STATUS_LABELS[statusAction.status]}". This is visible to the whole team.`}
          confirmLabel={statusAction.label}
          variant={statusAction.status === 'disputed' || statusAction.status === 'escalated' || statusAction.status === 'written_off' ? 'danger' : 'default'}
          isLoading={statusMutation.isPending}
        />
      )}
    </div>
  );
}

function SummaryField({
  label,
  value,
  emphasize,
}: {
  label: string;
  value: string;
  emphasize?: 'success' | 'danger';
}) {
  return (
    <div>
      <span className="text-slate-500 block font-medium mb-0.5">{label}</span>
      <span
        className={
          emphasize === 'success'
            ? 'font-bold text-emerald-600 tabular-nums capitalize'
            : emphasize === 'danger'
            ? 'font-bold text-rose-600 tabular-nums capitalize'
            : 'font-semibold text-slate-900 capitalize'
        }
      >
        {value}
      </span>
    </div>
  );
}

function ActivityModal({
  invoiceId,
  defaultType,
  onClose,
  onDone,
}: {
  invoiceId: string;
  defaultType: CollectionActivityType;
  onClose: () => void;
  onDone: () => void;
}) {
  const { showToast } = useToast();
  const [activityType, setActivityType] = useState<CollectionActivityType>(defaultType);
  const [note, setNote] = useState('');
  const [activityAt, setActivityAt] = useState(todayIso());
  const [nextFollowUpAt, setNextFollowUpAt] = useState('');

  const mutation = useMutation({
    mutationFn: () =>
      collectionsService.addActivity(invoiceId, {
        activity_type: activityType,
        note: note.trim() || undefined,
        activity_at: activityAt ? `${activityAt}T00:00:00Z` : undefined,
        next_follow_up_at: nextFollowUpAt || undefined,
      }),
    onSuccess: () => {
      showToast('success', 'Activity logged');
      onDone();
      onClose();
    },
    onError: (err) => showToast('error', 'Could not log activity', toApiError(err).message),
  });

  return (
    <Modal isOpen={true} onClose={onClose} title="Log Activity / Follow-up" size="md">
      <div className="space-y-4">
        <Select
          label="Activity Type"
          required
          value={activityType}
          onChange={(e) => setActivityType(e.target.value as CollectionActivityType)}
          options={ACTIVITY_TYPE_OPTIONS}
        />
        <Input label="Activity Date" type="date" value={activityAt} onChange={(e) => setActivityAt(e.target.value)} />
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1.5">Note</label>
          <textarea
            rows={3}
            placeholder="What happened, what was discussed..."
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
          />
        </div>
        <Input
          label="Next Follow-up Date"
          type="date"
          value={nextFollowUpAt}
          onChange={(e) => setNextFollowUpAt(e.target.value)}
          helperText="Optional — schedule the next time this invoice needs attention."
        />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" isLoading={mutation.isPending} onClick={() => mutation.mutate()}>
            Save
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function PromiseModal({
  invoiceId,
  amountDue,
  onClose,
  onDone,
}: {
  invoiceId: string;
  amountDue: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const { showToast } = useToast();
  const [amount, setAmount] = useState(amountDue);
  const [promisedDate, setPromisedDate] = useState(todayIso());
  const [note, setNote] = useState('');

  const mutation = useMutation({
    mutationFn: () =>
      collectionsService.addPromise(invoiceId, {
        promised_amount: amount,
        promised_date: promisedDate,
        note: note.trim() || undefined,
      }),
    onSuccess: () => {
      showToast('success', 'Promise to pay recorded');
      onDone();
      onClose();
    },
    onError: (err) => showToast('error', 'Could not record promise', toApiError(err).message),
  });

  const canSubmit = Number(amount) > 0 && !!promisedDate;

  return (
    <Modal isOpen={true} onClose={onClose} title="Add Promise to Pay" size="md">
      <div className="space-y-4">
        <Input
          label="Promised Amount"
          type="number"
          min="0"
          step="0.01"
          required
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <Input
          label="Promised Date"
          type="date"
          required
          value={promisedDate}
          onChange={(e) => setPromisedDate(e.target.value)}
        />
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1.5">Note</label>
          <textarea
            rows={3}
            placeholder="Any context from the customer..."
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" disabled={!canSubmit} isLoading={mutation.isPending} onClick={() => mutation.mutate()}>
            Save
          </Button>
        </div>
      </div>
    </Modal>
  );
}
