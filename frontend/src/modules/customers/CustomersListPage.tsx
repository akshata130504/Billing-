import { useCallback, useEffect, useMemo, useState, type MouseEvent } from 'react';
import type { ReactNode } from 'react';
import {
  CUSTOMERS_COLUMN_DEFS,
  CUSTOMERS_EMPTY_DEFAULTS,
  CUSTOMERS_HEADER_DEFAULTS,
  CUSTOMERS_STAT_DEFS,
  resolveList,
  visible,
} from '../../appUi/registry';
import { usePageUi, useUiEditable } from '../../appUi/UiConfigContext';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Building2, Plus, RefreshCw, Search, UserCheck, UserX, Users, X } from 'lucide-react';
import { customerService } from '../../services/customerService';
import { isCreateRequested } from '../../hooks/useCreateDeepLink';
import type { CustomerListParams, CustomerOut, CustomerStatus } from '../../types/api';
import type { CustomerSortKey } from '../../types/customers';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { DataTable, type Column } from '../../components/common/DataTable';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { PageHeader } from '../../components/common/PageHeader';
import { StatCard } from '../../components/common/StatCard';
import { useAuth } from '../../hooks/useAuth';
import { formatDate, humanize, statusVariant } from '../../utils/format';

const PAGE_SIZE = 20;

const SORT_OPTIONS: { value: CustomerSortKey; label: string }[] = [
  { value: '-created_at', label: 'Newest first' },
  { value: 'created_at', label: 'Oldest first' },
  { value: 'display_name', label: 'Name A–Z' },
  { value: '-display_name', label: 'Name Z–A' },
  { value: 'customer_number', label: 'Customer number' },
  { value: '-updated_at', label: 'Recently updated' },
];

interface CustomerCounts {
  total: number;
  active: number;
  inactive: number;
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(handle);
  }, [value, delayMs]);
  return debounced;
}

export function CustomersListPage() {
  const ui = usePageUi('customers');
  const editable = useUiEditable();
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const canWrite = hasRole('finance');

  // Quick-action deep link (`/customers?action=new`): open the create form.
  const [searchParams] = useSearchParams();
  const createRequested = isCreateRequested(searchParams);
  useEffect(() => {
    if (createRequested && canWrite) navigate('/customers/new', { replace: true });
  }, [createRequested, canWrite, navigate]);

  const [items, setItems] = useState<CustomerOut[]>([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<CustomerCounts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<'all' | CustomerStatus>('all');
  const [sort, setSort] = useState<CustomerSortKey>('-created_at');
  const [page, setPage] = useState(1);

  const debouncedSearch = useDebouncedValue(search.trim(), 300);
  const hasFilters = debouncedSearch !== '' || status !== 'all';

  // Reset to the first page whenever a filter changes.
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, status, sort]);

  const loadCounts = useCallback(async () => {
    try {
      const [all, active, inactive] = await Promise.all([
        customerService.list({ page: 1, page_size: 1 }),
        customerService.list({ page: 1, page_size: 1, status: 'active' }),
        customerService.list({ page: 1, page_size: 1, status: 'inactive' }),
      ]);
      setCounts({ total: all.total, active: active.total, inactive: inactive.total });
    } catch {
      // Counts are non-blocking; the table error state covers the primary failure.
    }
  }, []);

  const loadCustomers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: CustomerListParams = {
        page,
        page_size: PAGE_SIZE,
        sort,
        search: debouncedSearch || undefined,
        status: status === 'all' ? undefined : status,
      };
      const data = await customerService.list(params);
      setItems(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setError(err?.message || 'Failed to load customers');
    } finally {
      setLoading(false);
    }
  }, [page, sort, debouncedSearch, status]);

  useEffect(() => {
    loadCustomers();
  }, [loadCustomers]);

  useEffect(() => {
    loadCounts();
  }, [loadCounts]);

  const refresh = () => {
    loadCustomers();
    loadCounts();
  };

  const clearFilters = () => {
    setSearch('');
    setStatus('all');
  };

  // DataTable has no row-click prop; delegate clicks from the wrapper to the row's customer.
  const handleTableClick = (event: MouseEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (target.closest('a, button')) return;
    const row = target.closest('tbody tr');
    if (!row || !row.parentElement) return;
    const index = Array.from(row.parentElement.children).indexOf(row);
    const customer = items[index];
    if (customer) navigate(`/customers/${customer.id}`);
  };

  const columns = useMemo<Column<CustomerOut>[]>(
    () => [
      {
        key: 'customer_number',
        title: 'Customer #',
        className: 'whitespace-nowrap',
        render: (c) => (
          <span className="font-mono text-xs font-medium text-slate-600">{c.customer_number}</span>
        ),
      },
      {
        key: 'display_name',
        title: 'Customer',
        render: (c) => (
          <div className="min-w-0">
            <Link
              to={`/customers/${c.id}`}
              className="font-semibold text-slate-900 hover:text-brand-600 transition-colors"
            >
              {c.display_name}
            </Link>
            <div className="text-xs text-slate-500 truncate">{c.email || 'No email'}</div>
          </div>
        ),
      },
      {
        key: 'company_name',
        title: 'Company / GSTIN',
        render: (c) => (
          <div className="min-w-0">
            <div className="text-slate-800 truncate">{c.company_name || '—'}</div>
            <div className="text-xs text-slate-500 font-mono">{c.gstin || 'No GSTIN'}</div>
          </div>
        ),
      },
      {
        key: 'status',
        title: 'Status',
        render: (c) => (
          <Badge variant={statusVariant(c.status)} size="sm" dot>
            {humanize(c.status)}
          </Badge>
        ),
      },
      {
        key: 'terms',
        title: 'Currency / Terms',
        className: 'whitespace-nowrap',
        render: (c) => (
          <div>
            <div className="text-slate-800 font-medium">{c.currency}</div>
            <div className="text-xs text-slate-500">
              {c.payment_terms_days === 0 ? 'Due on receipt' : `Net ${c.payment_terms_days}`}
            </div>
          </div>
        ),
      },
      {
        key: 'created_at',
        title: 'Created',
        className: 'whitespace-nowrap',
        render: (c) => <span className="text-slate-600">{formatDate(c.created_at)}</span>,
      },
    ],
    []
  );
  // Visual-editor configuration: column order, labels and visibility over the defaults.
  const configuredColumns = useMemo(() => {
    const byUiKey: Record<string, Column<CustomerOut> | undefined> = {
      customer_number: columns.find((c) => c.key === 'customer_number'),
      customer: columns.find((c) => c.key === 'display_name'),
      company: columns.find((c) => c.key === 'company_name'),
      status: columns.find((c) => c.key === 'status'),
      currency_terms: columns.find((c) => c.key === 'terms'),
      created: columns.find((c) => c.key === 'created_at'),
    };
    return visible(resolveList(CUSTOMERS_COLUMN_DEFS, ui.columns))
      .map((item) => {
        const column = byUiKey[item.key];
        return column ? { ...column, title: item.label } : null;
      })
      .filter((c): c is Column<CustomerOut> => c !== null);
  }, [columns, ui.columns]);
  const renderStat = (key: string, title: string): ReactNode => {
    switch (key) {
      case 'total':
        return <StatCard title={title} value={counts ? counts.total : '—'} icon={<Users className="w-4 h-4" />} />;
      case 'active':
        return <StatCard title={title} value={counts ? counts.active : '—'} icon={<UserCheck className="w-4 h-4" />} />;
      case 'inactive':
        return <StatCard title={title} value={counts ? counts.inactive : '—'} icon={<UserX className="w-4 h-4" />} />;
      case 'matching':
        return (
          <StatCard
            title={title}
            value={loading && items.length === 0 ? '—' : total}
            comparisonText={hasFilters ? 'Search and status filters applied' : 'No filters applied'}
            icon={<Building2 className="w-4 h-4" />}
          />
        );
      default:
        return null;
    }
  };
  const configuredStats = visible(resolveList(CUSTOMERS_STAT_DEFS, ui.stats));

  const showEmptyState = !loading && !error && items.length === 0;

  return (
    <div className="space-y-6 pb-12">
      <div {...editable('customers.header')}>
      <PageHeader
        eyebrow={ui.header?.eyebrow ?? CUSTOMERS_HEADER_DEFAULTS.eyebrow}
        title={ui.header?.title ?? CUSTOMERS_HEADER_DEFAULTS.title}
        subtitle={ui.header?.subtitle ?? CUSTOMERS_HEADER_DEFAULTS.subtitle}
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={refresh}
              leadingIcon={<RefreshCw className="w-4 h-4" />}
            >
              Refresh
            </Button>
            {canWrite && (
              <Button
                variant="primary"
                size="sm"
                onClick={() => navigate('/customers/new')}
                leadingIcon={<Plus className="w-4 h-4" />}
              >
                New Customer
              </Button>
            )}
          </>
        }
      />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {configuredStats.map((stat) => (
          <div key={stat.key} {...editable(`customers.stat.${stat.key}`)}>
            {renderStat(stat.key, stat.label)}
          </div>
        ))}
      </div>

      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex flex-col md:flex-row gap-3 md:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search by name, company, email or customer number..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-9 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 focus:bg-white transition-colors"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                aria-label="Clear search"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 rounded text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as 'all' | CustomerStatus)}
              aria-label="Filter by status"
              className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as CustomerSortKey)}
              aria-label="Sort customers"
              className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                Clear
              </Button>
            )}
          </div>
        </div>
      </div>

      {error ? (
        <ErrorState title="Could not load customers" message={error} onRetry={loadCustomers} />
      ) : showEmptyState ? (
        hasFilters ? (
          <EmptyState
            icon={<Search className="w-6 h-6 stroke-1" />}
            title="No customers match these filters"
            description="Try a different search term or clear the status filter to see every customer."
            action={
              <Button variant="outline" size="sm" onClick={clearFilters}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <div {...editable('customers.empty')}>
          <EmptyState
            icon={<Users className="w-6 h-6 stroke-1" />}
            title={ui.empty?.title ?? CUSTOMERS_EMPTY_DEFAULTS.title}
            description={ui.empty?.description ?? CUSTOMERS_EMPTY_DEFAULTS.description}
            action={
              canWrite ? (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => navigate('/customers/new')}
                  leadingIcon={<Plus className="w-4 h-4" />}
                >
                  New Customer
                </Button>
              ) : undefined
            }
          />
          </div>
        )
      ) : (
        <div {...editable('customers.columns')} onClick={handleTableClick} className="[&_tbody_tr]:cursor-pointer">
          <DataTable<CustomerOut>
            columns={configuredColumns}
            data={items}
            keyExtractor={(c) => c.id}
            isLoading={loading}
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onPageChange={setPage}
            emptyMessage="No customers found"
            emptySubtext="Adjust your filters or add a new customer."
          />
        </div>
      )}
    </div>
  );
}

export default CustomersListPage;
