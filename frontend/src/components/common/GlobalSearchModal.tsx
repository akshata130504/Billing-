import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search,
  X,
  Users,
  Receipt,
  FileText,
  Package,
  Repeat,
  CreditCard,
  ArrowRight,
} from 'lucide-react';
import { mockSearchDirectory } from '../../pages/dashboard/mockDashboardData';
import { SearchCategory, SearchResultItem } from '../../types';

export interface GlobalSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function GlobalSearchModal({ isOpen, onClose }: GlobalSearchModalProps) {
  const [query, setQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<SearchCategory | 'all'>('all');
  const navigate = useNavigate();

  // Escape closes the modal. Ctrl/Cmd + K toggling is owned by AppLayout so the
  // two handlers never race each other on the same keydown.
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Start from a clean search each time the modal is reopened
  useEffect(() => {
    if (!isOpen) {
      setQuery('');
      setActiveCategory('all');
    }
  }, [isOpen]);

  const filteredResults = useMemo(() => {
    return mockSearchDirectory.filter((item) => {
      const matchesCategory = activeCategory === 'all' || item.category === activeCategory;
      const matchesQuery =
        !query.trim() ||
        item.title.toLowerCase().includes(query.toLowerCase()) ||
        item.subtitle.toLowerCase().includes(query.toLowerCase()) ||
        item.category.toLowerCase().includes(query.toLowerCase());
      return matchesCategory && matchesQuery;
    });
  }, [query, activeCategory]);

  if (!isOpen) return null;

  const categoryIcons: Record<SearchCategory, React.ComponentType<{ className?: string }>> = {
    customers: Users,
    invoices: Receipt,
    quotes: FileText,
    products: Package,
    subscriptions: Repeat,
    payments: CreditCard,
  };

  const handleSelect = (item: SearchResultItem) => {
    onClose();
    navigate(item.path);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 p-4 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Search Box Card */}
      <div className="relative w-full max-w-2xl bg-white rounded-2xl shadow-modal border border-slate-200 z-10 overflow-hidden flex flex-col max-h-[80vh]">
        {/* Search Input Bar */}
        <div className="p-4 border-b border-slate-100 flex items-center gap-3">
          <Search className="w-5 h-5 text-slate-400 shrink-0" />
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search across customers, invoices, quotes, products, subscriptions, payments..."
            className="flex-1 text-sm bg-transparent placeholder:text-slate-400 text-slate-900 outline-none"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="p-1 rounded-md text-slate-400 hover:text-slate-600"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <span className="hidden sm:inline-block text-[10px] font-mono bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded border border-slate-200">
            ESC
          </span>
        </div>

        {/* Category Filters */}
        <div className="px-4 py-2 bg-slate-50/70 border-b border-slate-100 flex items-center gap-1.5 overflow-x-auto text-xs">
          {(
            [
              'all',
              'customers',
              'invoices',
              'quotes',
              'products',
              'subscriptions',
              'payments',
            ] as const
          ).map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-2.5 py-1 rounded-lg font-medium capitalize whitespace-nowrap transition-colors ${
                activeCategory === cat
                  ? 'bg-brand-600 text-white shadow-xs'
                  : 'text-slate-600 hover:bg-slate-200/70'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Search Results List */}
        <div className="p-2 overflow-y-auto divide-y divide-slate-100">
          {filteredResults.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-400">
              No matching records found for &ldquo;{query}&rdquo;
            </div>
          ) : (
            filteredResults.map((item) => {
              const Icon = categoryIcons[item.category];
              return (
                <button
                  key={item.id}
                  onClick={() => handleSelect(item)}
                  className="w-full flex items-center justify-between p-3 rounded-xl hover:bg-slate-50 transition-colors text-left group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center shrink-0 group-hover:bg-brand-50 group-hover:text-brand-600 transition-colors">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-slate-900 group-hover:text-brand-700 truncate">
                          {item.title}
                        </span>
                        {item.badge && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">
                            {item.badge}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400 truncate">
                        {item.subtitle}
                      </p>
                    </div>
                  </div>
                  <ArrowRight className="w-4 h-4 text-slate-300 group-hover:text-brand-600 shrink-0 ml-2" />
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
