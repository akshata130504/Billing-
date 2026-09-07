import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useExpenses } from './ExpensesContext';
import { formatINR } from './mockExpenses';
import { ExpenseFormModal } from './components/ExpenseFormModal';
import { DeleteExpenseModal } from './components/DeleteExpenseModal';
import {
  ArrowLeft,
  Edit2,
  Copy,
  Trash2,
  FileText,
  Building,
  Briefcase,
  Calendar,
  CreditCard,
  User,
  Paperclip,
  Download,
  AlertCircle,
  Clock,
  ExternalLink,
} from 'lucide-react';
import { useToast } from '../../components/common/Toast';

export function ExpenseDetailsPage() {
  const { expenseId } = useParams<{ expenseId: string }>();
  const navigate = useNavigate();
  const { getExpenseById, updateExpense, deleteExpense, duplicateExpense, addToInvoice } =
    useExpenses();
  const { showToast } = useToast();

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);

  const expense = expenseId ? getExpenseById(expenseId) : undefined;

  if (!expense) {
    return (
      <div className="bg-white border border-slate-200/80 rounded-2xl p-12 text-center shadow-2xs">
        <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-500 flex items-center justify-center mx-auto mb-3">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-base font-bold text-slate-900">Expense Not Found</h2>
        <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
          The requested expense record <span className="font-mono font-semibold">{expenseId}</span> does not exist or has been removed.
        </p>
        <div className="mt-4">
          <Link
            to="/expenses"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 shadow-2xs transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Return to Expenses</span>
          </Link>
        </div>
      </div>
    );
  }

  const getStatusBadge = () => {
    switch (expense.status) {
      case 'invoiced':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            Invoiced
          </span>
        );
      case 'billable':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200">
            Billable
          </span>
        );
      case 'recorded':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            Recorded
          </span>
        );
      case 'reimbursed':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            Reimbursed
          </span>
        );
      case 'draft':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            Draft
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            Cancelled
          </span>
        );
      default:
        return null;
    }
  };

  const handleDownloadReceipt = () => {
    showToast(
      'info',
      'Download Receipt',
      `Downloading ${expense.receipt?.fileName || 'receipt.pdf'} for local records.`
    );
  };

  const handleDuplicate = () => {
    const dup = duplicateExpense(expense.id);
    navigate(`/expenses/${dup.id}`);
  };

  return (
    <div className="space-y-4">
      {/* Back to Expenses button */}
      <div>
        <Link
          to="/expenses"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Expenses</span>
        </Link>
      </div>

      {/* Top Banner Header */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              <span className="text-xs font-mono font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
                {expense.id}
              </span>
              {getStatusBadge()}
              {expense.billable ? (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100">
                  Billable to Customer
                </span>
              ) : (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600">
                  Internal Operating Expense
                </span>
              )}
            </div>

            <h1 className="text-xl font-bold text-slate-900 tracking-tight">
              {expense.name}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {expense.description || `${expense.category} expense recorded on ${expense.date}`}
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 flex-wrap shrink-0">
            {expense.billable && expense.status !== 'invoiced' && (
              <button
                type="button"
                onClick={() => addToInvoice(expense.id)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 shadow-2xs transition-colors"
              >
                <span>Add to Invoice</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => setIsEditOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-700 bg-white border border-slate-200/80 hover:bg-slate-50 shadow-2xs transition-colors"
            >
              <Edit2 className="w-3.5 h-3.5 text-slate-500" />
              <span>Edit</span>
            </button>

            <button
              type="button"
              onClick={handleDuplicate}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-700 bg-white border border-slate-200/80 hover:bg-slate-50 shadow-2xs transition-colors"
            >
              <Copy className="w-3.5 h-3.5 text-slate-500" />
              <span>Duplicate</span>
            </button>

            <button
              type="button"
              onClick={() => setIsDeleteOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-rose-600 bg-white border border-rose-200/80 hover:bg-rose-50 shadow-2xs transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5 text-rose-500" />
              <span>Delete</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Grid: Details & Financial Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left 2 Columns: Financial & Allocation Details */}
        <div className="lg:col-span-2 space-y-4">
          {/* Amount & Key Metrics Strip */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-800 mb-3 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-600" />
              Financial Details
            </h2>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-1">
              <div>
                <span className="text-[11px] font-medium text-slate-400 block uppercase">
                  Expense Amount
                </span>
                <span className="text-xl font-bold text-slate-900 font-mono tracking-tight">
                  {formatINR(expense.amount)}
                </span>
                <span className="text-[10px] text-slate-400 block mt-0.5">
                  Currency: {expense.currency}
                </span>
              </div>

              {expense.billable && (
                <div>
                  <span className="text-[11px] font-medium text-emerald-600 block uppercase">
                    Billable Amount
                  </span>
                  <span className="text-xl font-bold text-emerald-700 font-mono tracking-tight">
                    {formatINR(expense.billableAmount ?? expense.amount)}
                  </span>
                  <span className="text-[10px] text-emerald-600/80 block mt-0.5">
                    GST Tax: {expense.taxRate ? `${expense.taxRate}%` : '0% Nil'}
                  </span>
                </div>
              )}

              <div>
                <span className="text-[11px] font-medium text-slate-400 block uppercase">
                  Expense Date
                </span>
                <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 mt-1">
                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                  <span>{expense.date}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Customer & Project Allocation */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
              Customer & Project Allocation
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              <div className="p-3 bg-slate-50/70 rounded-xl border border-slate-100">
                <span className="text-[11px] font-medium text-slate-400 block uppercase mb-1">
                  Customer
                </span>
                <div className="flex items-center gap-2 font-semibold text-slate-900">
                  <Building className="w-4 h-4 text-slate-500" />
                  <span>{expense.customer || 'Internal Operating'}</span>
                </div>
              </div>

              <div className="p-3 bg-slate-50/70 rounded-xl border border-slate-100">
                <span className="text-[11px] font-medium text-slate-400 block uppercase mb-1">
                  Associated Project
                </span>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-semibold text-slate-900">
                    <Briefcase className="w-4 h-4 text-slate-500" />
                    <span>{expense.project || '—'}</span>
                  </div>
                  {expense.projectId && (
                    <Link
                      to={`/projects/${expense.projectId}`}
                      className="text-brand-600 hover:text-brand-700 flex items-center gap-1 font-medium"
                    >
                      <span>Open Project</span>
                      <ExternalLink className="w-3 h-3" />
                    </Link>
                  )}
                </div>
              </div>

              <div className="p-3 bg-slate-50/70 rounded-xl border border-slate-100">
                <span className="text-[11px] font-medium text-slate-400 block uppercase mb-1">
                  Invoice Treatment
                </span>
                <p className="font-semibold text-slate-900 capitalize">
                  {expense.invoiceTreatment?.replace(/_/g, ' ') || 'Internal expense'}
                </p>
              </div>

              <div className="p-3 bg-slate-50/70 rounded-xl border border-slate-100">
                <span className="text-[11px] font-medium text-slate-400 block uppercase mb-1">
                  Invoice Reference
                </span>
                <p className="font-mono font-semibold text-slate-900">
                  {expense.invoiceId || (expense.status === 'invoiced' ? 'INV-2026-0042' : 'Not yet invoiced')}
                </p>
              </div>
            </div>
          </div>

          {/* Payment & Audit Info */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
              Payment & Audit Ledger
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              <div className="flex items-start gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
                  <CreditCard className="w-4 h-4" />
                </div>
                <div>
                  <span className="text-[11px] font-medium text-slate-400 block uppercase">
                    Payment Method
                  </span>
                  <span className="font-semibold text-slate-800">{expense.paymentMethod}</span>
                </div>
              </div>

              <div className="flex items-start gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center shrink-0">
                  <User className="w-4 h-4" />
                </div>
                <div>
                  <span className="text-[11px] font-medium text-slate-400 block uppercase">
                    Paid By
                  </span>
                  <span className="font-semibold text-slate-800">{expense.paidBy}</span>
                </div>
              </div>
            </div>

            {expense.notes && (
              <div className="pt-3 border-t border-slate-100 text-xs">
                <span className="text-[11px] font-medium text-slate-400 block uppercase mb-1">
                  Audit Notes & Description
                </span>
                <p className="text-slate-600 leading-relaxed bg-slate-50/70 p-3 rounded-xl border border-slate-100">
                  {expense.notes}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Right 1 Column: Receipt Card & Metadata */}
        <div className="space-y-4">
          {/* Receipt Card */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <Paperclip className="w-3.5 h-3.5 text-purple-600" />
              Receipt Attachment
            </h2>

            {expense.receipt ? (
              <div className="space-y-3">
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-white border border-slate-200 text-brand-600 flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-slate-900 truncate">
                      {expense.receipt.fileName}
                    </p>
                    <p className="text-[11px] text-slate-400">
                      {expense.receipt.fileSize} · {expense.receipt.uploadDate}
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleDownloadReceipt}
                  className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200/70 rounded-lg transition-colors"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download / View Receipt</span>
                </button>
              </div>
            ) : (
              <div className="text-center py-6 text-xs text-slate-400">
                <Paperclip className="w-8 h-8 mx-auto text-slate-300 mb-1.5" />
                <p>No receipt attached to this expense.</p>
                <button
                  type="button"
                  onClick={() => setIsEditOpen(true)}
                  className="mt-2 text-brand-600 hover:text-brand-700 font-semibold"
                >
                  + Upload Receipt
                </button>
              </div>
            )}
          </div>

          {/* Quick Context Card */}
          <div className="bg-slate-50/80 border border-slate-200/80 rounded-2xl p-4 text-xs text-slate-600 space-y-2">
            <span className="font-bold text-slate-800 block text-[11px] uppercase tracking-wider">
              About Project Rebilling
            </span>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              When an expense is marked <span className="font-semibold text-slate-700">Billable</span>, it automatically appears as an unbilled expense item inside the linked customer project.
            </p>
            <div className="pt-2 border-t border-slate-200/60 flex items-center gap-1.5 text-[11px] text-slate-400">
              <Clock className="w-3 h-3" />
              <span>Created {new Date(expense.createdAt).toLocaleDateString()}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Edit Form Modal */}
      <ExpenseFormModal
        isOpen={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        onSave={(data) => {
          updateExpense(expense.id, data);
        }}
        editingExpense={expense}
      />

      {/* Delete Confirmation Modal */}
      <DeleteExpenseModal
        isOpen={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        onConfirm={() => {
          deleteExpense(expense.id);
          navigate('/expenses');
        }}
        title="Delete Expense Record"
        itemName={expense.name}
      />
    </div>
  );
}
