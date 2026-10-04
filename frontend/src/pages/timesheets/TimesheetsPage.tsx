import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import {
  Timer,
  Plus,
  Search,
  DollarSign,
  Clock,
  CheckCircle2,
  XCircle,
  Send,
  Trash2,
  Edit2,
  RefreshCw,
  Building2,
  Briefcase,
  Layers,
  Receipt,
} from 'lucide-react';
import { timesheetService } from '../../services/timesheetService';
import type {
  TimeEntryCreate,
  TimeEntryRead,
  TimeEntryStatus,
  TimeEntrySummaryKPIs,
  TimeEntryUpdate,
} from '../../types/api';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { StatCard } from '../../components/common/StatCard';
import { LoadingState } from '../../components/common/LoadingState';
import { EmptyState } from '../../components/common/EmptyState';
import { Modal } from '../../components/common/Modal';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatMoney, formatDate, humanize } from '../../utils/format';

import { TimeEntryModal } from './TimeEntryModal';
import { WeeklyTimesheetView } from './WeeklyTimesheetView';
import { GenerateInvoiceModal } from './GenerateInvoiceModal';

export function TimesheetsPage() {
  const [searchParams] = useSearchParams();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canApprove = hasRole('finance') || hasRole('admin');

  const [activeTab, setActiveTab] = useState<'list' | 'weekly'>('list');
  const [entries, setEntries] = useState<TimeEntryRead[]>([]);
  const [summary, setSummary] = useState<TimeEntrySummaryKPIs | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  // Filters
  const customerIdParam = searchParams.get('customer_id') || '';
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [billableFilter, setBillableFilter] = useState<string>('all');

  // Modals
  const [entryModalOpen, setEntryModalOpen] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<TimeEntryRead | null>(null);
  const [invoiceModalOpen, setInvoiceModalOpen] = useState(false);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [entryToReject, setEntryToReject] = useState<TimeEntryRead | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [entryToDelete, setEntryToDelete] = useState<TimeEntryRead | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [kpiData, listData] = await Promise.all([
        timesheetService.summary({}),
        timesheetService.list({
          customer_id: customerIdParam || undefined,
          status: statusFilter !== 'all' ? (statusFilter as TimeEntryStatus) : undefined,
          billable: billableFilter === 'billable' ? true : billableFilter === 'non_billable' ? false : undefined,
          search: searchQuery || undefined,
        }),
      ]);
      setSummary(kpiData);
      setEntries(listData);
    } catch (err: any) {
      showToast('error', 'Error', err.message || 'Failed to load timesheet data');
    } finally {
      setLoading(false);
    }
  }, [customerIdParam, statusFilter, billableFilter, searchQuery, showToast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSaveEntry = async (data: TimeEntryCreate | TimeEntryUpdate) => {
    try {
      setActionLoading(true);
      if (selectedEntry) {
        await timesheetService.update(selectedEntry.id, data as TimeEntryUpdate);
        showToast('success', 'Entry Updated', 'Time entry updated successfully');
      } else {
        await timesheetService.create(data as TimeEntryCreate);
        showToast('success', 'Entry Logged', 'Time entry logged successfully');
      }
      setEntryModalOpen(false);
      setSelectedEntry(null);
      loadData();
    } catch (err: any) {
      showToast('error', 'Save Failed', err.message || 'Failed to save time entry');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteEntry = async () => {
    if (!entryToDelete) return;
    try {
      setDeleting(true);
      await timesheetService.delete(entryToDelete.id);
      showToast('success', 'Deleted', 'Time entry deleted');
      setEntryToDelete(null);
      loadData();
    } catch (err: any) {
      showToast('error', 'Delete Failed', err.message || 'Failed to delete entry');
    } finally {
      setDeleting(false);
    }
  };

  const handleSubmitEntry = async (id: string) => {
    try {
      await timesheetService.submit(id);
      showToast('success', 'Submitted', 'Timesheet entry submitted for approval');
      loadData();
    } catch (err: any) {
      showToast('error', 'Submit Failed', err.message || 'Failed to submit entry');
    }
  };

  const handleApproveEntry = async (id: string) => {
    try {
      await timesheetService.approve(id);
      showToast('success', 'Approved', 'Timesheet entry approved');
      loadData();
    } catch (err: any) {
      showToast('error', 'Approve Failed', err.message || 'Failed to approve entry');
    }
  };

  const handleRejectEntry = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!entryToReject) return;
    try {
      await timesheetService.reject(entryToReject.id, rejectReason);
      showToast('info', 'Rejected', 'Timesheet entry rejected');
      setRejectModalOpen(false);
      setEntryToReject(null);
      setRejectReason('');
      loadData();
    } catch (err: any) {
      showToast('error', 'Reject Failed', err.message || 'Failed to reject entry');
    }
  };

  return (
    <div className="space-y-6 pb-16">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-1">
            <Timer className="w-4 h-4" />
            Operations & Delivery
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Timesheets & Time Tracking</h1>
          <p className="text-sm text-slate-500 mt-1">
            Log time against customers and projects, manage approvals, and convert billable hours directly into invoices.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Button
            variant="outline"
            size="sm"
            onClick={() => loadData()}
            leadingIcon={<RefreshCw className="w-4 h-4" />}
          >
            Refresh
          </Button>
          {canApprove && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setInvoiceModalOpen(true)}
              className="text-emerald-700 border-emerald-200 hover:bg-emerald-50"
              leadingIcon={<Receipt className="w-4 h-4 text-emerald-600" />}
            >
              Generate Invoice
            </Button>
          )}
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setSelectedEntry(null);
              setEntryModalOpen(true);
            }}
            leadingIcon={<Plus className="w-4 h-4" />}
          >
            Log Time
          </Button>
        </div>
      </div>

      {/* KPI Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard
          title="Total Hours"
          value={`${summary?.total_hours || '0.00'}h`}
          icon={<Clock className="w-4 h-4 text-slate-500" />}
        />
        <StatCard
          title="Billable Hours"
          value={`${summary?.billable_hours || '0.00'}h`}
          icon={<CheckCircle2 className="w-4 h-4 text-emerald-600" />}
        />
        <StatCard
          title="Non-Billable"
          value={`${summary?.non_billable_hours || '0.00'}h`}
          icon={<Layers className="w-4 h-4 text-slate-500" />}
        />
        <StatCard
          title="Billable Amount"
          value={formatMoney(summary?.billable_amount || '0.00')}
          icon={<DollarSign className="w-4 h-4 text-blue-600" />}
        />
        <StatCard
          title="Unbilled Value"
          value={formatMoney(summary?.unbilled_amount || '0.00')}
          icon={<Receipt className="w-4 h-4 text-amber-600" />}
        />
        <StatCard
          title="Pending Approval"
          value={summary?.pending_approval_count ?? 0}
          icon={<Send className="w-4 h-4 text-amber-600" />}
        />
      </div>

      {/* View Switcher & Filter Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          {/* View Switcher */}
          <div className="flex items-center bg-slate-100 p-1 rounded-lg border border-slate-200 w-fit">
            <button
              onClick={() => setActiveTab('list')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                activeTab === 'list'
                  ? 'bg-white text-blue-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              List View
            </button>
            <button
              onClick={() => setActiveTab('weekly')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                activeTab === 'weekly'
                  ? 'bg-white text-blue-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Weekly Matrix
            </button>
          </div>

          {/* Quick Filters */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative flex-1 sm:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search project or task..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-2.5 py-1.5 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Statuses</option>
              <option value="draft">Draft</option>
              <option value="submitted">Submitted</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="billed">Billed</option>
            </select>
            <select
              value={billableFilter}
              onChange={(e) => setBillableFilter(e.target.value)}
              className="px-2.5 py-1.5 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Types</option>
              <option value="billable">Billable Only</option>
              <option value="non_billable">Non-Billable Only</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {activeTab === 'weekly' ? (
        <WeeklyTimesheetView
          onAddEntry={() => {
            setSelectedEntry(null);
            setEntryModalOpen(true);
          }}
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          {loading ? (
            <div className="py-16">
              <LoadingState message="Loading time entries..." />
            </div>
          ) : entries.length === 0 ? (
            <div className="py-12">
              <EmptyState
                title="No time entries logged"
                description="Start recording time against client engagements and projects."
                icon={<Timer className="w-8 h-8 text-slate-400" />}
                action={
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setSelectedEntry(null);
                      setEntryModalOpen(true);
                    }}
                  >
                    Log First Time Entry
                  </Button>
                }
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-600">
                <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                  <tr>
                    <th className="px-5 py-3.5">Date</th>
                    <th className="px-5 py-3.5">Member</th>
                    <th className="px-5 py-3.5">Customer & Project</th>
                    <th className="px-5 py-3.5">Description</th>
                    <th className="px-5 py-3.5 text-center">Hours</th>
                    <th className="px-5 py-3.5">Rate / Amount</th>
                    <th className="px-5 py-3.5">Status</th>
                    <th className="px-5 py-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {entries.map((entry) => {
                    const isBilled = entry.status === 'billed';
                    const isApproved = entry.status === 'approved';
                    const isSubmitted = entry.status === 'submitted';
                    const isDraft = entry.status === 'draft';
                    const isRejected = entry.status === 'rejected';

                    return (
                      <tr key={entry.id} className="hover:bg-slate-50/70 transition-colors">
                        <td className="px-5 py-4 whitespace-nowrap text-xs font-medium text-slate-900">
                          {formatDate(entry.date)}
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap text-xs text-slate-700">
                          <span className="font-semibold text-slate-900">{entry.user_name || 'Member'}</span>
                        </td>
                        <td className="px-5 py-4">
                          <div className="font-semibold text-slate-900 flex items-center gap-1.5">
                            <Briefcase className="w-3.5 h-3.5 text-blue-500 flex-shrink-0" />
                            <span>{entry.project_name || 'General'}</span>
                          </div>
                          {entry.customer_name ? (
                            <div className="text-xs text-slate-400 flex items-center gap-1 mt-0.5">
                              <Building2 className="w-3 h-3 text-slate-300" />
                              <Link
                                to={`/customer-lifecycle/${entry.customer_id}`}
                                className="hover:text-blue-600 hover:underline"
                              >
                                {entry.customer_name}
                              </Link>
                            </div>
                          ) : (
                            <span className="text-[11px] text-slate-400 italic">Internal</span>
                          )}
                        </td>
                        <td className="px-5 py-4 max-w-xs truncate text-xs text-slate-600">
                          <span title={entry.description}>{entry.description}</span>
                          {entry.rejection_reason && (
                            <div className="text-[11px] text-rose-600 font-medium mt-0.5 flex items-center gap-1">
                              <XCircle className="w-3 h-3 flex-shrink-0" />
                              <span>{entry.rejection_reason}</span>
                            </div>
                          )}
                        </td>
                        <td className="px-5 py-4 text-center">
                          <span className="inline-block px-2 py-0.5 rounded bg-blue-50 font-bold text-blue-900 text-xs border border-blue-100">
                            {entry.duration_hours}h
                          </span>
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap">
                          {entry.billable ? (
                            <div>
                              <div className="font-bold text-slate-900 text-xs">
                                {formatMoney(entry.billable_amount)}
                              </div>
                              <div className="text-[10px] text-slate-400">
                                @ INR {entry.billing_rate}/hr
                              </div>
                            </div>
                          ) : (
                            <Badge variant="neutral" className="text-[10px]">
                              Non-Billable
                            </Badge>
                          )}
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap">
                          <Badge
                            variant={
                              isBilled
                                ? 'success'
                                : isApproved
                                ? 'info'
                                : isSubmitted
                                ? 'warning'
                                : isRejected
                                ? 'danger'
                                : 'neutral'
                            }
                          >
                            {humanize(entry.status)}
                          </Badge>
                          {isBilled && entry.invoice_id && (
                            <div className="text-[10px] text-blue-600 mt-1 flex items-center gap-1">
                              <Link to={`/invoices/${entry.invoice_id}`} className="hover:underline flex items-center gap-0.5">
                                <Receipt className="w-3 h-3" />
                                <span>{entry.invoice_number || 'View Invoice'}</span>
                              </Link>
                            </div>
                          )}
                        </td>
                        <td className="px-5 py-4 text-right whitespace-nowrap">
                          <div className="flex items-center justify-end gap-1.5">
                            {/* Draft action: Submit */}
                            {(isDraft || isRejected) && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-xs text-blue-600 hover:bg-blue-50 px-2 py-1"
                                onClick={() => handleSubmitEntry(entry.id)}
                                title="Submit for Approval"
                              >
                                <Send className="w-3.5 h-3.5 mr-1" />
                                Submit
                              </Button>
                            )}

                            {/* Submitted action: Approve / Reject (finance) */}
                            {isSubmitted && canApprove && (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="text-xs text-emerald-700 hover:bg-emerald-50 px-2 py-1"
                                  onClick={() => handleApproveEntry(entry.id)}
                                  title="Approve Entry"
                                >
                                  <CheckCircle2 className="w-3.5 h-3.5 mr-1 text-emerald-600" />
                                  Approve
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="text-xs text-rose-700 hover:bg-rose-50 px-2 py-1"
                                  onClick={() => {
                                    setEntryToReject(entry);
                                    setRejectModalOpen(true);
                                  }}
                                  title="Reject Entry"
                                >
                                  <XCircle className="w-3.5 h-3.5 mr-1 text-rose-600" />
                                  Reject
                                </Button>
                              </>
                            )}

                            {/* Edit (if not billed) */}
                            {!isBilled && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-xs text-slate-500 hover:text-slate-900 px-2 py-1"
                                onClick={() => {
                                  setSelectedEntry(entry);
                                  setEntryModalOpen(true);
                                }}
                              >
                                <Edit2 className="w-3.5 h-3.5" />
                              </Button>
                            )}

                            {/* Delete (if not billed) */}
                            {!isBilled && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-xs text-rose-500 hover:text-rose-700 hover:bg-rose-50 px-2 py-1"
                                onClick={() => setEntryToDelete(entry)}
                                title="Delete Entry"
                                aria-label="Delete time entry"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Log / Edit Time Entry Modal */}
      {entryModalOpen && (
        <TimeEntryModal
          isOpen={entryModalOpen}
          onClose={() => {
            setEntryModalOpen(false);
            setSelectedEntry(null);
          }}
          onSave={handleSaveEntry}
          initialEntry={selectedEntry}
          loading={actionLoading}
        />
      )}

      {/* Convert to Invoice Modal */}
      {invoiceModalOpen && (
        <GenerateInvoiceModal
          isOpen={invoiceModalOpen}
          onClose={() => setInvoiceModalOpen(false)}
          onSuccess={loadData}
          initialCustomerId={customerIdParam}
        />
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={entryToDelete !== null}
        onClose={() => {
          if (!deleting) setEntryToDelete(null);
        }}
        onConfirm={handleDeleteEntry}
        title="Delete time entry"
        description="Are you sure you want to delete this time entry? This cannot be undone."
        confirmLabel="Delete"
        variant="danger"
        isLoading={deleting}
      />

      {/* Reject Reason Modal */}
      {rejectModalOpen && entryToReject && (
        <Modal
          isOpen={rejectModalOpen}
          onClose={() => {
            setRejectModalOpen(false);
            setEntryToReject(null);
          }}
          title={`Reject Time Entry: ${entryToReject.project_name || 'Entry'}`}
        >
          <form onSubmit={handleRejectEntry} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Reason for Rejection <span className="text-rose-500">*</span>
              </label>
              <textarea
                required
                rows={3}
                placeholder="Explain why this time entry is being returned (e.g. invalid hours, missing deliverable context)..."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>
            <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
              <Button variant="ghost" size="sm" type="button" onClick={() => setRejectModalOpen(false)}>
                Cancel
              </Button>
              <Button variant="danger" size="sm" type="submit">
                Reject Timesheet
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
