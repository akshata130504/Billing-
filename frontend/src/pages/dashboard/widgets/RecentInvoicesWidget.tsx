import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

interface RecentInvoiceItem {
  id: string;
  invoiceNumber: string;
  customerName: string;
  amount: string;
  status: 'Paid' | 'Pending' | 'Overdue';
  date: string;
}

const DEFAULT_RECENT_INVOICES: RecentInvoiceItem[] = [
  {
    id: '1',
    invoiceNumber: 'INV-2025-001',
    customerName: 'Acme Corp',
    amount: '₹ 48,000',
    status: 'Paid',
    date: 'Sep 6, 2025',
  },
  {
    id: '2',
    invoiceNumber: 'INV-2025-002',
    customerName: 'Bright Studio',
    amount: '₹ 32,000',
    status: 'Pending',
    date: 'Sep 5, 2025',
  },
  {
    id: '3',
    invoiceNumber: 'INV-2025-003',
    customerName: 'CloudTech',
    amount: '₹ 1,20,000',
    status: 'Overdue',
    date: 'Sep 3, 2025',
  },
  {
    id: '4',
    invoiceNumber: 'INV-2025-004',
    customerName: 'Nova Systems',
    amount: '₹ 56,000',
    status: 'Paid',
    date: 'Sep 1, 2025',
  },
  {
    id: '5',
    invoiceNumber: 'INV-2025-005',
    customerName: 'Zenith Media',
    amount: '₹ 28,000',
    status: 'Pending',
    date: 'Aug 30, 2025',
  },
];

const statusStyles: Record<RecentInvoiceItem['status'], { bg: string; text: string }> = {
  Paid: {
    bg: 'bg-[#DDF4EA]',
    text: 'text-[#107548]',
  },
  Pending: {
    bg: 'bg-[#F9D9E8]',
    text: 'text-[#E83E8C]',
  },
  Overdue: {
    bg: 'bg-[#FCEBD9]',
    text: 'text-[#C05621]',
  },
};

import type { PaymentOut } from '../../../types';

export interface RecentInvoicesWidgetProps {
  transactions?: PaymentOut[];
}

export function RecentInvoicesWidget({ transactions: _transactions }: RecentInvoicesWidgetProps = {}) {
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
            {DEFAULT_RECENT_INVOICES.map((inv) => {
              const badgeStyle = statusStyles[inv.status];
              return (
                <tr
                  key={inv.id}
                  className="hover:bg-[#F7F8FC]/70 transition-colors"
                >
                  <td className="py-3 px-3">
                    <Link
                      to="/invoices"
                      className="font-medium text-[#3F51C9] hover:underline font-mono text-xs"
                    >
                      {inv.invoiceNumber}
                    </Link>
                  </td>
                  <td className="py-3 px-3 font-semibold text-[#11194F]">
                    {inv.customerName}
                  </td>
                  <td className="py-3 px-3 font-semibold text-[#11194F] tabular-nums">
                    {inv.amount}
                  </td>
                  <td className="py-3 px-3">
                    <span
                      className={`inline-block px-2.5 py-0.5 rounded-md text-[11px] font-semibold ${badgeStyle.bg} ${badgeStyle.text}`}
                    >
                      {inv.status}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-[#7B829A] text-[11px]">
                    {inv.date}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
