import type { ProjectInvoiceInput } from '../../../services/projectService';
import { useState } from 'react';
import { Project } from '../types';
import { formatINR } from '../format';
import { formatDate } from './ProjectTable';
import { CreateInvoiceModal } from './CreateInvoiceModal';
import { Button } from '../../../components/common/Button';
import { Badge } from '../../../components/common/Badge';
import { Plus, ArrowUpRight, ArrowDownLeft, FileText, Receipt } from 'lucide-react';

interface ProjectTransactionsProps {
  project: Project;
  onCreateInvoice: (invoice: ProjectInvoiceInput) => Promise<boolean> | boolean | void;
}

export function ProjectTransactions({ project, onCreateInvoice }: ProjectTransactionsProps) {
  const [isInvoiceModalOpen, setIsInvoiceModalOpen] = useState(false);

  // Collect all transactions: quotes, invoices, payments, credit notes
  const transactions = project.transactions || [];

  const getTypeBadge = (type: string) => {
    switch (type) {
      case 'Invoice':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-md">
            <FileText className="w-3 h-3 text-brand-600" />
            Invoice
          </span>
        );
      case 'Payment':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md">
            <ArrowDownLeft className="w-3 h-3 text-emerald-600" />
            Payment
          </span>
        );
      case 'Quote':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-md">
            <Receipt className="w-3 h-3 text-amber-600" />
            Quote
          </span>
        );
      case 'Credit Note':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-700 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded-md">
            <ArrowUpRight className="w-3 h-3 text-rose-600" />
            Credit Note
          </span>
        );
      default:
        return <Badge variant="neutral" size="sm">{type}</Badge>;
    }
  };

  const getStatusBadge = (status: string) => {
    const s = status.toLowerCase();
    if (s === 'paid' || s === 'completed' || s === 'accepted') {
      return <Badge variant="success" size="sm" dot>{status}</Badge>;
    }
    if (s === 'pending' || s === 'sent') {
      return <Badge variant="warning" size="sm" dot>{status}</Badge>;
    }
    if (s === 'overdue') {
      return <Badge variant="danger" size="sm" dot>{status}</Badge>;
    }
    return <Badge variant="neutral" size="sm">{status}</Badge>;
  };

  return (
    <div className="space-y-4">
      {/* Top action and transaction summary */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3 flex-wrap text-xs text-slate-600">
          <div className="px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200/90">
            Total Records: <strong className="text-slate-900 ml-1">{transactions.length}</strong>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-blue-50 border border-blue-100 text-brand-800">
            Total Invoiced: <strong className="ml-1">{formatINR(project.billed)}</strong>
          </div>
        </div>

        <Button
          variant="primary"
          size="sm"
          leadingIcon={<Plus className="w-3.5 h-3.5" />}
          onClick={() => setIsInvoiceModalOpen(true)}
        >
          New Invoice
        </Button>
      </div>

      {/* Transactions Table */}
      <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs overflow-hidden">
        {transactions.length === 0 ? (
          <div className="p-12 text-center">
            <FileText className="w-8 h-8 text-slate-400 mx-auto mb-2" />
            <h4 className="text-sm font-semibold text-slate-800">No transactions recorded</h4>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              Quotes, progressive invoices, and payment settlements connected to this project will appear here.
            </p>
            <div className="mt-4">
              <Button
                variant="outline"
                size="sm"
                leadingIcon={<Plus className="w-3.5 h-3.5" />}
                onClick={() => setIsInvoiceModalOpen(true)}
              >
                Create First Invoice
              </Button>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 border-b border-slate-200 text-slate-500 uppercase tracking-wider font-semibold text-[10.5px]">
                <tr>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-3">Reference #</th>
                  <th className="py-3 px-3">Date</th>
                  <th className="py-3 px-3 text-right">Amount</th>
                  <th className="py-3 px-4 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {transactions.map((txn) => (
                  <tr key={txn.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3 px-4 whitespace-nowrap">
                      {getTypeBadge(txn.type)}
                    </td>
                    <td className="py-3 px-3 font-mono font-semibold text-slate-900">
                      {txn.reference}
                    </td>
                    <td className="py-3 px-3 text-slate-600 whitespace-nowrap tabular-nums">
                      {formatDate(txn.date)}
                    </td>
                    <td className="py-3 px-3 text-right font-bold text-slate-900 tabular-nums whitespace-nowrap">
                      {formatINR(txn.amount)}
                    </td>
                    <td className="py-3 px-4 text-center whitespace-nowrap">
                      {getStatusBadge(txn.status)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <CreateInvoiceModal
        isOpen={isInvoiceModalOpen}
        onClose={() => setIsInvoiceModalOpen(false)}
        onCreateInvoice={onCreateInvoice}
        defaultAmount={Math.max(0, project.budget - project.billed)}
      />
    </div>
  );
}
