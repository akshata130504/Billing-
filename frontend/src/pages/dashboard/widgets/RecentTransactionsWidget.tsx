import { ArrowRight, CreditCard } from 'lucide-react';
import { mockRecentTransactions, TransactionItem } from '../mockDashboardData';
import { useToast } from '../../../components/common/Toast';

export function RecentTransactionsWidget() {
  const { showToast } = useToast();

  const getStatusBadge = (status: TransactionItem['status']) => {
    switch (status) {
      case 'settled':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100/80 text-emerald-800">
            Settled
          </span>
        );
      case 'processing':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-100/80 text-blue-800">
            Processing
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-100/80 text-rose-800">
            Failed
          </span>
        );
      case 'refunded':
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-purple-100/80 text-purple-800">
            Refunded
          </span>
        );
    }
  };

  return (
    <div className="bg-white p-5 rounded-2xl border border-slate-200/90 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            Recent Transactions
          </h3>
          <p className="text-xs text-slate-400">
            Gateway payouts, webhooks & direct settlements
          </p>
        </div>
        <button
          type="button"
          onClick={() => showToast('info', 'Payments Ledger', 'Opening full payment ledger')}
          className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700"
        >
          <span>View All</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-100 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
              <th className="py-2.5 px-3">Transaction</th>
              <th className="py-2.5 px-3">Customer</th>
              <th className="py-2.5 px-3">Invoice</th>
              <th className="py-2.5 px-3">Method</th>
              <th className="py-2.5 px-3">Amount</th>
              <th className="py-2.5 px-3">Date</th>
              <th className="py-2.5 px-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-xs">
            {mockRecentTransactions.map((tx) => (
              <tr key={tx.id} className="hover:bg-slate-50/70 transition-colors">
                <td className="py-3 px-3 font-mono font-bold text-slate-900">
                  {tx.txHash}
                </td>
                <td className="py-3 px-3 font-semibold text-slate-800">
                  {tx.customerName}
                </td>
                <td className="py-3 px-3 text-slate-500 font-mono">
                  {tx.invoiceNumber}
                </td>
                <td className="py-3 px-3 text-slate-600">
                  <div className="flex items-center gap-1.5">
                    <CreditCard className="w-3.5 h-3.5 text-slate-400" />
                    <span>{tx.paymentMethod}</span>
                  </div>
                </td>
                <td className="py-3 px-3 font-bold text-slate-900 tabular-nums">
                  {tx.amount}
                </td>
                <td className="py-3 px-3 text-slate-400 text-[11px]">
                  {tx.date}
                </td>
                <td className="py-3 px-3">
                  {getStatusBadge(tx.status)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
