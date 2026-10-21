import { ProjectFilterState } from '../types';
import { Card, CardContent } from '../../../components/common/Card';
import { Button } from '../../../components/common/Button';
import { Search, X, Filter, LayoutList, LayoutGrid } from 'lucide-react';
import { usePageSpec } from '../../../appUi/usePageSpec';

interface ProjectFiltersProps {
  filters: ProjectFilterState;
  onFilterChange: (updates: Partial<ProjectFilterState>) => void;
  onClearFilters: () => void;
  customerOptions: string[];
}

export function ProjectFilters({
  filters,
  onFilterChange,
  onClearFilters,
  customerOptions,
}: ProjectFiltersProps) {
  const ui = usePageSpec('projects');
  const isFiltered =
    filters.searchQuery !== '' ||
    filters.statusTab !== 'all' ||
    filters.customer !== 'all';

  return (
    <Card className="border-slate-200/90 shadow-2xs">
      <CardContent className="p-3 space-y-3">
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          {/* Status Quick Pills: All | Active | Inactive */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 scrollbar-none" {...ui.edit('tabs')}>
            {ui.shown('tabs').map((tab) => {
              const isSelected = filters.statusTab === tab.key;
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => onFilterChange({ statusTab: tab.key as any })}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer select-none ${
                    isSelected
                      ? 'bg-slate-900 text-white shadow-2xs'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                  {...ui.edit(`tabs.${tab.key}`)}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Controls: Search, Customer, View Mode Toggle, Clear */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
            {/* Search Input */}
            <div className="relative min-w-[200px] sm:w-60">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <input
                type="text"
                placeholder="Search project or customer..."
                value={filters.searchQuery}
                onChange={(e) => onFilterChange({ searchQuery: e.target.value })}
                className="w-full pl-9 pr-7 py-1.5 text-xs bg-slate-50 hover:bg-slate-100/70 focus:bg-white border border-slate-200/90 rounded-lg text-slate-900 placeholder:text-slate-400 outline-none transition-colors"
              />
              {filters.searchQuery && (
                <button
                  type="button"
                  onClick={() => onFilterChange({ searchQuery: '' })}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-0.5"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Customer Filter */}
            <div className="relative min-w-[150px]">
              <select
                value={filters.customer}
                onChange={(e) => onFilterChange({ customer: e.target.value })}
                className="w-full py-1.5 pl-3 pr-7 text-xs bg-slate-50 hover:bg-slate-100/70 border border-slate-200/90 rounded-lg text-slate-700 outline-none transition-colors cursor-pointer appearance-none"
              >
                <option value="all">All Customers</option>
                {customerOptions.map((cust) => (
                  <option key={cust} value={cust}>
                    {cust}
                  </option>
                ))}
              </select>
              <Filter className="w-3.5 h-3.5 absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            </div>

            {/* View Mode Toggle: List / Card */}
            <div className="flex items-center bg-slate-100 p-0.5 rounded-lg border border-slate-200 shrink-0">
              <button
                type="button"
                onClick={() => onFilterChange({ viewMode: 'list' })}
                className={`p-1.5 rounded-md transition-colors ${
                  filters.viewMode === 'list'
                    ? 'bg-white text-brand-600 shadow-2xs font-semibold'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
                title="List View"
                aria-label="List View"
              >
                <LayoutList className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => onFilterChange({ viewMode: 'card' })}
                className={`p-1.5 rounded-md transition-colors ${
                  filters.viewMode === 'card'
                    ? 'bg-white text-brand-600 shadow-2xs font-semibold'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
                title="Card View"
                aria-label="Card View"
              >
                <LayoutGrid className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Clear Filters Button */}
            {isFiltered && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onClearFilters}
                className="text-slate-500 hover:text-rose-600 text-xs shrink-0"
              >
                <X className="w-3.5 h-3.5 mr-1" />
                Clear
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
