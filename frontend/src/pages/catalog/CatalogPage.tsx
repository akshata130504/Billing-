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
import type { OfferingOut, PriceBookOut, OfferingIn, PriceBookIn } from '../../types/catalog_cpq';
import { OfferingModal } from './components/OfferingModal';
import { PriceBookModal } from './components/PriceBookModal';

const PAGE_SIZE = 25;

type CatalogTab = 'all' | 'products' | 'services' | 'plans' | 'bundles' | 'price_books';

const TAB_TYPE: Partial<Record<CatalogTab, string>> = {
  products: 'product',
  services: 'service',
  plans: 'plan',
  bundles: 'bundle',
};

interface CatalogCounts {
  all: number;
  active: number;
  product: number;
  service: number;
  plan: number;
  bundle: number;
}

const EMPTY_COUNTS: CatalogCounts = { all: 0, active: 0, product: 0, service: 0, plan: 0, bundle: 0 };

export function CatalogPage() {
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canEdit = hasRole('finance');
  const canArchive = hasRole('admin');

  const [activeTab, setActiveTab] = useState<CatalogTab>('all');
  const [offerings, setOfferings] = useState<OfferingOut[]>([]);
  const [offeringsTotal, setOfferingsTotal] = useState(0);
  const [priceBooks, setPriceBooks] = useState<PriceBookOut[]>([]);
  const [priceBooksTotal, setPriceBooksTotal] = useState(0);
  const [counts, setCounts] = useState<CatalogCounts>(EMPTY_COUNTS);
  // Capped list of active offerings for the bundle / price-book pickers in the modals.
  const [pickerOfferings, setPickerOfferings] = useState<OfferingOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);

  // Modals state
  const [isOfferingModalOpen, setIsOfferingModalOpen] = useState(false);
  const [editingOffering, setEditingOffering] = useState<OfferingOut | null>(null);

  const [isPriceBookModalOpen, setIsPriceBookModalOpen] = useState(false);
  const [editingPriceBook, setEditingPriceBook] = useState<PriceBookOut | null>(null);

  // Archive confirmation state
  const [offeringToArchive, setOfferingToArchive] = useState<OfferingOut | null>(null);
  const [isArchiving, setIsArchiving] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const search = searchQuery.trim() || undefined;
      const isPriceBooks = activeTab === 'price_books';
      // KPI counts come from each filtered list's `total`, so they cover the
      // whole catalog rather than just the rows on this page.
      const count = (extra: { type?: string; is_active?: boolean }) =>
        catalogCpqService
          .listOfferings({ search, ...extra, page: 1, page_size: 1 })
          .then((r) => r.total ?? 0);
      const [offeringData, pbData, all, active, product, service, plan, bundle] = await Promise.all([
        catalogCpqService.listOfferings({
          search,
          type: TAB_TYPE[activeTab],
          page: isPriceBooks ? 1 : page,
          page_size: PAGE_SIZE,
        }),
        catalogCpqService.listPriceBooks({
          search,
          page: isPriceBooks ? page : 1,
          page_size: PAGE_SIZE,
        }),
        count({}),
        count({ is_active: true }),
        count({ type: 'product' }),
        count({ type: 'service' }),
        count({ type: 'plan' }),
        count({ type: 'bundle' }),
      ]);
      setOfferings(offeringData.items || []);
      setOfferingsTotal(offeringData.total ?? 0);
      setPriceBooks(pbData.items || []);
      setPriceBooksTotal(pbData.total ?? 0);
      setCounts({ all, active, product, service, plan, bundle });
    } catch (err) {
      setLoadError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, activeTab, page]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const changeTab = (tab: CatalogTab) => {
    setActiveTab(tab);
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
    setEditingOffering(offering);
    setIsOfferingModalOpen(true);
    void loadPickerOfferings();
  };

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
    await loadData();
  };

  const handleConfirmArchive = async () => {
    if (!offeringToArchive) return;
    try {
      setIsArchiving(true);
      await catalogCpqService.archiveOffering(offeringToArchive.id);
      setOfferingToArchive(null);
      showToast('success', 'Offering archived');
      await loadData();
    } catch (err) {
      showToast('error', 'Could not archive offering', toApiError(err).message);
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

  // KPI stats: organization-wide totals for the current search.
  const activeCount = counts.active;
  const productsCount = counts.product;
  const servicesCount = counts.service;
  const plansCount = counts.plan;
  const bundlesCount = counts.bundle;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-brand-50 rounded-xl text-brand-600 border border-brand-100">
              <Package className="w-5 h-5" />
            </div>
            <h1 className="text-xl font-bold text-slate-900">Commercial Product Catalog</h1>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Master commercial catalog answering "What does Rooman sell?" — products, services, subscriptions, and bundles.
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
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3.5">
        <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Active Offerings</p>
          <p className="text-xl font-bold text-slate-900 mt-1">{activeCount}</p>
        </div>
        <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Products</p>
          <p className="text-xl font-bold text-blue-600 mt-1">{productsCount}</p>
        </div>
        <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Services</p>
          <p className="text-xl font-bold text-indigo-600 mt-1">{servicesCount}</p>
        </div>
        <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Recurring Plans</p>
          <p className="text-xl font-bold text-amber-600 mt-1">{plansCount}</p>
        </div>
        <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Curated Bundles</p>
          <p className="text-xl font-bold text-purple-600 mt-1">{bundlesCount}</p>
        </div>
      </div>

      {/* Navigation Tabs & Search */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 border-b border-slate-200 pb-2">
        <div className="flex items-center gap-1 overflow-x-auto">
          {[
            { id: 'all', label: 'All Offerings', count: counts.all },
            { id: 'products', label: 'Products', count: productsCount },
            { id: 'services', label: 'Services', count: servicesCount },
            { id: 'plans', label: 'Plans', count: plansCount },
            { id: 'bundles', label: 'Bundles', count: bundlesCount },
            { id: 'price_books', label: 'Price Books', count: priceBooksTotal },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => changeTab(tab.id as CatalogTab)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                activeTab === tab.id
                  ? 'bg-slate-900 text-white shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              {tab.label}
              <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                activeTab === tab.id ? 'bg-slate-800 text-slate-200' : 'bg-slate-200/70 text-slate-600'
              }`}>
                {tab.count}
              </span>
            </button>
          ))}
        </div>

        <div className="relative min-w-[220px]">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search offerings by SKU, name..."
            value={searchQuery}
            onChange={(e) => changeSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
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
              <tr>
                <th className="px-4 py-3">Offering / SKU</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Pricing Model</th>
                <th className="px-4 py-3">Catalog Base Price</th>
                <th className="px-4 py-3">Frequency</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredOfferings.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400 italic">
                    No offerings found for this view. Create your first offering to get started.
                  </td>
                </tr>
              ) : (
                filteredOfferings.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-4 py-3">
                      <p className="font-semibold text-slate-900">{item.name}</p>
                      <p className="text-[10px] font-mono text-slate-400">{item.sku}</p>
                    </td>
                    <td className="px-4 py-3">
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
                    <td className="px-4 py-3 capitalize">{item.pricing_model.replace('_', ' ')}</td>
                    <td className="px-4 py-3 font-semibold text-slate-900">
                      ₹{item.base_price}
                      <span className="text-[10px] text-slate-400 font-normal ml-1">/ {item.unit}</span>
                    </td>
                    <td className="px-4 py-3 capitalize">{item.billing_frequency.replace('_', ' ')}</td>
                    <td className="px-4 py-3">
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
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {!canEdit && !canArchive && (
                          <span className="text-[11px] text-slate-400">View only</span>
                        )}
                        {canEdit && (
                        <button
                          onClick={() => openOfferingModal(item)}
                          className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                          title="Edit Offering"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
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
    </div>
  );
}

export default CatalogPage;
