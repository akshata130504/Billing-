import { PaymentFilterState } from '../types';
import { Search, RotateCcw } from 'lucide-react';

interface PaymentFiltersProps {
  filters: PaymentFilterState;
  onChange: (filters: PaymentFilterState) => void;
  onReset: () => void;
  customers: { id: string; name: string }[];
}

const PAYMENT_METHODS = [
  'UPI',
  'Credit Card',
  'Debit Card',
  'Bank Transfer',
  'Net Banking',
  'Cash',
  'Cheque',
  'Other',
];

const STATUS_OPTIONS = [
  { value: 'all', label: 'All Statuses' },
  { value: 'completed', label: 'Completed' },
  { value: 'pending', label: 'Pending' },
  { value: 'failed', label: 'Failed' },
  { value: 'partially_refunded', label: 'Partially Refunded' },
  { value: 'refunded', label: 'Refunded' },
];

export function PaymentFilters({
  filters,
  onChange,
  onReset,
  customers,
}: PaymentFiltersProps) {
  const isFiltered =
    filters.searchQuery.trim() !== '' ||
    filters.statusTab !== 'all' ||
    filters.customer !== 'all' ||
    filters.paymentMethod !== 'all' ||
    filters.status !== 'all' ||
    filters.sortBy !== 'newest';

  const handleChange = <K extends keyof PaymentFilterState>(
    key: K,
    value: PaymentFilterState[K]
  ) => {
    onChange({
      ...filters,
      [key]: value,
    });
  };

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl p-3 shadow-2xs space-y-2.5">
      {/* Search and Quick Tabs */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-2.5">
        {/* Search Bar */}
        <div className="relative w-full sm:max-w-xs">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={filters.searchQuery}
            onChange={(e) => handleChange('searchQuery', e.target.value)}
            placeholder="Search payment #, ref, customer..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50/70 border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 transition-colors"
          />
        </div>

        {/* View Tabs */}
        <div className="flex items-center gap-2 self-end sm:self-auto shrink-0 flex-wrap">
          <div className="inline-flex items-center p-0.5 bg-slate-100/90 rounded-lg border border-slate-200/80">
            {(['all', 'completed', 'pending', 'failed', 'refunded'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => handleChange('statusTab', tab)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
                  filters.statusTab === tab
                    ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                {tab === 'all' ? 'All' : tab}
              </button>
            ))}
          </div>

          {isFiltered && (
            <button
              type="button"
              onClick={onReset}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200/70 rounded-lg transition-colors"
              title="Reset all filters"
            >
              <RotateCcw className="w-3 h-3 shrink-0" />
              <span>Clear</span>
            </button>
          )}
        </div>
      </div>

      {/* Dropdown Filters Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 border-t border-slate-100">
        {/* Customer */}
        <div>
          <select
            value={filters.customer}
            onChange={(e) => handleChange('customer', e.target.value)}
            className="w-full py-1 px-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            <option value="all">All Customers</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        {/* Payment Method */}
        <div>
          <select
            value={filters.paymentMethod}
            onChange={(e) => handleChange('paymentMethod', e.target.value)}
            className="w-full py-1 px-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            <option value="all">All Payment Methods</option>
            {PAYMENT_METHODS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>

        {/* Status */}
        <div>
          <select
            value={filters.status}
            onChange={(e) => handleChange('status', e.target.value)}
            className="w-full py-1 px-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            {STATUS_OPTIONS.map((st) => (
              <option key={st.value} value={st.value}>
                {st.label}
              </option>
            ))}
          </select>
        </div>

        {/* Sort By */}
        <div>
          <select
            value={filters.sortBy}
            onChange={(e) =>
              handleChange('sortBy', e.target.value as PaymentFilterState['sortBy'])
            }
            className="w-full py-1 px-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            <option value="newest">Sort: Newest</option>
            <option value="oldest">Sort: Oldest</option>
            <option value="amount_high">Highest Amount</option>
            <option value="amount_low">Lowest Amount</option>
          </select>
        </div>
      </div>
    </div>
  );
}
