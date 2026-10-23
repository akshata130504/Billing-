import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Search, SlidersHorizontal } from 'lucide-react';
import { Card, CardContent } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { DataTable, type Column } from '../../components/common/DataTable';
import { ErrorState } from '../../components/common/ErrorState';
import { PageHeader } from '../../components/common/PageHeader';
import { collectionsService } from '../../services/collectionsService';
import { toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { formatDate, formatMoney } from '../../utils/format';
import type { AgingBucket, CollectionInvoiceOut, CollectionStatus } from '../../types/collections';
import { AGING_BUCKET_LABELS, COLLECTION_STATUS_LABELS, COLLECTION_STATUS_VARIANTS } from './collectionsUi';

const PAGE_SIZE = 20;

const STATUS_OPTIONS: { value: '' | CollectionStatus; label: string }[] = [
  { value: '', label: 'All statuses' },
  ...(Object.keys(COLLECTION_STATUS_LABELS) as CollectionStatus[]).map((status) => ({
    value: status,
    label: COLLECTION_STATUS_LABELS[status],
  })),
];

const AGING_OPTIONS: { value: '' | AgingBucket; label: string }[] = [
  { value: '', label: 'All aging buckets' },
  ...(Object.keys(AGING_BUCKET_LABELS) as AgingBucket[]).map((bucket) => ({
    value: bucket,
    label: AGING_BUCKET_LABELS[bucket],
  })),
];

const SORT_OPTIONS = [
  { value: '-outstanding', label: 'Outstanding (high to low)' },
  { value: 'outstanding', label: 'Outstanding (low to high)' },
  { value: '-days_overdue', label: 'Days overdue (most)' },
  { value: 'days_overdue', label: 'Days overdue (least)' },
  { value: 'due_date', label: 'Due date (earliest)' },
  { value: '-due_date', label: 'Due date (latest)' },
  { value: 'customer', label: 'Customer (A-Z)' },
  { value: '-customer', label: 'Customer (Z-A)' },
];

/** Debounces a fast-changing value (e.g. a search input) before it drives a query. */
function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function CollectionsInvoiceListPage() {
  const navigate = useNavigate();

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<'' | CollectionStatus>('');
  const [agingBucket, setAgingBucket] = useState<'' | AgingBucket>('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [amountMin, setAmountMin] = useState('');
  const [amountMax, setAmountMax] = useState('');
  const [sort, setSort] = useState('-outstanding');
  const [page, setPage] = useState(1);

  const debouncedSearch = useDebouncedValue(search, 300);

  const listParams = useMemo(
    () => ({
      search: debouncedSearch || undefined,
      status: status || undefined,
      aging_bucket: agingBucket || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      amount_min: amountMin || undefined,
      amount_max: amountMax || undefined,
      sort,
      page,
      page_size: PAGE_SIZE,
    }),
    [debouncedSearch, status, agingBucket, dateFrom, dateTo, amountMin, amountMax, sort, page]
  );

  const invoicesQuery = useQuery({
    queryKey: queryKeys.collections.list(listParams),
    queryFn: () => collectionsService.list(listParams),
  });

  const resetPage = () => setPage(1);

  const clearFilters = () => {
    setSearch('');
    setStatus('');
    setAgingBucket('');
    setDateFrom('');
    setDateTo('');
    setAmountMin('');
    setAmountMax('');
    setSort('-outstanding');
    setPage(1);
  };

  const hasFilters =
    !!search || !!status || !!agingBucket || !!dateFrom || !!dateTo || !!amountMin || !!amountMax;

  const columns: Column<CollectionInvoiceOut>[] = [
    {
      key: 'invoice_number',
      title: 'Invoice #',
      render: (item) => <span className="font-mono font-bold text-slate-700 text-xs">{item.invoice_number}</span>,
    },
    {
      key: 'customer',
      title: 'Customer',
      render: (item) => <span className="font-semibold text-slate-900 text-xs">{item.customer.display_name}</span>,
    },
    {
      key: 'issue_date',
      title: 'Invoice Date',
      render: (item) => <span className="text-xs text-slate-600">{formatDate(item.issue_date)}</span>,
    },
    {
      key: 'due_date',
      title: 'Due Date',
      render: (item) => <span className="text-xs text-slate-600">{formatDate(item.due_date)}</span>,
    },
    {
      key: 'total',
      title: 'Invoice Amount',
      align: 'right',
      render: (item) => <span className="text-xs font-semibold text-slate-900 tabular-nums">{formatMoney(item.total, item.currency)}</span>,
    },
    {
      key: 'amount_paid',
      title: 'Paid',
      align: 'right',
      render: (item) => <span className="text-xs text-emerald-600 tabular-nums">{formatMoney(item.amount_paid, item.currency)}</span>,
    },
    {
      key: 'amount_due',
      title: 'Outstanding',
      align: 'right',
      render: (item) => <span className="text-xs font-bold text-slate-900 tabular-nums">{formatMoney(item.amount_due, item.currency)}</span>,
    },
    {
      key: 'days_overdue',
      title: 'Days Overdue',
      align: 'right',
      render: (item) => (
        <span className={`text-xs font-semibold tabular-nums ${item.days_overdue > 0 ? 'text-rose-600' : 'text-slate-500'}`}>
          {item.days_overdue > 0 ? item.days_overdue : '—'}
        </span>
      ),
    },
    {
      key: 'collection_status',
      title: 'Collection Status',
      render: (item) => (
        <Badge variant={COLLECTION_STATUS_VARIANTS[item.collection_status]} size="sm">
          {COLLECTION_STATUS_LABELS[item.collection_status]}
        </Badge>
      ),
    },
    {
      key: 'last_contact_at',
      title: 'Last Contact',
      render: (item) => <span className="text-xs text-slate-500">{formatDate(item.last_contact_at)}</span>,
    },
    {
      key: 'next_follow_up_at',
      title: 'Next Follow-up',
      render: (item) => <span className="text-xs text-slate-500">{formatDate(item.next_follow_up_at)}</span>,
    },
    {
      key: 'action',
      title: 'Actions',
      align: 'right',
      render: (item) => (
        <Button variant="outline" size="sm" onClick={() => navigate(`/collections/invoices/${item.id}`)}>
          View
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Revenue"
        title="Collection Invoices"
        subtitle="Search, filter and act on every invoice with an outstanding balance."
        backTo={{ to: '/collections', label: 'Back to Collections' }}
      />

      <Card>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <Input
              label="Search"
              placeholder="Invoice # or customer..."
              leadingIcon={<Search className="w-4 h-4" />}
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                resetPage();
              }}
            />
            <Select
              label="Collection Status"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value as '' | CollectionStatus);
                resetPage();
              }}
              options={STATUS_OPTIONS}
            />
            <Select
              label="Aging Bucket"
              value={agingBucket}
              onChange={(e) => {
                setAgingBucket(e.target.value as '' | AgingBucket);
                resetPage();
              }}
              options={AGING_OPTIONS}
            />
            <Select
              label="Sort By"
              value={sort}
              onChange={(e) => {
                setSort(e.target.value);
                resetPage();
              }}
              options={SORT_OPTIONS}
            />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Input
              label="Due From"
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                resetPage();
              }}
            />
            <Input
              label="Due To"
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                resetPage();
              }}
            />
            <Input
              label="Min Outstanding"
              type="number"
              min="0"
              step="0.01"
              value={amountMin}
              onChange={(e) => {
                setAmountMin(e.target.value);
                resetPage();
              }}
            />
            <Input
              label="Max Outstanding"
              type="number"
              min="0"
              step="0.01"
              value={amountMax}
              onChange={(e) => {
                setAmountMax(e.target.value);
                resetPage();
              }}
            />
          </div>
          {hasFilters && (
            <div className="flex justify-end">
              <Button
                variant="ghost"
                size="sm"
                leadingIcon={<SlidersHorizontal className="w-3.5 h-3.5" />}
                onClick={clearFilters}
              >
                Clear filters
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {invoicesQuery.isError ? (
        <ErrorState
          message={toApiError(invoicesQuery.error).message}
          onRetry={() => void invoicesQuery.refetch()}
        />
      ) : (
        <DataTable
          columns={columns}
          data={invoicesQuery.data?.items ?? []}
          keyExtractor={(item) => item.id}
          isLoading={invoicesQuery.isPending}
          page={invoicesQuery.data?.page ?? page}
          pageSize={PAGE_SIZE}
          total={invoicesQuery.data?.total}
          onPageChange={setPage}
          emptyMessage="No collection invoices found"
          emptySubtext={
            hasFilters
              ? 'Try adjusting or clearing your filters.'
              : 'Invoices with an outstanding balance will show up here.'
          }
        />
      )}
    </div>
  );
}
