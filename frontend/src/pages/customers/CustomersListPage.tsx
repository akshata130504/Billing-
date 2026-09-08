import { useCallback, useEffect, useMemo, useState, type MouseEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Building2, Plus, RefreshCw, Search, UserCheck, UserX, Users, X } from 'lucide-react';
import { customerService } from '../../services/customerService';
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
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const canWrite = hasRole('finance');

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

  const showEmptyState = !loading && !error && items.length === 0;

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        eyebrow="Workspace"
        title="Customers"
        subtitle="Every organisation and individual you bill. Open a customer to see contacts, invoices, payments and subscriptions in one place."
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

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total customers"
          value={counts ? counts.total : '—'}
          icon={<Users className="w-4 h-4" />}
        />
        <StatCard
          title="Active"
          value={counts ? counts.active : '—'}
          icon={<UserCheck className="w-4 h-4" />}
        />
        <StatCard
          title="Inactive"
          value={counts ? counts.inactive : '—'}
          icon={<UserX className="w-4 h-4" />}
        />
        <StatCard
          title="Matching filters"
          value={loading && items.length === 0 ? '—' : total}
          comparisonText={hasFilters ? 'Search and status filters applied' : 'No filters applied'}
          icon={<Building2 className="w-4 h-4" />}
        />
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
          <EmptyState
            icon={<Users className="w-6 h-6 stroke-1" />}
            title="No customers yet"
            description="Customers are the organisations and people you invoice. Add your first customer to start creating quotes, invoices and subscriptions."
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
        )
      ) : (
        <div onClick={handleTableClick} className="[&_tbody_tr]:cursor-pointer">
          <DataTable<CustomerOut>
            columns={columns}
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
