import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
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
} from 'lucide-react';
import { Button } from '../../components/common/Button';
import { LoadingState } from '../../components/common/LoadingState';
import { PlanModal } from './components/PlanModal';
import { planPricingService } from '../../services/planPricingService';
import type { PlanPricingItem, CreatePlanPricingInput } from '../../types/plans_pricing';

export function PlansPricingPage() {
  const [plans, setPlans] = useState<PlanPricingItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'all' | 'active' | 'draft' | 'archived'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPricingModel, setSelectedPricingModel] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'name' | 'price' | 'created_at'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const [isPlanModalOpen, setIsPlanModalOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<PlanPricingItem | null>(null);

  const fetchPlans = async () => {
    setIsLoading(true);
    try {
      const res = await planPricingService.listPlans();
      setPlans(res.items);
    } catch (err) {
      console.error('Failed to fetch plans', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchPlans();
  }, []);

  // Dashboard KPIs
  const kpis = useMemo(() => {
    const total = plans.length;
    const active = plans.filter((p) => p.status === 'active' || p.is_active).length;
    const draft = plans.filter((p) => p.status === 'draft').length;
    const archived = plans.filter((p) => p.status === 'archived' || !p.is_active).length;
    const prices = plans.map((p) => Number(p.base_price || 0));
    const avgPrice = prices.length > 0 ? prices.reduce((a, b) => a + b, 0) / prices.length : 0;
    return { total, active, draft, archived, avgPrice };
  }, [plans]);

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
    await fetchPlans();
  };

  const handleClonePlan = async (plan: PlanPricingItem) => {
    try {
      await planPricingService.clonePlan(plan.id);
      await fetchPlans();
    } catch (err) {
      console.error('Failed to clone plan', err);
    }
  };

  const handleToggleStatus = async (plan: PlanPricingItem) => {
    try {
      await planPricingService.updatePlan(plan.id, {
        is_active: !plan.is_active,
        status: plan.is_active ? 'archived' : 'active',
      });
      await fetchPlans();
    } catch (err) {
      console.error('Failed to toggle plan status', err);
    }
  };

  const handleDeletePlan = async (planId: string) => {
    if (confirm('Are you sure you want to permanently delete this pricing plan?')) {
      try {
        await planPricingService.deletePlan(planId);
        await fetchPlans();
      } catch (err) {
        console.error('Failed to delete plan', err);
      }
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 animate-in fade-in duration-150">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900">Plans & Pricing</h1>
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
              Commercial Engine
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Manage recurring subscriptions, dynamic volume & graduated tiers, discrete packages, and pricing simulations.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link to="/plans-pricing/simulator">
            <Button variant="outline" size="sm" leadingIcon={<Calculator className="w-4 h-4 text-indigo-600" />}>
              Pricing Simulator
            </Button>
          </Link>
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
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Active Plans</p>
          <p className="text-2xl font-bold text-emerald-600 mt-1">{kpis.active}</p>
          <p className="text-[11px] text-slate-500 mt-0.5">Ready for quotes & checkout</p>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Draft Plans</p>
          <p className="text-2xl font-bold text-amber-600 mt-1">{kpis.draft}</p>
          <p className="text-[11px] text-slate-500 mt-0.5">In configuration</p>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Archived Plans</p>
          <p className="text-2xl font-bold text-slate-500 mt-1">{kpis.archived}</p>
          <p className="text-[11px] text-slate-500 mt-0.5">Legacy & deactivated</p>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Avg Plan Rate</p>
          <p className="text-2xl font-bold text-slate-900 mt-1">₹{Math.round(kpis.avgPrice).toLocaleString('en-IN')}</p>
          <p className="text-[11px] text-slate-500 mt-0.5">Base recurring benchmark</p>
        </div>
      </div>

      {/* Tabs & Filters Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          {/* Tabs */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl text-xs font-semibold text-slate-600">
            {(['all', 'active', 'draft', 'archived'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-3 py-1.5 rounded-lg capitalize transition-all ${
                  activeTab === tab ? 'bg-white text-slate-900 shadow-2xs font-bold' : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                {tab}
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
                onChange={(e) => setSearchQuery(e.target.value)}
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
              onClick={fetchPlans}
              title="Refresh"
              leadingIcon={<RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />}
            />
          </div>
        </div>
      </div>

      {/* Plans Table */}
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
        {isLoading ? (
          <div className="py-16">
            <LoadingState message="Loading plans & pricing configurations..." />
          </div>
        ) : (
          <table className="w-full text-left text-xs text-slate-600 border-collapse">
            <thead className="bg-slate-50 border-b border-slate-200/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <tr>
                <th
                  className="px-4 py-3 cursor-pointer hover:text-slate-900"
                  onClick={() => {
                    if (sortBy === 'name') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
                    else { setSortBy('name'); setSortOrder('asc'); }
                  }}
                >
                  Plan / Code {sortBy === 'name' ? (sortOrder === 'asc' ? '↑' : '↓') : ''}
                </th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Pricing Model</th>
                <th
                  className="px-4 py-3 cursor-pointer hover:text-slate-900"
                  onClick={() => {
                    if (sortBy === 'price') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
                    else { setSortBy('price'); setSortOrder('asc'); }
                  }}
                >
                  Price / Rate {sortBy === 'price' ? (sortOrder === 'asc' ? '↑' : '↓') : ''}
                </th>
                <th className="px-4 py-3">Billing Frequency</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredPlans.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-400 italic">
                    No pricing plans found matching your filters. Click &quot;New Plan&quot; to create one.
                  </td>
                </tr>
              ) : (
                filteredPlans.map((plan) => (
                  <tr key={plan.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-4 py-3">
                      <p className="font-semibold text-slate-900">{plan.name}</p>
                      <p className="text-[10px] font-mono text-slate-400">{plan.code || plan.sku}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700">
                        {plan.category || 'General'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
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
                    <td className="px-4 py-3 font-semibold text-slate-900">
                      ₹{Number(plan.base_price).toLocaleString('en-IN')}
                      <span className="text-[10px] text-slate-400 font-normal ml-1">/ {plan.unit}</span>
                    </td>
                    <td className="px-4 py-3 capitalize">{plan.billing_frequency.replace('_', ' ')}</td>
                    <td className="px-4 py-3">
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
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
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
                        <button
                          onClick={() => handleDeletePlan(plan.id)}
                          className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50"
                          title="Delete Plan"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

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
