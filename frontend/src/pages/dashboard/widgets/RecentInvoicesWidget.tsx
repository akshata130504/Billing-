import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { invoiceService } from '../../../services/invoiceService';
import { formatMoney, formatDate } from '../../../utils/format';
import type { Invoice } from '../../../types/invoices';
import type { PaymentOut } from '../../../types';

export interface RecentInvoicesWidgetProps {
  transactions?: PaymentOut[];
}

const statusBadgeStyles: Record<string, { bg: string; text: string; label: string }> = {
  PAID: { bg: 'bg-[#DDF4EA]', text: 'text-[#107548]', label: 'Paid' },
  SENT: { bg: 'bg-[#E8EBFC]', text: 'text-[#25247A]', label: 'Sent' },
  PARTIALLY_PAID: { bg: 'bg-[#F9D9E8]', text: 'text-[#E83E8C]', label: 'Partially Paid' },
  OVERDUE: { bg: 'bg-[#FCEBD9]', text: 'text-[#C05621]', label: 'Overdue' },
  DRAFT: { bg: 'bg-slate-100', text: 'text-slate-600', label: 'Draft' },
  VOID: { bg: 'bg-slate-100', text: 'text-slate-400', label: 'Void' },
};

export function RecentInvoicesWidget({ transactions: _transactions }: RecentInvoicesWidgetProps = {}) {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    invoiceService
      .listInvoices({ page_size: 5 })
      .then((res) => {
        if (mounted) setInvoices(res.items || []);
      })
      .catch((err) => {
        console.error('Failed to load recent invoices:', err);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="bg-white p-5 rounded-2xl border border-[#E7E9F2] shadow-sm space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-[#11194F] tracking-tight">
          Recent Invoices
        </h3>
        <Link
          to="/invoices"
          className="inline-flex items-center gap-1 text-xs font-semibold text-[#E83E8C] hover:text-[#D81B60] transition-colors"
        >
          <span>View all</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#F0F2FA] text-[11px] font-semibold text-[#7B829A]">
              <th className="py-2.5 px-3">Invoice #</th>
              <th className="py-2.5 px-3">Customer</th>
              <th className="py-2.5 px-3">Amount</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#F0F2FA] text-xs">
            {invoices.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-8 px-3 text-center text-slate-400 italic text-xs">
                  {loading ? 'Loading recent invoices...' : 'No invoices recorded yet.'}
                </td>
              </tr>
            ) : (
              invoices.map((inv) => {
                const sKey = (inv.status || 'DRAFT').toUpperCase();
                const badge = statusBadgeStyles[sKey] || {
                  bg: 'bg-slate-100',
                  text: 'text-slate-600',
                  label: inv.status,
                };
                const custName =
                  inv.customer?.display_name ||
                  inv.customer?.displayName ||
                  inv.customer?.name ||
                  'Customer';

                return (
                  <tr
                    key={inv.id}
                    className="hover:bg-[#F7F8FC]/70 transition-colors"
                  >
                    <td className="py-3 px-3">
                      <Link
                        to={`/invoices/${inv.id}`}
                        className="font-medium text-[#3F51C9] hover:underline font-mono text-xs"
                      >
                        {inv.invoice_number}
                      </Link>
                    </td>
                    <td className="py-3 px-3 font-semibold text-[#11194F]">
                      {custName}
                    </td>
                    <td className="py-3 px-3 font-semibold text-[#11194F] tabular-nums">
                      {formatMoney(inv.total ?? 0, inv.currency || 'INR')}
                    </td>
                    <td className="py-3 px-3">
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded-md text-[11px] font-semibold ${badge.bg} ${badge.text}`}
                      >
                        {badge.label}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-[#7B829A] text-[11px]">
                      {inv.issue_date || inv.invoice_date ? formatDate(inv.issue_date || inv.invoice_date!) : '—'}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
