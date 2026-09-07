import { ExpenseFilterState } from '../types';
import { Search, RotateCcw, LayoutList, LayoutGrid } from 'lucide-react';
import { mockCustomers } from '../mockExpenses';

interface ExpenseFiltersProps {
  filters: ExpenseFilterState;
  onChange: (filters: ExpenseFilterState) => void;
  onReset: () => void;
  availableProjects: string[];
}

const CATEGORIES = [
  'Travel',
  'Meals',
  'Office Supplies',
  'Software',
  'Cloud Services',
  'Advertising',
  'Utilities',
  'Equipment',
  'Professional Services',
  'Other',
];

const STATUSES = [
  { value: 'all', label: 'All Statuses' },
  { value: 'recorded', label: 'Recorded' },
  { value: 'billable', label: 'Billable' },
  { value: 'invoiced', label: 'Invoiced' },
  { value: 'reimbursed', label: 'Reimbursed' },
  { value: 'draft', label: 'Draft' },
  { value: 'cancelled', label: 'Cancelled' },
];

export function ExpenseFilters({
  filters,
  onChange,
  onReset,
  availableProjects,
}: ExpenseFiltersProps) {
  const isFiltered =
    filters.searchQuery.trim() !== '' ||
    filters.status !== 'all' ||
    filters.customer !== 'all' ||
    filters.project !== 'all' ||
    filters.category !== 'all' ||
    filters.billable !== 'all' ||
    filters.sortBy !== 'newest';

  const handleChange = (key: keyof ExpenseFilterState, value: any) => {
    onChange({
      ...filters,
      [key]: value,
    });
  };

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl p-3 shadow-2xs space-y-2.5">
      {/* Search & Top Actions */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-2.5">
        {/* Search Bar */}
        <div className="relative w-full sm:max-w-md">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={filters.searchQuery}
            onChange={(e) => handleChange('searchQuery', e.target.value)}
            placeholder="Search by expense, customer, project or ID..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50/70 border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 transition-colors"
          />
        </div>

        {/* View Mode & Reset Button */}
        <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
          {isFiltered && (
            <button
              type="button"
              onClick={onReset}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200/70 rounded-lg transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Clear Filters</span>
            </button>
          )}

          {/* List vs Card View Toggle */}
          <div className="inline-flex items-center p-0.5 bg-slate-100/90 rounded-lg border border-slate-200/80">
            <button
              type="button"
              onClick={() => handleChange('viewMode', 'list')}
              className={`p-1 rounded-md text-xs font-medium transition-colors ${
                filters.viewMode === 'list'
                  ? 'bg-white text-slate-900 shadow-2xs'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
              title="List View"
            >
              <LayoutList className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => handleChange('viewMode', 'card')}
              className={`p-1 rounded-md text-xs font-medium transition-colors ${
                filters.viewMode === 'card'
                  ? 'bg-white text-slate-900 shadow-2xs'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
              title="Card View"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Filter Selects Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 pt-1 border-t border-slate-100">
        {/* Status */}
        <div>
          <select
            value={filters.status}
            onChange={(e) => handleChange('status', e.target.value)}
            className="w-full py-1 px-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            {STATUSES.map((st) => (
              <option key={st.value} value={st.value}>
                {st.label}
              </option>
            ))}
          </select>
        </div>

        {/* Customer */}
        <div>
          <select
            value={filters.customer}
            onChange={(e) => handleChange('customer', e.target.value)}
            className="w-full py-1 px-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            <option value="all">All Customers</option>
            {mockCustomers.map((cust) => (
              <option key={cust} value={cust}>
                {cust}
              </option>
            ))}
          </select>
        </div>

        {/* Project */}
        <div>
          <select
            value={filters.project}
            onChange={(e) => handleChange('project', e.target.value)}
            className="w-full py-1 px-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            <option value="all">All Projects</option>
            {availableProjects.map((proj) => (
              <option key={proj} value={proj}>
                {proj}
              </option>
            ))}
          </select>
        </div>

        {/* Category */}
        <div>
          <select
            value={filters.category}
            onChange={(e) => handleChange('category', e.target.value)}
            className="w-full py-1 px-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            <option value="all">All Categories</option>
            {CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>

        {/* Billable */}
        <div>
          <select
            value={filters.billable}
            onChange={(e) => handleChange('billable', e.target.value)}
            className="w-full py-1 px-2 text-xs bg-white border border-slate-200 rounded-lg text-slate-700 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            <option value="all">All Types</option>
            <option value="billable">Billable</option>
            <option value="non_billable">Non-Billable</option>
          </select>
        </div>

        {/* Sort By */}
        <div>
          <select
            value={filters.sortBy}
            onChange={(e) => handleChange('sortBy', e.target.value)}
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
