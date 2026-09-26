import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, Loader2, Search, X } from 'lucide-react';
import { cn } from '../../utils/cn';
import { customerService } from '../../services/customerService';
import { toApiError } from '../../services/apiClient';
import type { CustomerOut } from '../../types/api';

export interface CustomerComboboxProps {
  /** Selected customer id ('' when nothing is selected). */
  value: string;
  onChange: (customerId: string, customer: CustomerOut | null) => void;
  label?: string;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  error?: string;
  className?: string;
  /** Allow clearing the selection (e.g. for filters). */
  clearable?: boolean;
  id?: string;
}

const RESULT_LIMIT = 20;

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/**
 * Server-searching customer picker. Unlike a <select> fed by one page of
 * customers, every customer in the organization is reachable by typing.
 */
export function CustomerCombobox({
  value,
  onChange,
  label,
  placeholder = 'Search customers by name or email...',
  required,
  disabled,
  error,
  className,
  clearable = false,
  id: customId,
}: CustomerComboboxProps) {
  const generatedId = useId();
  const id = customId || generatedId;
  const listId = `${id}-listbox`;
  const containerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [selected, setSelected] = useState<CustomerOut | null>(null);
  const debouncedQuery = useDebounced(query.trim(), 250);

  const searchQuery = useQuery({
    queryKey: ['customers', 'combobox', debouncedQuery],
    queryFn: () =>
      customerService.list({ search: debouncedQuery || undefined, page: 1, page_size: RESULT_LIMIT }),
    enabled: open,
    staleTime: 30_000,
  });

  // Resolve the label for a preselected id that isn't in the loaded results.
  const selectedQuery = useQuery({
    queryKey: ['customers', 'detail', value],
    queryFn: () => customerService.get(value),
    enabled: Boolean(value) && selected?.id !== value,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!value) setSelected(null);
    else if (selectedQuery.data && selectedQuery.data.id === value) setSelected(selectedQuery.data);
  }, [value, selectedQuery.data]);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  const results = useMemo(() => searchQuery.data?.items ?? [], [searchQuery.data]);
  const total = searchQuery.data?.total ?? 0;

  useEffect(() => {
    setActiveIndex(0);
  }, [debouncedQuery]);

  const choose = (customer: CustomerOut | null) => {
    setSelected(customer);
    onChange(customer?.id ?? '', customer);
    setOpen(false);
    setQuery('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!open) setOpen(true);
      setActiveIndex((i) => Math.min(i + 1, Math.max(results.length - 1, 0)));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      if (open && results[activeIndex]) {
        e.preventDefault();
        choose(results[activeIndex]);
      }
    } else if (e.key === 'Escape') {
      if (open) {
        e.stopPropagation();
        setOpen(false);
      }
    }
  };

  const displayValue = open
    ? query
    : selected
      ? `${selected.display_name}${selected.email ? ` (${selected.email})` : ''}`
      : value && selectedQuery.isLoading
        ? 'Loading...'
        : '';

  return (
    <div className={cn('w-full', className)} ref={containerRef}>
      {label && (
        <label htmlFor={id} className="block text-xs font-medium text-slate-700 mb-1.5">
          {label}
          {required && <span className="text-rose-500 ml-0.5">*</span>}
        </label>
      )}
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          id={id}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-invalid={Boolean(error)}
          autoComplete="off"
          disabled={disabled}
          value={displayValue}
          placeholder={selected ? undefined : placeholder}
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            if (!open) setOpen(true);
          }}
          onKeyDown={handleKeyDown}
          className={cn(
            'block w-full rounded-lg border bg-white pl-9 pr-9 py-2 text-sm text-slate-900 transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
            'disabled:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed',
            error ? 'border-rose-300' : 'border-slate-300'
          )}
        />
        {clearable && value && !disabled ? (
          <button
            type="button"
            aria-label="Clear customer"
            onClick={() => choose(null)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 rounded text-slate-400 hover:text-slate-600"
          >
            <X className="w-4 h-4" />
          </button>
        ) : (
          <ChevronDown className="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        )}

        {open && !disabled && (
          <ul
            id={listId}
            role="listbox"
            className="absolute z-50 mt-1 w-full max-h-64 overflow-y-auto bg-white border border-slate-200 rounded-lg shadow-elevated py-1 text-sm"
          >
            {searchQuery.isLoading ? (
              <li className="px-3 py-2.5 text-xs text-slate-500 flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Searching customers...
              </li>
            ) : searchQuery.isError ? (
              <li className="px-3 py-2.5 text-xs text-rose-600">
                {toApiError(searchQuery.error).message}
              </li>
            ) : results.length === 0 ? (
              <li className="px-3 py-2.5 text-xs text-slate-500">
                {debouncedQuery ? `No customers match "${debouncedQuery}".` : 'No customers yet.'}
              </li>
            ) : (
              <>
                {results.map((c, index) => (
                  <li
                    key={c.id}
                    role="option"
                    aria-selected={c.id === value}
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => choose(c)}
                    className={cn(
                      'px-3 py-2 cursor-pointer',
                      index === activeIndex ? 'bg-slate-50' : '',
                      c.id === value ? 'font-semibold text-brand-700' : 'text-slate-800'
                    )}
                  >
                    <div className="truncate">{c.display_name}</div>
                    {(c.email || c.company_name) && (
                      <div className="text-[11px] text-slate-500 truncate">
                        {[c.company_name, c.email].filter(Boolean).join(' · ')}
                      </div>
                    )}
                  </li>
                ))}
                {total > results.length && (
                  <li className="px-3 py-2 text-[11px] text-slate-400 border-t border-slate-100">
                    Showing {results.length} of {total}. Keep typing to narrow results.
                  </li>
                )}
              </>
            )}
          </ul>
        )}
      </div>
      {error && <p className="mt-1 text-xs text-rose-600">{error}</p>}
    </div>
  );
}
