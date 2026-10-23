import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useInfiniteQuery } from '@tanstack/react-query';
import {
  Activity,
  ArrowRight,
  CreditCard,
  ReceiptText,
  RefreshCw,
  Search,
  Settings2,
  Users,
  X,
} from 'lucide-react';
import { controlCenterService } from '../../services/controlCenterService';
import { toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import type { ActivityCategoryFilter, ActivityItem, ActivitySeverity } from '../../types/api';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Input } from '../../components/common/Input';
import { Card, CardContent } from '../../components/common/Card';
import { LoadingState, LoadingSpinner } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { EmptyState } from '../../components/common/EmptyState';
import { PageHeader } from '../../components/common/PageHeader';
import { formatDate, formatDateTime, formatNumber, formatRelative, humanize, toIsoDate } from '../../utils/format';
import { cn } from '../../utils/cn';
import { usePageSpec, type SpecUi } from '../../appUi/usePageSpec';

// ---------------------------------------------------------------------------
// Static config
// ---------------------------------------------------------------------------

const PAGE_SIZE = 25;

type ActivityCategory = ActivityItem['category'];

/** Filter chip icons; labels, order and visibility come from the page spec (`filters`). */
const CATEGORY_FILTER_ICONS: Record<ActivityCategoryFilter, typeof Activity> = {
  all: Activity,
  billing: ReceiptText,
  customers: Users,
  payments: CreditCard,
  system: Settings2,
};

const CATEGORY_STYLE: Record<ActivityCategory, { icon: typeof Activity; bg: string; text: string; label: string }> = {
  billing: { icon: ReceiptText, bg: 'bg-blue-50', text: 'text-brand-600', label: 'Billing' },
  customers: { icon: Users, bg: 'bg-violet-50', text: 'text-violet-600', label: 'Customers' },
  payments: { icon: CreditCard, bg: 'bg-emerald-50', text: 'text-emerald-600', label: 'Payments' },
  system: { icon: Settings2, bg: 'bg-slate-100', text: 'text-slate-500', label: 'System' },
};

const SEVERITY_RING: Record<ActivitySeverity, string> = {
  normal: 'ring-slate-200',
  success: 'ring-emerald-300',
  warning: 'ring-amber-300',
  danger: 'ring-rose-300',
};

/**
 * Entity types the frontend has a detail route for. Anything else (users,
 * memberships, imports, plans, ...) renders without a link.
 */
const ENTITY_ROUTES: Record<string, { path: string; label: string }> = {
  invoice: { path: '/invoices', label: 'View invoice' },
  customer: { path: '/customers', label: 'View customer' },
  payment: { path: '/payments', label: 'View payment' },
  subscription: { path: '/subscriptions', label: 'View subscription' },
  quote: { path: '/quotes', label: 'View quote' },
};

function entityLink(item: ActivityItem): { to: string; label: string } | null {
  if (!item.entity_type || !item.entity_id) return null;
  const route = ENTITY_ROUTES[item.entity_type.toLowerCase()];
  return route ? { to: `${route.path}/${item.entity_id}`, label: route.label } : null;
}

/**
 * The API description is "<entity label> - <actor label>" (or just the actor
 * when the entity has no label). Split it so the actor can be rendered
 * separately from what was acted on.
 */
function splitDescription(description: string): { subject: string | null; actor: string | null } {
  const raw = description.trim();
  if (!raw) return { subject: null, actor: null };
  const idx = raw.lastIndexOf(' - ');
  if (idx <= 0) return { subject: null, actor: raw };
  return { subject: raw.slice(0, idx).trim() || null, actor: raw.slice(idx + 3).trim() || null };
}

function dayLabel(dayIso: string, todayIso: string, yesterdayIso: string): string {
  if (dayIso === todayIso) return 'Today';
  if (dayIso === yesterdayIso) return 'Yesterday';
  return formatDate(dayIso);
}

// ---------------------------------------------------------------------------
// Building blocks
// ---------------------------------------------------------------------------

function ActivityRow({ item, isLast }: { item: ActivityItem; isLast: boolean }) {
  const style = CATEGORY_STYLE[item.category] ?? CATEGORY_STYLE.system;
  const Icon = style.icon;
  const { subject, actor } = splitDescription(item.description);
  const link = entityLink(item);

  return (
    <li className="relative flex gap-4">
      {!isLast && <span aria-hidden className="absolute left-[19px] top-10 bottom-0 w-px bg-slate-200" />}
      <div
        className={cn(
          'relative z-10 shrink-0 w-10 h-10 rounded-full flex items-center justify-center ring-4 ring-white',
          style.bg,
          style.text
        )}
      >
        <span className={cn('absolute inset-0 rounded-full ring-2', SEVERITY_RING[item.severity] ?? SEVERITY_RING.normal)} />
        <Icon className="w-4 h-4" />
      </div>

      <div className="flex-1 min-w-0 pb-6">
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-card px-4 py-3 hover:border-slate-300 transition-colors">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-slate-900">{item.title}</p>
                <Badge size="sm" variant="neutral">
                  {style.label}
                </Badge>
                {item.severity !== 'normal' && (
                  <Badge size="sm" variant={item.severity === 'success' ? 'success' : item.severity === 'warning' ? 'warning' : 'danger'} dot>
                    {humanize(item.severity)}
                  </Badge>
                )}
              </div>
              {subject && <p className="mt-0.5 text-xs text-slate-600 truncate">{subject}</p>}
              <p className="mt-1 text-[11px] text-slate-500">
                {actor ? (
                  <>
                    by <span className="font-medium text-slate-700">{actor}</span>
                  </>
                ) : (
                  <span className="text-slate-400">Automated</span>
                )}
                {item.entity_type && (
                  <>
                    <span className="mx-1.5 text-slate-300">·</span>
                    <span className="uppercase tracking-wider text-[10px] font-semibold text-slate-400">
                      {humanize(item.entity_type)}
                    </span>
                  </>
                )}
              </p>
            </div>
            <div className="flex items-center gap-3 shrink-0 sm:flex-col sm:items-end sm:gap-1">
              <time
                dateTime={item.timestamp}
                title={formatDateTime(item.timestamp)}
                className="text-[11px] font-medium text-slate-500 whitespace-nowrap tabular-nums"
              >
                {formatRelative(item.timestamp)}
              </time>
              {link && (
                <Link
                  to={link.to}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand-600 hover:text-brand-700 whitespace-nowrap"
                >
                  {link.label}
                  <ArrowRight className="w-3 h-3" />
                </Link>
              )}
            </div>
          </div>
        </div>
      </div>
    </li>
  );
}

function FilterBar({
  category,
  onCategory,
  search,
  onSearch,
  from,
  to,
  onFrom,
  onTo,
  onClear,
  hasClientFilters,
  ui,
}: {
  category: ActivityCategoryFilter;
  onCategory: (c: ActivityCategoryFilter) => void;
  search: string;
  onSearch: (v: string) => void;
  from: string;
  to: string;
  onFrom: (v: string) => void;
  onTo: (v: string) => void;
  onClear: () => void;
  hasClientFilters: boolean;
  ui: SpecUi;
}) {
  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap" role="tablist" aria-label="Activity category" {...ui.edit('filters')}>
          {ui.shown('filters').map((f) => {
            const key = f.key as ActivityCategoryFilter;
            const Icon = CATEGORY_FILTER_ICONS[key] ?? Activity;
            const active = key === category;
            return (
              <button
                key={f.key}
                {...ui.edit(`filters.${f.key}`)}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => onCategory(key)}
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                  active
                    ? 'bg-brand-50 text-brand-700 border-brand-200'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300 hover:text-slate-900'
                )}
              >
                <Icon className={cn('w-3.5 h-3.5 shrink-0', active ? 'text-brand-600' : 'text-slate-400')} />
                {f.label}
              </button>
            );
          })}
        </div>
        <div className="flex flex-col lg:flex-row lg:items-center gap-3">
          <div className="flex-1">
            <Input
              aria-label="Search activity"
              placeholder="Search by title, entity or actor..."
              value={search}
              onChange={(e) => onSearch(e.target.value)}
              leadingIcon={<Search className="w-4 h-4" />}
            />
          </div>
          <div className="flex items-center gap-2">
            <Input type="date" aria-label="From date" value={from} max={to || undefined} onChange={(e) => onFrom(e.target.value)} />
            <span className="text-xs text-slate-400 shrink-0">to</span>
            <Input type="date" aria-label="To date" value={to} min={from || undefined} onChange={(e) => onTo(e.target.value)} />
          </div>
          {hasClientFilters && (
            <Button variant="ghost" size="sm" leadingIcon={<X className="w-3.5 h-3.5" />} onClick={onClear}>
              Clear
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ActivityPage() {
  const ui = usePageSpec('activity');
  const [category, setCategory] = useState<ActivityCategoryFilter>('all');
  const [search, setSearch] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');

  const query = useInfiniteQuery({
    queryKey: queryKeys.controlCenter.activity({ category, page_size: PAGE_SIZE }),
    queryFn: ({ pageParam }) =>
      controlCenterService.activity({ category, page: pageParam, page_size: PAGE_SIZE }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page < last.total_pages ? last.page + 1 : undefined),
  });

  const loadedItems = useMemo(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data]
  );
  const total = query.data?.pages[0]?.total ?? 0;

  // The API only filters by category; search and date range are applied
  // client-side to what has been loaded so far.
  const hasClientFilters = Boolean(search.trim() || from || to);
  const visibleItems = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return loadedItems.filter((item) => {
      if (needle) {
        const haystack = `${item.title} ${item.description} ${item.entity_type ?? ''}`.toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      if (from || to) {
        const day = toIsoDate(new Date(item.timestamp));
        if (from && day < from) return false;
        if (to && day > to) return false;
      }
      return true;
    });
  }, [loadedItems, search, from, to]);

  const groups = useMemo(() => {
    const now = new Date();
    const todayIso = toIsoDate(now);
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    const yesterdayIso = toIsoDate(yesterday);

    const byDay = new Map<string, ActivityItem[]>();
    for (const item of visibleItems) {
      const day = toIsoDate(new Date(item.timestamp));
      const bucket = byDay.get(day);
      if (bucket) bucket.push(item);
      else byDay.set(day, [item]);
    }
    return Array.from(byDay.entries()).map(([day, items]) => ({
      day,
      label: dayLabel(day, todayIso, yesterdayIso),
      items,
    }));
  }, [visibleItems]);

  const clearClientFilters = () => {
    setSearch('');
    setFrom('');
    setTo('');
  };

  let body: ReactNode;
  if (query.isPending) {
    body = <LoadingState message="Loading activity..." />;
  } else if (query.isError) {
    body = <ErrorState message={toApiError(query.error).message} onRetry={() => void query.refetch()} />;
  } else if (loadedItems.length === 0) {
    body = (
      <div {...ui.edit('empty')}>
      <EmptyState
        icon={<Activity className="w-6 h-6 stroke-1" />}
        title={
          category === 'all'
            ? ui.text('empty', 'none_title')
            : ui.text('empty', 'category_title', { category: ui.label('filters', category).toLowerCase() })
        }
        description={
          category === 'all'
            ? ui.text('empty', 'none_description')
            : ui.text('empty', 'category_description')
        }
        action={
          category !== 'all' ? (
            <Button variant="outline" size="sm" onClick={() => setCategory('all')}>
              Show all activity
            </Button>
          ) : undefined
        }
      />
      </div>
    );
  } else if (visibleItems.length === 0) {
    body = (
      <div {...ui.edit('empty')}>
      <EmptyState
        icon={<Search className="w-6 h-6 stroke-1" />}
        title={ui.text('empty', 'no_match_title')}
        description={
          query.hasNextPage
            ? ui.text('empty', 'no_match_more', { count: formatNumber(loadedItems.length) })
            : ui.text('empty', 'no_match_description')
        }
        action={
          <div className="flex items-center gap-2">
            {query.hasNextPage && (
              <Button variant="outline" size="sm" isLoading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
                Load more
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={clearClientFilters}>
              Clear filters
            </Button>
          </div>
        }
      />
      </div>
    );
  } else {
    body = (
      <div className="space-y-8">
        {groups.map((group) => (
          <section key={group.day} aria-label={group.label}>
            <div className="flex items-center gap-3 mb-4">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{group.label}</h2>
              <span className="text-[11px] text-slate-400 tabular-nums">
                {group.items.length} {group.items.length === 1 ? 'event' : 'events'}
              </span>
              <span className="flex-1 h-px bg-slate-200" />
            </div>
            <ol className="ml-1">
              {group.items.map((item, idx) => (
                <ActivityRow key={item.id} item={item} isLast={idx === group.items.length - 1} />
              ))}
            </ol>
          </section>
        ))}

        <div className="flex flex-col items-center gap-2 pt-2">
          <p className="text-[11px] text-slate-400 tabular-nums">
            Showing {formatNumber(visibleItems.length)}
            {hasClientFilters && ` of ${formatNumber(loadedItems.length)} loaded`} · {formatNumber(total)} total
            {category !== 'all' && ` in ${CATEGORY_STYLE[category as ActivityCategory]?.label ?? humanize(category)}`}
          </p>
          {query.hasNextPage ? (
            <Button
              variant="outline"
              size="sm"
              isLoading={query.isFetchingNextPage}
              onClick={() => void query.fetchNextPage()}
            >
              Load more
            </Button>
          ) : (
            <p className="text-xs text-slate-500" {...ui.edit('feed')}>{ui.text('feed', 'end_of_log')}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-12">
      <div {...ui.edit('header')}>
      <PageHeader
        eyebrow={ui.text('header', 'eyebrow')}
        title={ui.text('header', 'title')}
        subtitle={ui.text('header', 'subtitle')}
        actions={
          <Button
            variant="outline"
            size="sm"
            leadingIcon={
              query.isFetching && !query.isFetchingNextPage ? <LoadingSpinner size="sm" className="text-slate-500" /> : <RefreshCw className="w-3.5 h-3.5" />
            }
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            Refresh
          </Button>
        }
      />
      </div>

      <FilterBar
        category={category}
        onCategory={setCategory}
        search={search}
        onSearch={setSearch}
        from={from}
        to={to}
        onFrom={setFrom}
        onTo={setTo}
        onClear={clearClientFilters}
        hasClientFilters={hasClientFilters}
        ui={ui}
      />

      {hasClientFilters && !query.isPending && !query.isError && query.hasNextPage && visibleItems.length > 0 && (
        <p className="text-[11px] text-slate-400 -mt-3" {...ui.edit('feed')}>
          {ui.text('feed', 'filter_note', { count: formatNumber(loadedItems.length) })}
        </p>
      )}

      {body}
    </div>
  );
}
