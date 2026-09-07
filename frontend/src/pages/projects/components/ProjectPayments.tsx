import { Project } from '../types';
import { formatINR } from '../mockProjects';
import { formatDate } from './ProjectTable';
import { Badge } from '../../../components/common/Badge';
import { CreditCard } from 'lucide-react';

interface ProjectPaymentsProps {
  project: Project;
}

export function ProjectPayments({ project }: ProjectPaymentsProps) {
  const payments = project.payments || [];
  const totalReceived = payments
    .filter((p) => p.status === 'completed')
    .reduce((acc, p) => acc + p.amount, 0);

  return (
    <div className="space-y-4">
      {/* Top metrics bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-100 text-xs text-emerald-800">
          Total Settled: <strong className="ml-1">{formatINR(totalReceived)}</strong>
        </div>
        <div className="px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200/90 text-xs text-slate-700">
          Receipts: <strong className="text-slate-900 ml-1">{payments.length} transactions</strong>
        </div>
      </div>

      {/* Payments Table */}
      <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs overflow-hidden">
        {payments.length === 0 ? (
          <div className="p-12 text-center">
            <CreditCard className="w-8 h-8 text-slate-400 mx-auto mb-2" />
            <h4 className="text-sm font-semibold text-slate-800">No payment receipts logged</h4>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              Payments recorded against issued invoices will automatically appear in this settlement ledger.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 border-b border-slate-200 text-slate-500 uppercase tracking-wider font-semibold text-[10.5px]">
                <tr>
                  <th className="py-3 px-4">Payment Date</th>
                  <th className="py-3 px-3">Reference</th>
                  <th className="py-3 px-3">Invoice</th>
                  <th className="py-3 px-3">Method</th>
                  <th className="py-3 px-3 text-right">Amount</th>
                  <th className="py-3 px-4 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {payments.map((pay) => (
                  <tr key={pay.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3 px-4 text-slate-600 whitespace-nowrap tabular-nums">
                      {formatDate(pay.paymentDate)}
                    </td>
                    <td className="py-3 px-3 font-mono font-medium text-slate-800">
                      {pay.reference}
                    </td>
                    <td className="py-3 px-3 font-mono text-brand-600">
                      {pay.invoiceNumber}
                    </td>
                    <td className="py-3 px-3 text-slate-600 whitespace-nowrap">
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 text-[11px] font-medium text-slate-700">
                        {pay.method}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-right font-bold text-slate-900 tabular-nums whitespace-nowrap">
                      {formatINR(pay.amount)}
                    </td>
                    <td className="py-3 px-4 text-center whitespace-nowrap">
                      <Badge
                        variant={pay.status === 'completed' ? 'success' : 'warning'}
                        size="sm"
                        dot
                      >
                        {pay.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
