import type { ProjectInvoiceInput } from '../../../services/projectService';
import { useState } from 'react';
import { Project } from '../types';
import { formatINR } from '../format';
import { formatDate } from './ProjectTable';
import { CreateInvoiceModal } from './CreateInvoiceModal';
import { Button } from '../../../components/common/Button';
import { Badge } from '../../../components/common/Badge';
import { Plus, FileText } from 'lucide-react';

interface ProjectInvoicesProps {
  project: Project;
  onCreateInvoice: (invoice: ProjectInvoiceInput) => Promise<boolean> | boolean | void;
}

export function ProjectInvoices({ project, onCreateInvoice }: ProjectInvoicesProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const invoices = project.invoices || [];
  const invoicedTotal = invoices.reduce((acc, inv) => acc + inv.amount, 0);
  const paidTotal = invoices
    .filter((inv) => inv.status === 'paid')
    .reduce((acc, inv) => acc + inv.amount, 0);
  const balanceDue = Math.max(0, invoicedTotal - paidTotal);

  return (
    <div className="space-y-4">
      {/* Top metrics bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200/90 text-xs text-slate-700">
            Total Invoiced: <strong className="text-slate-900 ml-1">{formatINR(invoicedTotal)}</strong>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-100 text-xs text-emerald-800">
            Paid to Date: <strong className="ml-1">{formatINR(paidTotal)}</strong>
          </div>
          <div className="px-3 py-1.5 rounded-xl bg-amber-50 border border-amber-100 text-xs text-amber-800">
            Balance Due: <strong className="ml-1">{formatINR(balanceDue)}</strong>
          </div>
        </div>

        <Button
          variant="primary"
          size="sm"
          leadingIcon={<Plus className="w-3.5 h-3.5" />}
          onClick={() => setIsModalOpen(true)}
        >
          Create Invoice
        </Button>
      </div>

      {/* Invoices Table */}
      <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs overflow-hidden">
        {invoices.length === 0 ? (
          <div className="p-12 text-center">
            <FileText className="w-8 h-8 text-slate-400 mx-auto mb-2" />
            <h4 className="text-sm font-semibold text-slate-800">No project invoices issued yet</h4>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              Issue progressive milestone billing to draw down on the agreed project budget.
            </p>
            <div className="mt-4">
              <Button
                variant="outline"
                size="sm"
                leadingIcon={<Plus className="w-3.5 h-3.5" />}
                onClick={() => setIsModalOpen(true)}
              >
                Generate Milestone Invoice
              </Button>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 border-b border-slate-200 text-slate-500 uppercase tracking-wider font-semibold text-[10.5px]">
                <tr>
                  <th className="py-3 px-4">Invoice #</th>
                  <th className="py-3 px-3">Date</th>
                  <th className="py-3 px-3">Due Date</th>
                  <th className="py-3 px-3 text-right">Amount</th>
                  <th className="py-3 px-4 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {invoices.map((inv) => (
                  <tr key={inv.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3 px-4 font-mono font-bold text-slate-900">
                      {inv.invoiceNumber}
                    </td>
                    <td className="py-3 px-3 text-slate-600 whitespace-nowrap tabular-nums">
                      {formatDate(inv.date)}
                    </td>
                    <td className="py-3 px-3 text-slate-600 whitespace-nowrap tabular-nums">
                      {formatDate(inv.dueDate)}
                    </td>
                    <td className="py-3 px-3 text-right font-bold text-slate-900 tabular-nums whitespace-nowrap">
                      {formatINR(inv.amount)}
                    </td>
                    <td className="py-3 px-4 text-center whitespace-nowrap">
                      <Badge
                        variant={
                          inv.status === 'paid'
                            ? 'success'
                            : inv.status === 'pending'
                            ? 'warning'
                            : inv.status === 'overdue'
                            ? 'danger'
                            : 'neutral'
                        }
                        size="sm"
                        dot={inv.status !== 'draft'}
                      >
                        {inv.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <CreateInvoiceModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreateInvoice={onCreateInvoice}
        defaultAmount={Math.max(0, project.budget - project.billed)}
      />
    </div>
  );
}
