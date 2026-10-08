import { useState, useEffect, useMemo, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Plus,
  Search,
  RefreshCw,
  Calculator,
  Edit2,
  Copy,
  Archive,
  Trash2,
  CheckCircle2,
  XCircle,
  Repeat,
} from 'lucide-react';
import { Button } from '../../components/common/Button';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { Pagination } from '../../components/common/Pagination';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';
import { PlanModal } from './components/PlanModal';
import { planPricingService } from '../../services/planPricingService';
import { currencySymbol } from '../../utils/format';
import type { PlanPricingItem, CreatePlanPricingInput } from '../../types/plans_pricing';
import { usePageSpec } from '../../appUi/usePageSpec';

const PAGE_SIZE = 25;

export function PlansPricingPage() {
  const ui = usePageSpec('plans_pricing');
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const navigate = useNavigate();
  const canEdit = hasRole('finance');
  const canDelete = hasRole('admin');

  const [plans, setPlans] = useState<PlanPricingItem[]>([]);
  const [totalPlans, setTotalPlans] = useState(0);
  const [counts, setCounts] = useState({ active: 0, archived: 0 });
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [planToDelete, setPlanToDelete] = useState<PlanPricingItem | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'active' | 'draft' | 'archived'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPricingModel, setSelectedPricingModel] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'name' | 'price' | 'created_at'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const [isPlanModalOpen, setIsPlanModalOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<PlanPricingItem | null>(null);

  // Tab + search are applied by the server so every plan is reachable via
  // pagination; model filter and sorting apply to the loaded page.
  const fetchPlans = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const search = searchQuery.trim() || undefined;
      const isActive =
        activeTab === 'active' ? true : activeTab === 'archived' ? false : undefined;
      if (activeTab === 'draft') {
        // Plans are catalog offerings, which have no draft state on the backend.
        setPlans([]);
        setTotalPlans(0);
      } else {
        const res = await planPricingService.listPlans({ search, is_active: isActive, page, page_size: PAGE_SIZE });
        setPlans(res.items);
        setTotalPlans(res.total ?? res.items.length);
      }
      const [activeRes, archivedRes] = await Promise.all([
        planPricingService.listPlans({ search, is_active: true, page: 1, page_size: 1 }),
        planPricingService.listPlans({ search, is_active: false, page: 1, page_size: 1 }),
      ]);
      setCounts({ active: activeRes.total ?? 0, archived: archivedRes.total ?? 0 });
    } catch (err) {
      setLoadError(toApiError(err).message);
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, activeTab, page]);

  useEffect(() => {
    void fetchPlans();
  }, [fetchPlans]);

  // Dashboard KPIs
  const kpis = useMemo(() => {
    const draft = plans.filter((p) => p.status === 'draft').length;
    const prices = plans.map((p) => Number(p.base_price || 0));
    const avgPrice = prices.length > 0 ? prices.reduce((a, b) => a + b, 0) / prices.length : 0;
    return { active: counts.active, draft, archived: counts.archived, avgPrice };
  }, [plans, counts]);

  // Filtered & Sorted Plans
  const filteredPlans = useMemo(() => {
    return plans
      .filter((plan) => {
        // Tab filter
        if (activeTab === 'active' && !plan.is_active && plan.status !== 'active') return false;
        if (activeTab === 'draft' && plan.status !== 'draft') return false;
        if (activeTab === 'archived' && plan.is_active && plan.status !== 'archived') return false;

        // Model filter
        if (selectedPricingModel !== 'all' && plan.pricing_model !== selectedPricingModel) return false;

        // Search query
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          const matchName = plan.name.toLowerCase().includes(q);
          const matchCode = (plan.code || plan.sku || '').toLowerCase().includes(q);
          const matchCat = (plan.category || '').toLowerCase().includes(q);
          if (!matchName && !matchCode && !matchCat) return false;
        }

        return true;
      })
      .sort((a, b) => {
        if (sortBy === 'name') {
          return sortOrder === 'asc' ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name);
        }
        if (sortBy === 'price') {
          const pA = Number(a.base_price || 0);
          const pB = Number(b.base_price || 0);
          return sortOrder === 'asc' ? pA - pB : pB - pA;
        }
        const tA = new Date(a.created_at || 0).getTime();
        const tB = new Date(b.created_at || 0).getTime();
        return sortOrder === 'asc' ? tA - tB : tB - tA;
      });
  }, [plans, activeTab, selectedPricingModel, searchQuery, sortBy, sortOrder]);

  const handleSavePlan = async (data: CreatePlanPricingInput) => {
    if (editingPlan) {
      await planPricingService.updatePlan(editingPlan.id, data);
    } else {
      await planPricingService.createPlan(data);
    }
    showToast('success', editingPlan ? 'Plan updated' : 'Plan created');
    await fetchPlans();
  };

  const handleClonePlan = async (plan: PlanPricingItem) => {
    try {
      await planPricingService.clonePlan(plan.id);
      showToast('success', 'Plan cloned', `A copy of "${plan.name}" was created.`);
      await fetchPlans();
    } catch (err) {
      showToast('error', 'Could not clone plan', toApiError(err).message);
    }
  };

  const handleToggleStatus = async (plan: PlanPricingItem) => {
    try {
      await planPricingService.updatePlan(plan.id, {
        is_active: !plan.is_active,
        status: plan.is_active ? 'archived' : 'active',
      });
      showToast('success', plan.is_active ? 'Plan archived' : 'Plan activated');
      await fetchPlans();
    } catch (err) {
      showToast('error', 'Could not update plan status', toApiError(err).message);
    }
  };

  const handleConfirmDelete = async () => {
    if (!planToDelete) return;
    setIsDeleting(true);
    try {
      await planPricingService.deletePlan(planToDelete.id);
      setPlanToDelete(null);
      showToast('success', 'Plan deleted');
      await fetchPlans();
    } catch (err) {
      showToast('error', 'Could not delete plan', toApiError(err).message);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 animate-in fade-in duration-150">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900" {...ui.edit('header')}>{ui.text('header', 'title')}</h1>
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200" {...ui.edit('header')}>
              {ui.text('header', 'badge')}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5" {...ui.edit('header')}>
            {ui.text('header', 'subtitle')}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link to="/plans-pricing/simulator">
            <Button variant="outline" size="sm" leadingIcon={<Calculator className="w-4 h-4 text-indigo-600" />}>
              Pricing Simulator
            </Button>
          </Link>
          {canEdit && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setEditingPlan(null);
                setIsPlanModalOpen(true);
              }}
              leadingIcon={<Plus className="w-4 h-4" />}
            >
              New Plan
            </Button>
          )}
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4" {...ui.edit('kpis')}>
        {ui.render('kpis', {
          active: (item, edit) => (
            <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-2xl font-bold text-emerald-600 mt-1">{kpis.active}</p>
              {item.caption && <p className="text-[11px] text-slate-500 mt-0.5">{item.caption}</p>}
            </div>
          ),
          draft: (item, edit) => (
            <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-2xl font-bold text-amber-600 mt-1">{kpis.draft}</p>
              {item.caption && <p className="text-[11px] text-slate-500 mt-0.5">{item.caption}</p>}
            </div>
          ),
          archived: (item, edit) => (
            <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-2xl font-bold text-slate-500 mt-1">{kpis.archived}</p>
              {item.caption && <p className="text-[11px] text-slate-500 mt-0.5">{item.caption}</p>}
            </div>
          ),
          avg_rate: (item, edit) => (
            <div className="min-w-0 bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-2xl font-bold text-slate-900 mt-1 min-w-0 break-all tabular-nums">₹{Math.round(kpis.avgPrice).toLocaleString('en-IN')}</p>
              {item.caption && <p className="text-[11px] text-slate-500 mt-0.5">{item.caption}</p>}
            </div>
          ),
        })}
      </div>

      {/* Tabs & Filters Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          {/* Tabs */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl text-xs font-semibold text-slate-600" {...ui.edit('tabs')}>
            {ui.shown('tabs').map((tab) => (
              <button
                key={tab.key}
                {...ui.edit(`tabs.${tab.key}`)}
                onClick={() => {
                  setActiveTab(tab.key as any);
                  setPage(1);
                }}
                className={`px-3 py-1.5 rounded-lg capitalize transition-all ${
                  activeTab === tab.key ? 'bg-white text-slate-900 shadow-2xs font-bold' : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Search & Model Filter */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(1);
                }}
                placeholder="Search plan name, code..."
                className="pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-slate-50/50 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800 w-56"
              />
            </div>

            <select
              value={selectedPricingModel}
              onChange={(e) => setSelectedPricingModel(e.target.value)}
              className="px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 bg-white font-medium text-slate-700 focus:outline-hidden focus:ring-2 focus:ring-slate-900/10"
            >
              <option value="all">All Models</option>
              <option value="flat">Flat</option>
              <option value="per_unit">Per Unit</option>
              <option value="volume">Volume</option>
              <option value="tiered">Tiered / Graduated</option>
              <option value="package">Package</option>
            </select>

            <Button
              variant="outline"
              size="sm"
              onClick={() => void fetchPlans()}
              title="Refresh"
              leadingIcon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
            />
          </div>
        </div>
      </div>

      {/* Plans Table */}
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
        {loadError ? (
          <ErrorState
            title="Couldn't load plans"
            message={loadError}
            onRetry={() => void fetchPlans()}
            className="rounded-none border-0"
          />
        ) : isLoading ? (
          <div className="py-16">
            <LoadingState message="Loading plans & pricing configurations..." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600 border-collapse">
            <thead className="bg-slate-50 border-b border-slate-200/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <tr {...ui.edit('columns')}>
                {ui.shown('columns').map((col) => (
                  <th
                    key={col.key}
                    className={`px-4 py-3${col.key === 'actions' ? ' text-right' : ''}${col.key === 'plan_name' || col.key === 'base_price' ? ' cursor-pointer hover:text-slate-900' : ''}`}
                    {...ui.edit(`columns.${col.key}`)}
                    onClick={() => {
                      if (col.key === 'plan_name') {
                        if (sortBy === 'name') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
                        else { setSortBy('name'); setSortOrder('asc'); }
                      } else if (col.key === 'base_price') {
                        if (sortBy === 'price') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
                        else { setSortBy('price'); setSortOrder('asc'); }
                      }
                    }}
                  >
                    {col.label}
                    {col.key === 'plan_name' && sortBy === 'name' ? (sortOrder === 'asc' ? ' ↑' : ' ↓') : ''}
                    {col.key === 'base_price' && sortBy === 'price' ? (sortOrder === 'asc' ? ' ↑' : ' ↓') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredPlans.length === 0 ? (
                <tr>
                  <td colSpan={ui.shown('columns').length} className="px-4 py-12 text-center text-slate-400 italic" {...ui.edit('empty')}>
                    {ui.text('empty', 'none')}
                  </td>
                </tr>
              ) : (
                filteredPlans.map((plan) => (
                  <tr key={plan.id} className="hover:bg-slate-50/80 transition-colors">
                    {ui.shown('columns').map((col) => {
                      if (col.key === 'plan_name') {
                        return (
                          <td key="plan_name" className="px-4 py-3">
                            <p className="font-semibold text-slate-900">{plan.name}</p>
                            <p className="text-[10px] font-mono text-slate-400">{plan.code || plan.sku}</p>
                          </td>
                        );
                      }
                      if (col.key === 'code') {
                        return (
                          <td key="code" className="px-4 py-3">
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700">
                              {plan.category || 'General'}
                            </span>
                          </td>
                        );
                      }
                      if (col.key === 'pricing_model') {
                        return (
                          <td key="pricing_model" className="px-4 py-3">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold capitalize ${
                                plan.pricing_model === 'tiered'
                                  ? 'bg-purple-50 text-purple-700 border border-purple-200'
                                  : plan.pricing_model === 'volume'
                                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                                  : plan.pricing_model === 'package'
                                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                  : plan.pricing_model === 'flat'
                                  ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                                  : 'bg-slate-100 text-slate-700'
                              }`}
                            >
                              {plan.pricing_model.replace('_', ' ')}
                            </span>
                            {plan.pricing_tiers && plan.pricing_tiers.length > 0 && (
                              <span className="text-[10px] text-slate-400 block mt-0.5">
                                {plan.pricing_tiers.length} {plan.pricing_model === 'package' ? 'packages' : 'tiers'}
                              </span>
                            )}
                          </td>
                        );
                      }
                      if (col.key === 'base_price') {
                        return (
                          <td key="base_price" className="px-4 py-3 font-semibold text-slate-900 min-w-0 max-w-[16rem] break-all tabular-nums">
                            {currencySymbol(plan.currency)}{Number(plan.base_price).toLocaleString((plan.currency || 'INR') === 'INR' ? 'en-IN' : 'en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
                            <span className="text-[10px] text-slate-400 font-normal ml-1">/ {plan.unit}</span>
                          </td>
                        );
                      }
                      if (col.key === 'billing_interval') {
                        return (
                          <td key="billing_interval" className="px-4 py-3 capitalize">{plan.billing_frequency.replace('_', ' ')}</td>
                        );
                      }
                      if (col.key === 'status') {
                        return (
                          <td key="status" className="px-4 py-3">
                            {plan.is_active ? (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600">
                                <CheckCircle2 className="w-3.5 h-3.5" /> Active
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400">
                                <XCircle className="w-3.5 h-3.5" /> Archived
                              </span>
                            )}
                          </td>
                        );
                      }
                      if (col.key === 'actions') {
                        return (
                          <td key="actions" className="px-4 py-3 text-right">
                            <div className="flex items-center justify-end gap-1">
                              {!canEdit && <span className="text-[11px] text-slate-400">View only</span>}
                              {canEdit && (
                              <>
                              {plan.is_active && (
                              <button
                                onClick={() => {
                                  setEditingPlan(plan);
                                  setIsPlanModalOpen(true);
                                }}
                                className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                                title="Edit Plan"
                              >
                                <Edit2 className="w-3.5 h-3.5" />
                              </button>
                              )}
                              {plan.is_active && plan.billing_frequency !== 'one_time' && (
                                <button
                                  onClick={() => navigate(`/subscriptions/new?offering_id=${plan.id}`)}
                                  className="p-1 rounded text-slate-400 hover:text-emerald-600 hover:bg-emerald-50"
                                  title="Create subscription"
                                  aria-label={`Create subscription on ${plan.name}`}
                                >
                                  <Repeat className="w-3.5 h-3.5" />
                                </button>
                              )}
                              <button
                                onClick={() => handleClonePlan(plan)}
                                className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"
                                title="Clone Plan"
                              >
                                <Copy className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => handleToggleStatus(plan)}
                                className="p-1 rounded text-slate-400 hover:text-amber-600 hover:bg-amber-50"
                                title={plan.is_active ? 'Archive Plan' : 'Activate Plan'}
                              >
                                <Archive className="w-3.5 h-3.5" />
                              </button>
                              </>
                              )}
                              {canDelete && (
                              <button
                                onClick={() => setPlanToDelete(plan)}
                                className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50"
                                title="Delete Plan"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
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
        )}
        {!loadError && !isLoading && (
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={totalPlans}
            onPageChange={setPage}
            itemLabel="plans"
          />
        )}
      </div>

      <ConfirmDialog
        isOpen={Boolean(planToDelete)}
        onClose={() => setPlanToDelete(null)}
        onConfirm={() => void handleConfirmDelete()}
        title="Delete pricing plan"
        description={
          planToDelete
            ? `Are you sure you want to permanently delete "${planToDelete.name}"? This cannot be undone.`
            : ''
        }
        confirmLabel="Delete"
        variant="danger"
        isLoading={isDeleting}
      />

      {/* Create / Edit Plan Modal */}
      <PlanModal
        isOpen={isPlanModalOpen}
        onClose={() => setIsPlanModalOpen(false)}
        onSave={handleSavePlan}
        initialData={editingPlan}
      />
    </div>
  );
}

export default PlansPricingPage;
