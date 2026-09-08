import { CreditCard } from 'lucide-react';
import type { PaymentOut } from '../../../types';
import { Badge } from '../../../components/common/Badge';
import { formatDateTime, formatMoney, humanize, statusVariant } from '../../../utils/format';

export interface RecentTransactionsWidgetProps {
  transactions: PaymentOut[];
}

export function RecentTransactionsWidget({ transactions }: RecentTransactionsWidgetProps) {
  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            Recent Transactions
          </h3>
          <p className="text-xs text-slate-400">
            Latest payments recorded across every gateway
          </p>
        </div>
      </div>

      {transactions.length === 0 ? (
        <p className="text-xs text-slate-400 py-8 text-center">No payments recorded yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-100 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                <th className="py-2.5 px-3">Payment</th>
                <th className="py-2.5 px-3">Customer</th>
                <th className="py-2.5 px-3">Method</th>
                <th className="py-2.5 px-3">Amount</th>
                <th className="py-2.5 px-3">Date</th>
                <th className="py-2.5 px-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {transactions.map((tx) => (
                <tr key={tx.id} className="hover:bg-slate-50/70 transition-colors">
                  <td className="py-3 px-3 font-mono font-bold text-slate-900">
                    {tx.payment_number}
                  </td>
                  <td className="py-3 px-3 font-semibold text-slate-800">
                    {tx.customer?.display_name ?? '—'}
                  </td>
                  <td className="py-3 px-3 text-slate-600">
                    <div className="flex items-center gap-1.5">
                      <CreditCard className="w-3.5 h-3.5 text-slate-400" />
                      <span>{humanize(tx.method)}</span>
                    </div>
                  </td>
                  <td className="py-3 px-3 font-bold text-slate-900 tabular-nums">
                    {formatMoney(tx.amount, tx.currency)}
                  </td>
                  <td className="py-3 px-3 text-slate-400 text-[11px]">
                    {formatDateTime(tx.paid_at ?? tx.created_at)}
                  </td>
                  <td className="py-3 px-3">
                    <Badge variant={statusVariant(tx.status)} size="sm">
                      {humanize(tx.status)}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
