import { useEffect, useMemo, useRef, useState, type ComponentType } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Search,
  X,
  Users,
  Receipt,
  FileText,
  Package,
  Repeat,
  CreditCard,
  FolderKanban,
  Wallet,
  ArrowRight,
  CornerDownLeft,
} from 'lucide-react';
import { controlCenterService } from '../../services/controlCenterService';
import { queryKeys } from '../../hooks/queries';
import { toApiError } from '../../services/apiClient';
import type { SearchCategory, SearchCategoryFilter, SearchResult } from '../../types';
import { LoadingSpinner } from './LoadingState';
import { cn } from '../../utils/cn';

export interface GlobalSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const MIN_QUERY_LENGTH = 2;
const DEBOUNCE_MS = 250;

const CATEGORY_ORDER: SearchCategory[] = [
  'customers',
  'invoices',
  'quotes',
  'products',
  'subscriptions',
  'payments',
  'projects',
  'expenses',
];

const CATEGORY_ICONS: Record<SearchCategory, ComponentType<{ className?: string }>> = {
  customers: Users,
  invoices: Receipt,
  quotes: FileText,
  products: Package,
  subscriptions: Repeat,
  payments: CreditCard,
  // Result paths come from the backend: /projects/:id and /expenses/:id.
  projects: FolderKanban,
  expenses: Wallet,
};

function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(handle);
  }, [value, delay]);
  return debounced;
}

export function GlobalSearchModal({ isOpen, onClose }: GlobalSearchModalProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<SearchCategoryFilter>('all');
  const [activeIndex, setActiveIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const trimmed = query.trim();
  const debouncedQuery = useDebouncedValue(trimmed, DEBOUNCE_MS);
  const canSearch = debouncedQuery.length >= MIN_QUERY_LENGTH;

  const search = useQuery({
    queryKey: queryKeys.controlCenter.search(debouncedQuery),
    queryFn: () => controlCenterService.search(debouncedQuery),
    enabled: isOpen && canSearch,
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  });

  // Escape closes. Ctrl/Cmd+K toggling is owned by AppLayout.
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Reset when reopened.
  useEffect(() => {
    if (!isOpen) {
      setQuery('');
      setActiveCategory('all');
      setActiveIndex(0);
    }
  }, [isOpen]);

  const results = useMemo<SearchResult[]>(() => {
    const all = search.data ?? [];
    return activeCategory === 'all' ? all : all.filter((r) => r.category === activeCategory);
  }, [search.data, activeCategory]);

  // Group in a stable category order; keep a flat list for keyboard navigation.
  const grouped = useMemo(() => {
    const groups: { category: SearchCategory; items: SearchResult[] }[] = [];
    for (const category of CATEGORY_ORDER) {
      const items = results.filter((r) => r.category === category);
      if (items.length) groups.push({ category, items });
    }
    return groups;
  }, [results]);

  const flat = useMemo(() => grouped.flatMap((g) => g.items), [grouped]);

  useEffect(() => {
    setActiveIndex(0);
  }, [debouncedQuery, activeCategory]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  if (!isOpen) return null;

  const handleSelect = (item: SearchResult) => {
    onClose();
    navigate(item.path);
  };

  const onInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => (flat.length ? (i + 1) % flat.length : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => (flat.length ? (i - 1 + flat.length) % flat.length : 0));
    } else if (e.key === 'Enter') {
      const item = flat[activeIndex];
      if (item) {
        e.preventDefault();
        handleSelect(item);
      }
    }
  };

  const showHint = trimmed.length < MIN_QUERY_LENGTH;
  const isSearching = canSearch && (search.isPending || search.isFetching);
  const errorMessage = search.isError ? toApiError(search.error).message : null;

  let flatIndex = -1;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 p-4 overflow-y-auto">
      <div
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Global search"
        className="relative w-full max-w-2xl bg-white rounded-2xl shadow-modal border border-slate-200 z-10 overflow-hidden flex flex-col max-h-[80vh]"
      >
        {/* Input */}
        <div className="p-4 border-b border-slate-100 flex items-center gap-3">
          {isSearching ? (
            <LoadingSpinner size="sm" className="shrink-0" />
          ) : (
            <Search className="w-5 h-5 text-slate-400 shrink-0" />
          )}
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKeyDown}
            role="combobox"
            aria-expanded={flat.length > 0}
            aria-controls="global-search-results"
            aria-autocomplete="list"
            placeholder="Search customers, invoices, quotes, products, subscriptions, payments..."
            className="flex-1 text-sm bg-transparent placeholder:text-slate-400 text-slate-900 outline-none"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="p-1 rounded-md text-slate-400 hover:text-slate-600"
              aria-label="Clear search"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <span className="hidden sm:inline-block text-[10px] font-mono bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded border border-slate-200">
            ESC
          </span>
        </div>

        {/* Category filters */}
        <div className="px-4 py-2 bg-slate-50/70 border-b border-slate-100 flex items-center gap-1.5 overflow-x-auto text-xs">
          {(['all', ...CATEGORY_ORDER] as SearchCategoryFilter[]).map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setActiveCategory(cat)}
              className={cn(
                'px-2.5 py-1 rounded-lg font-medium capitalize whitespace-nowrap transition-colors',
                activeCategory === cat
                  ? 'bg-brand-600 text-white shadow-xs'
                  : 'text-slate-600 hover:bg-slate-200/70'
              )}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Results */}
        <div id="global-search-results" ref={listRef} className="p-2 overflow-y-auto" role="listbox">
          {showHint ? (
            <div className="py-12 text-center text-xs text-slate-400">
              Type at least {MIN_QUERY_LENGTH} characters to search your organization.
            </div>
          ) : errorMessage ? (
            <div className="py-12 text-center text-xs text-rose-600">{errorMessage}</div>
          ) : isSearching && flat.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-400">Searching...</div>
          ) : flat.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-400">
              No matching records for &ldquo;{debouncedQuery}&rdquo;
            </div>
          ) : (
            grouped.map((group) => {
              const Icon = CATEGORY_ICONS[group.category];
              return (
                <div key={group.category} className="mb-1.5">
                  <div className="px-3 pt-2 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    {group.category}
                  </div>
                  {group.items.map((item) => {
                    flatIndex += 1;
                    const index = flatIndex;
                    const isActive = index === activeIndex;
                    return (
                      <button
                        key={`${item.category}-${item.id}`}
                        type="button"
                        role="option"
                        aria-selected={isActive}
                        data-index={index}
                        onMouseEnter={() => setActiveIndex(index)}
                        onClick={() => handleSelect(item)}
                        className={cn(
                          'w-full flex items-center justify-between p-3 rounded-xl transition-colors text-left group',
                          isActive ? 'bg-brand-50' : 'hover:bg-slate-50'
                        )}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div
                            className={cn(
                              'w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors',
                              isActive
                                ? 'bg-white text-brand-600 border border-blue-200'
                                : 'bg-slate-100 text-slate-600'
                            )}
                          >
                            <Icon className="w-4 h-4" />
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span
                                className={cn(
                                  'text-xs font-semibold truncate',
                                  isActive ? 'text-brand-700' : 'text-slate-900'
                                )}
                              >
                                {item.title}
                              </span>
                              {item.badge && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-medium capitalize">
                                  {item.badge.replace(/_/g, ' ')}
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-400 truncate">{item.subtitle}</p>
                          </div>
                        </div>
                        {isActive ? (
                          <CornerDownLeft className="w-4 h-4 text-brand-600 shrink-0 ml-2" />
                        ) : (
                          <ArrowRight className="w-4 h-4 text-slate-300 group-hover:text-brand-600 shrink-0 ml-2" />
                        )}
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        <div className="px-4 py-2 border-t border-slate-100 bg-slate-50/60 flex items-center gap-4 text-[10px] text-slate-400">
          <span>
            <kbd className="font-mono">↑</kbd> <kbd className="font-mono">↓</kbd> to navigate
          </span>
          <span>
            <kbd className="font-mono">Enter</kbd> to open
          </span>
        </div>
      </div>
    </div>
  );
}
