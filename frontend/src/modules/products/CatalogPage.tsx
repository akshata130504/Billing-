import { useState, useEffect, useCallback } from 'react';
import {
  Package,
  BookOpen,
  Plus,
  Search,
  CheckCircle2,
  XCircle,
  Edit2,
  Archive,
  ArchiveRestore,
} from 'lucide-react';
import { Button } from '../../components/common/Button';
import { LoadingState } from '../../components/common/LoadingState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { ErrorState } from '../../components/common/ErrorState';
import { Pagination } from '../../components/common/Pagination';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';
import { catalogCpqService } from '../../services/catalogCpqService';
import { dashboardSummaryService } from '../../services/dashboardSummaryService';
import type { OfferingOut, PriceBookOut, OfferingIn, PriceBookIn } from '../../types/catalog_cpq';
import { OfferingModal } from './components/OfferingModal';
import { PriceBookModal } from './components/PriceBookModal';
import { usePageSpec } from '../../appUi/usePageSpec';
import { useCreateDeepLink } from '../../hooks/useCreateDeepLink';
import { formatMoney } from '../../utils/format';

const PAGE_SIZE = 25;

type CatalogTab = 'all' | 'products' | 'services' | 'plans' | 'bundles' | 'price_books';
type StatusFilter = 'active' | 'archived' | 'all';

const STATUS_OPTIONS: Array<{ id: StatusFilter; label: string }> = [
  { id: 'active', label: 'Active' },
  { id: 'archived', label: 'Archived' },
  { id: 'all', label: 'All' },
];

// Maps the UI filter onto the backend `is_active` query param (undefined = both).
const STATUS_TO_IS_ACTIVE: Record<StatusFilter, boolean | undefined> = {
  active: true,
  archived: false,
  all: undefined,
};

const TAB_TYPE: Partial<Record<CatalogTab, string>> = {
  products: 'product',
  services: 'service',
  plans: 'plan',
  bundles: 'bundle',
};

interface CatalogCounts {
  all: number;
  product: number;
  service: number;
  plan: number;
  bundle: number;
}

const EMPTY_COUNTS: CatalogCounts = { all: 0, product: 0, service: 0, plan: 0, bundle: 0 };
const EMPTY_STATUS_COUNTS: Record<StatusFilter, CatalogCounts> = {
  active: EMPTY_COUNTS,
  archived: EMPTY_COUNTS,
  all: EMPTY_COUNTS,
};

const toCounts = (total: number, byType: Record<string, number>): CatalogCounts => ({
  all: total,
  product: byType.product ?? 0,
  service: byType.service ?? 0,
  plan: byType.plan ?? 0,
  bundle: byType.bundle ?? 0,
});

export function CatalogPage() {
  const ui = usePageSpec('catalog');
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canEdit = hasRole('finance');
  const canArchive = hasRole('admin');

  const [activeTab, setActiveTab] = useState<CatalogTab>('all');
  const [offerings, setOfferings] = useState<OfferingOut[]>([]);
  const [offeringsTotal, setOfferingsTotal] = useState(0);
  const [priceBooks, setPriceBooks] = useState<PriceBookOut[]>([]);
  const [priceBooksTotal, setPriceBooksTotal] = useState(0);
  // Offering counts per status filter, all from one catalog summary (same search).
  const [statusCounts, setStatusCounts] = useState<Record<StatusFilter, CatalogCounts>>(EMPTY_STATUS_COUNTS);
  // Capped list of active offerings for the bundle / price-book pickers in the modals.
  const [pickerOfferings, setPickerOfferings] = useState<OfferingOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('active');

  // Modals state
  const [isOfferingModalOpen, setIsOfferingModalOpen] = useState(false);
  const [editingOffering, setEditingOffering] = useState<OfferingOut | null>(null);

  const [isPriceBookModalOpen, setIsPriceBookModalOpen] = useState(false);
  const [editingPriceBook, setEditingPriceBook] = useState<PriceBookOut | null>(null);

  // Archive confirmation state
  const [offeringToArchive, setOfferingToArchive] = useState<OfferingOut | null>(null);
  const [offeringToUnarchive, setOfferingToUnarchive] = useState<OfferingOut | null>(null);
  const [isArchiving, setIsArchiving] = useState(false);

  // Loaded on search change / after a mutation only; switching the status filter just picks a different set.
  const loadCounts = useCallback(async () => {
    try {
      const search = searchQuery.trim() || undefined;
      const { offerings: o } = await dashboardSummaryService.catalog({ search });
      setStatusCounts({
        active: toCounts(o.active, o.active_by_type || {}),
        archived: toCounts(o.inactive, o.inactive_by_type || {}),
        all: toCounts(o.total, o.by_type || {}),
      });
    } catch (err) {
      setLoadError(toApiError(err).message);
    }
  }, [searchQuery]);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const search = searchQuery.trim() || undefined;
      const isPriceBooks = activeTab === 'price_books';
      const [offeringData, pbData] = await Promise.all([
        catalogCpqService.listOfferings({
          search,
          type: TAB_TYPE[activeTab],
          is_active: STATUS_TO_IS_ACTIVE[statusFilter],
          page: isPriceBooks ? 1 : page,
          page_size: PAGE_SIZE,
        }),
        catalogCpqService.listPriceBooks({
          search,
          page: isPriceBooks ? page : 1,
          page_size: PAGE_SIZE,
        }),
      ]);
      setOfferings(offeringData.items || []);
      setOfferingsTotal(offeringData.total ?? 0);
      setPriceBooks(pbData.items || []);
      setPriceBooksTotal(pbData.total ?? 0);
      // The current page can disappear after an archive / restore; step back to the last real page.
      if (!isPriceBooks) {
        const lastPage = Math.max(1, Math.ceil((offeringData.total ?? 0) / PAGE_SIZE));
        if (page > lastPage) setPage(lastPage);
      }
    } catch (err) {
      setLoadError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, activeTab, statusFilter, page]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    void loadCounts();
  }, [loadCounts]);

  const changeTab = (tab: CatalogTab) => {
    setActiveTab(tab);
    setPage(1);
  };

  const changeStatusFilter = (value: StatusFilter) => {
    setStatusFilter(value);
    setPage(1);
  };

  const changeSearch = (value: string) => {
    setSearchQuery(value);
    setPage(1);
  };

  const loadPickerOfferings = useCallback(async () => {
    try {
      const res = await catalogCpqService.listOfferings({ is_active: true, page: 1, page_size: 100 });
      setPickerOfferings(res.items || []);
    } catch (err) {
      showToast('error', 'Could not load offerings', toApiError(err).message);
    }
  }, [showToast]);

  const openOfferingModal = (offering: OfferingOut | null) => {
    // Archived offerings are read-only; they must be unarchived before editing.
    if (offering && !offering.is_active) return;
    setEditingOffering(offering);
    setIsOfferingModalOpen(true);
    void loadPickerOfferings();
  };
  // Quick-action deep link (`/catalog?new=product`): open the new-offering form.
  useCreateDeepLink(() => openOfferingModal(null), canEdit);

  const openPriceBookModal = (pb: PriceBookOut | null) => {
    setEditingPriceBook(pb);
    setIsPriceBookModalOpen(true);
    void loadPickerOfferings();
  };

  const handleSaveOffering = async (data: OfferingIn) => {
    if (editingOffering) {
      await catalogCpqService.updateOffering(editingOffering.id, data);
    } else {
      await catalogCpqService.createOffering(data);
    }
    showToast('success', editingOffering ? 'Offering updated' : 'Offering created');
    await Promise.all([loadData(), loadCounts()]);
  };

  const handleConfirmArchive = async () => {
    if (!offeringToArchive) return;
    try {
      setIsArchiving(true);
      await catalogCpqService.archiveOffering(offeringToArchive.id);
      setOfferingToArchive(null);
      showToast('success', 'Offering archived');
      await Promise.all([loadData(), loadCounts()]);
    } catch (err) {
      showToast('error', 'Could not archive offering', toApiError(err).message);
    } finally {
      setIsArchiving(false);
    }
  };

  const handleConfirmUnarchive = async () => {
    if (!offeringToUnarchive) return;
    try {
      setIsArchiving(true);
      await catalogCpqService.unarchiveOffering(offeringToUnarchive.id);
      setOfferingToUnarchive(null);
      showToast('success', 'Offering unarchived');
      await Promise.all([loadData(), loadCounts()]);
    } catch (err) {
      setOfferingToUnarchive(null);
      showToast('error', 'Could not unarchive offering', toApiError(err).message);
    } finally {
      setIsArchiving(false);
    }
  };

  const handleSavePriceBook = async (data: PriceBookIn) => {
    if (editingPriceBook) {
      await catalogCpqService.updatePriceBook(editingPriceBook.id, data);
    } else {
      await catalogCpqService.createPriceBook(data);
    }
    showToast('success', editingPriceBook ? 'Price book updated' : 'Price book created');
    await loadData();
  };

  // Rows are already filtered server-side (type + search) and paginated.
  const filteredOfferings = offerings;
  const filteredPriceBooks = priceBooks;

  // KPI cards: always the ACTIVE catalog, independent of the status filter.
  const kpi = statusCounts.active;
  const activeCount = kpi.all;
  const productsCount = kpi.product;
  const servicesCount = kpi.service;
  const plansCount = kpi.plan;
  const bundlesCount = kpi.bundle;

  // Tab badges: follow the selected status filter.
  const tabCounts = statusCounts[statusFilter];

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-brand-50 rounded-xl text-brand-600 border border-brand-100">
              <Package className="w-5 h-5" />
            </div>
            <h1 className="text-xl font-bold text-slate-900" {...ui.edit('header')}>{ui.text('header', 'title')}</h1>
          </div>
          <p className="text-xs text-slate-500 mt-1" {...ui.edit('header')}>
            {ui.text('header', 'subtitle')}
          </p>
        </div>

        {canEdit && (
        <div className="flex items-center gap-2.5 shrink-0">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<BookOpen className="w-4 h-4 text-emerald-600" />}
            onClick={() => openPriceBookModal(null)}
            className="whitespace-nowrap font-medium"
          >
            New Price Book
          </Button>

          <Button
            variant="primary"
            size="sm"
            leadingIcon={<Plus className="w-4 h-4" />}
            onClick={() => openOfferingModal(null)}
            className="whitespace-nowrap font-semibold shadow-xs"
          >
            New Offering
          </Button>
        </div>
        )}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3.5" {...ui.edit('kpis')}>
        {ui.render('kpis', {
          active: (item, edit) => (
            <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-xl font-bold text-slate-900 mt-1">{activeCount}</p>
              {item.caption && <p className="text-[10px] text-slate-400 mt-0.5">{item.caption}</p>}
            </div>
          ),
          products: (item, edit) => (
            <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-xl font-bold text-blue-600 mt-1">{productsCount}</p>
              {item.caption && <p className="text-[10px] text-slate-400 mt-0.5">{item.caption}</p>}
            </div>
          ),
          services: (item, edit) => (
            <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-xl font-bold text-indigo-600 mt-1">{servicesCount}</p>
              {item.caption && <p className="text-[10px] text-slate-400 mt-0.5">{item.caption}</p>}
            </div>
          ),
          plans: (item, edit) => (
            <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-xl font-bold text-amber-600 mt-1">{plansCount}</p>
              {item.caption && <p className="text-[10px] text-slate-400 mt-0.5">{item.caption}</p>}
            </div>
          ),
          bundles: (item, edit) => (
            <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-xl font-bold text-purple-600 mt-1">{bundlesCount}</p>
              {item.caption && <p className="text-[10px] text-slate-400 mt-0.5">{item.caption}</p>}
            </div>
          ),
        })}
      </div>

      {/* Navigation Tabs & Search */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 border-b border-slate-200 pb-2">
        <div className="flex items-center gap-1 overflow-x-auto" {...ui.edit('tabs')}>
          {ui.shown('tabs').map((tab) => {
            // Counts follow the status filter (active / archived / all), from the server's summary.
            const countFor: Record<string, number> = {
              all: tabCounts.all,
              products: tabCounts.product,
              services: tabCounts.service,
              plans: tabCounts.plan,
              bundles: tabCounts.bundle,
              price_books: priceBooksTotal,
            };
            return (
              <button
                key={tab.key}
                {...ui.edit(`tabs.${tab.key}`)}
                onClick={() => changeTab(tab.key as CatalogTab)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                  activeTab === tab.key
                    ? 'bg-slate-900 text-white shadow-2xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                {tab.label}
                <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                  activeTab === tab.key ? 'bg-slate-800 text-slate-200' : 'bg-slate-200/70 text-slate-600'
                }`}>
                  {countFor[tab.key] ?? 0}
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2">
          {activeTab !== 'price_books' && (
            <div
              className="flex items-center gap-0.5 p-0.5 rounded-lg border border-slate-200 bg-white shrink-0"
              role="group"
              aria-label="Status filter"
            >
              {STATUS_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => changeStatusFilter(opt.id)}
                  aria-pressed={statusFilter === opt.id}
                  className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-colors ${
                    statusFilter === opt.id
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
          <div className="relative min-w-[220px]">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder={activeTab === 'price_books' ? 'Search price books by name, segment...' : 'Search offerings by SKU, name...'}
              aria-label={activeTab === 'price_books' ? 'Search price books' : 'Search offerings'}
              value={searchQuery}
              onChange={(e) => changeSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </div>
      </div>

      {/* Main Table Content */}
      {loadError ? (
        <ErrorState
          title="Couldn't load the catalog"
          message={loadError}
          onRetry={() => void loadData()}
        />
      ) : loading ? (
        <div className="py-12 bg-white rounded-xl border border-slate-200/80 flex items-center justify-center">
          <LoadingState message="Loading catalog offerings..." />
        </div>
      ) : activeTab === 'price_books' ? (
        /* Price Books Table */
        <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600 border-collapse">
            <thead className="bg-slate-50 border-b border-slate-200/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3">Price Book Name</th>
                <th className="px-4 py-3">Customer Segment</th>
                <th className="px-4 py-3">Currency</th>
                <th className="px-4 py-3">Active Overrides</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredPriceBooks.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-400 italic">
                    {searchQuery.trim()
                      ? `No Price Books match "${searchQuery.trim()}".`
                      : 'No Price Books configured yet. Click "New Price Book" to define a customer tier.'}
                  </td>
                </tr>
              ) : (
                filteredPriceBooks.map((pb) => (
                  <tr key={pb.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-4 py-3 font-semibold text-slate-900">
                      {pb.name}
                      {pb.is_default && (
                        <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
                          DEFAULT
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">{pb.customer_segment || 'General'}</td>
                    <td className="px-4 py-3 font-mono">{pb.currency}</td>
                    <td className="px-4 py-3">{pb.entries_count} items</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                        {pb.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {canEdit ? (
                        <Button variant="outline" size="sm" onClick={() => openPriceBookModal(pb)}>
                          Edit
                        </Button>
                      ) : (
                        <span className="text-[11px] text-slate-400">View only</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          </div>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={priceBooksTotal}
            onPageChange={setPage}
            itemLabel="price books"
          />
        </div>
      ) : (
        /* Offerings Table */
        <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600 border-collapse">
            <thead className="bg-slate-50 border-b border-slate-200/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <tr {...ui.edit('columns')}>
                {ui.shown('columns').map((col) => (
                  <th key={col.key} className={`px-4 py-3${col.key === 'actions' ? ' text-right' : ''}`} {...ui.edit(`columns.${col.key}`)}>
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredOfferings.length === 0 ? (
                <tr>
                  <td colSpan={ui.shown('columns').length} className="px-4 py-8 text-center text-slate-400 italic" {...ui.edit('empty')}>
                    {statusFilter === 'active' && !searchQuery.trim()
                      ? ui.text('empty', 'none')
                      : 'No offerings match the current filters.'}
                  </td>
                </tr>
              ) : (
                filteredOfferings.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                    {ui.shown('columns').map((col) => {
                      if (col.key === 'sku') {
                        return (
                          <td key="sku" className="px-4 py-3">
                            <p className="font-semibold text-slate-900">{item.name}</p>
                            <p className="text-[10px] font-mono text-slate-400">{item.sku}</p>
                          </td>
                        );
                      }
                      if (col.key === 'type') {
                        return (
                          <td key="type" className="px-4 py-3">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold capitalize ${
                              item.type === 'bundle'
                                ? 'bg-purple-50 text-purple-700 border border-purple-200'
                                : item.type === 'plan'
                                ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                : item.type === 'service'
                                ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                                : 'bg-blue-50 text-blue-700 border border-blue-200'
                            }`}>
                              {item.type}
                            </span>
                          </td>
                        );
                      }
                      if (col.key === 'accounting') {
                        return (
                          <td key="accounting" className="px-4 py-3">
                            <p className="capitalize">{item.category || item.pricing_model.replace('_', ' ')}</p>
                            <p className="text-[10px] text-slate-400">Tax: {item.tax_rate_pct}%</p>
                          </td>
                        );
                      }
                      if (col.key === 'pricing') {
                        return (
                          <td key="pricing" className="px-4 py-3 font-semibold text-slate-900">
                            {formatMoney(item.base_price, item.currency || 'INR')}
                            <span className="text-[10px] text-slate-400 font-normal ml-1">/ {item.unit}</span>
                          </td>
                        );
                      }
                      if (col.key === 'status') {
                        return (
                          <td key="status" className="px-4 py-3">
                            {item.is_active ? (
                              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600">
                                <CheckCircle2 className="w-3.5 h-3.5" /> Active
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400">
                                <XCircle className="w-3.5 h-3.5" /> Archived
                              </span>
                            )}
                          </td>
                        );
                      }
                      if (col.key === 'actions') {
                        return (
                          <td key="actions" className="px-4 py-3 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              {!canEdit && !canArchive && (
                                <span className="text-[11px] text-slate-400">View only</span>
                              )}
                              {canEdit && item.is_active && (
                              <button
                                onClick={() => openOfferingModal(item)}
                                className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                                title="Edit Offering"
                              >
                                <Edit2 className="w-3.5 h-3.5" />
                              </button>
                              )}
                              {canArchive && !item.is_active && (
                                <button
                                  onClick={() => setOfferingToUnarchive(item)}
                                  className="p-1 rounded text-slate-400 hover:text-emerald-600 hover:bg-emerald-50"
                                  title="Unarchive Offering"
                                >
                                  <ArchiveRestore className="w-3.5 h-3.5" />
                                </button>
                              )}
                              {canArchive && item.is_active && (
                                <button
                                  onClick={() => setOfferingToArchive(item)}
                                  className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50"
                                  title="Archive Offering"
                                >
                                  <Archive className="w-3.5 h-3.5" />
                                </button>
                              )}
                            </div>
                          </td>
                        );
                      }
                      return <td key={col.key} className="px-4 py-3" />;
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
          </div>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={offeringsTotal}
            onPageChange={setPage}
            itemLabel="offerings"
          />
        </div>
      )}

      {/* Offering Modal */}
      <OfferingModal
        isOpen={isOfferingModalOpen}
        onClose={() => setIsOfferingModalOpen(false)}
        onSave={handleSaveOffering}
        initialData={editingOffering}
        availableOfferings={pickerOfferings}
      />

      {/* Price Book Modal */}
      <PriceBookModal
        isOpen={isPriceBookModalOpen}
        onClose={() => setIsPriceBookModalOpen(false)}
        onSave={handleSavePriceBook}
        initialData={editingPriceBook}
        offerings={pickerOfferings}
      />

      {/* Archive Confirmation Dialog */}
      <ConfirmDialog
        isOpen={Boolean(offeringToArchive)}
        onClose={() => setOfferingToArchive(null)}
        onConfirm={handleConfirmArchive}
        title="Archive Commercial Offering"
        description={
          offeringToArchive
            ? `Are you sure you want to archive "${offeringToArchive.name}" (${offeringToArchive.sku})? This offering will be deactivated and cannot be added to new quotes or subscriptions.`
            : ''
        }
        confirmLabel="Archive"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={isArchiving}
      />
      {/* Unarchive Confirmation Dialog */}
      <ConfirmDialog
        isOpen={Boolean(offeringToUnarchive)}
        onClose={() => setOfferingToUnarchive(null)}
        onConfirm={handleConfirmUnarchive}
        title="Unarchive Commercial Offering"
        description={
          offeringToUnarchive
            ? `Unarchive "${offeringToUnarchive.name}" (${offeringToUnarchive.sku})? It will become active again and can be edited and added to new quotes or subscriptions.`
            : ''
        }
        confirmLabel="Unarchive"
        cancelLabel="Cancel"
        isLoading={isArchiving}
      />
    </div>
  );
}

export default CatalogPage;
