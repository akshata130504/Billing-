import { useState, useEffect } from 'react';
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
import { catalogCpqService } from '../../services/catalogCpqService';
import type { OfferingOut, PriceBookOut, OfferingIn, PriceBookIn } from '../../types/catalog_cpq';
import { OfferingModal } from './components/OfferingModal';
import { PriceBookModal } from './components/PriceBookModal';

export function CatalogPage() {
  const [activeTab, setActiveTab] = useState<'all' | 'products' | 'services' | 'plans' | 'bundles' | 'price_books'>('all');
  const [offerings, setOfferings] = useState<OfferingOut[]>([]);
  const [priceBooks, setPriceBooks] = useState<PriceBookOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Modals state
  const [isOfferingModalOpen, setIsOfferingModalOpen] = useState(false);
  const [editingOffering, setEditingOffering] = useState<OfferingOut | null>(null);

  const [isPriceBookModalOpen, setIsPriceBookModalOpen] = useState(false);
  const [editingPriceBook, setEditingPriceBook] = useState<PriceBookOut | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const [offeringData, pbData] = await Promise.all([
        catalogCpqService.listOfferings({ search: searchQuery.trim() || undefined }),
        catalogCpqService.listPriceBooks(),
      ]);
      setOfferings(offeringData.items || []);
      setPriceBooks(pbData.items || []);
    } catch (err) {
      console.error('Failed to fetch catalog data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [searchQuery]);

  const handleSaveOffering = async (data: OfferingIn) => {
    if (editingOffering) {
      await catalogCpqService.updateOffering(editingOffering.id, data);
    } else {
      await catalogCpqService.createOffering(data);
    }
    await loadData();
  };

  const handleArchiveOffering = async (id: string) => {
    if (confirm('Are you sure you want to archive this commercial offering?')) {
      await catalogCpqService.archiveOffering(id);
      await loadData();
    }
  };

  const handleSavePriceBook = async (data: PriceBookIn) => {
    if (editingPriceBook) {
      await catalogCpqService.updatePriceBook(editingPriceBook.id, data);
    } else {
      await catalogCpqService.createPriceBook(data);
    }
    await loadData();
  };

  // Filter offerings based on active tab
  const filteredOfferings = offerings.filter((item) => {
    if (activeTab === 'all') return true;
    if (activeTab === 'products') return item.type === 'product';
    if (activeTab === 'services') return item.type === 'service';
    if (activeTab === 'plans') return item.type === 'plan';
    if (activeTab === 'bundles') return item.type === 'bundle';
    return true;
  });

  // KPI stats
  const activeCount = offerings.filter((o) => o.is_active).length;
  const productsCount = offerings.filter((o) => o.type === 'product').length;
  const servicesCount = offerings.filter((o) => o.type === 'service').length;
  const plansCount = offerings.filter((o) => o.type === 'plan').length;
  const bundlesCount = offerings.filter((o) => o.type === 'bundle').length;

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

        <div className="flex items-center gap-2.5 shrink-0">
          <Button
            variant="outline"
            size="sm"
            leadingIcon={<BookOpen className="w-4 h-4 text-emerald-600" />}
            onClick={() => {
              setEditingPriceBook(null);
              setIsPriceBookModalOpen(true);
            }}
            className="whitespace-nowrap font-medium"
          >
            New Price Book
          </Button>

          <Button
            variant="primary"
            size="sm"
            leadingIcon={<Plus className="w-4 h-4" />}
            onClick={() => {
              setEditingOffering(null);
              setIsOfferingModalOpen(true);
            }}
            className="whitespace-nowrap font-semibold shadow-xs"
          >
            New Offering
          </Button>
        </div>
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
            { id: 'all', label: 'All Offerings', count: offerings.length },
            { id: 'products', label: 'Products', count: productsCount },
            { id: 'services', label: 'Services', count: servicesCount },
            { id: 'plans', label: 'Plans', count: plansCount },
            { id: 'bundles', label: 'Bundles', count: bundlesCount },
            { id: 'price_books', label: 'Price Books', count: priceBooks.length },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
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
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
      </div>

      {/* Main Table Content */}
      {loading ? (
        <div className="py-12 bg-white rounded-xl border border-slate-200/80 flex items-center justify-center">
          <LoadingState message="Loading catalog offerings..." />
        </div>
      ) : activeTab === 'price_books' ? (
        /* Price Books Table */
        <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
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
              {priceBooks.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-400 italic">
                    No Price Books configured yet. Click "New Price Book" to define a customer tier.
                  </td>
                </tr>
              ) : (
                priceBooks.map((pb) => (
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
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEditingPriceBook(pb);
                          setIsPriceBookModalOpen(true);
                        }}
                      >
                        Edit
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : (
        /* Offerings Table */
        <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
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
                        <button
                          onClick={() => {
                            setEditingOffering(item);
                            setIsOfferingModalOpen(true);
                          }}
                          className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                          title="Edit Offering"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        {item.is_active && (
                          <button
                            onClick={() => handleArchiveOffering(item.id)}
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
      )}

      {/* Offering Modal */}
      <OfferingModal
        isOpen={isOfferingModalOpen}
        onClose={() => setIsOfferingModalOpen(false)}
        onSave={handleSaveOffering}
        initialData={editingOffering}
        availableOfferings={offerings}
      />

      {/* Price Book Modal */}
      <PriceBookModal
        isOpen={isPriceBookModalOpen}
        onClose={() => setIsPriceBookModalOpen(false)}
        onSave={handleSavePriceBook}
        initialData={editingPriceBook}
        offerings={offerings}
      />
    </div>
  );
}

export default CatalogPage;
