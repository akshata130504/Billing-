import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UserCheck,
  Search,
  TrendingUp,
  AlertTriangle,
  RefreshCw,
  Clock,
  ShieldCheck,
  ChevronRight,
  HeartHandshake,
  Repeat,
} from 'lucide-react';
import { lifecycleService } from '../../services/lifecycleService';
import type {
  CustomerLifecycleItem,
  CustomerLifecycleStage,
  CustomerLifecycleUpdate,
  HealthStatus,
  LifecycleKPIs,
} from '../../types/api';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { StatCard } from '../../components/common/StatCard';
import { LoadingState } from '../../components/common/LoadingState';
import { EmptyState } from '../../components/common/EmptyState';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { formatMoney } from '../../utils/format';

const STAGE_CONFIG: Record<
  CustomerLifecycleStage,
  { label: string; color: string; bg: string; text: string; badge: 'success' | 'info' | 'warning' | 'danger' | 'neutral' }
> = {
  prospect: { label: 'Prospect', color: 'text-slate-600', bg: 'bg-slate-100', text: 'text-slate-700', badge: 'neutral' },
  onboarding: { label: 'Onboarding', color: 'text-blue-600', bg: 'bg-blue-50', text: 'text-blue-700', badge: 'info' },
  active: { label: 'Active', color: 'text-emerald-600', bg: 'bg-emerald-50', text: 'text-emerald-700', badge: 'success' },
  renewal_due: { label: 'Renewal Due', color: 'text-amber-600', bg: 'bg-amber-50', text: 'text-amber-700', badge: 'warning' },
  expansion: { label: 'Expansion', color: 'text-purple-600', bg: 'bg-purple-50', text: 'text-purple-700', badge: 'info' },
  at_risk: { label: 'At Risk', color: 'text-rose-600', bg: 'bg-rose-50', text: 'text-rose-700', badge: 'danger' },
  churned: { label: 'Churned', color: 'text-slate-400', bg: 'bg-slate-100', text: 'text-slate-500', badge: 'neutral' },
};

const HEALTH_CONFIG: Record<
  HealthStatus,
  { label: string; color: string; bg: string; badge: 'success' | 'info' | 'warning' | 'danger' }
> = {
  healthy: { label: 'Healthy', color: 'text-emerald-600', bg: 'bg-emerald-500', badge: 'success' },
  neutral: { label: 'Neutral', color: 'text-slate-600', bg: 'bg-slate-400', badge: 'info' },
  at_risk: { label: 'At Risk', color: 'text-amber-600', bg: 'bg-amber-500', badge: 'warning' },
  critical: { label: 'Critical', color: 'text-rose-600', bg: 'bg-rose-500', badge: 'danger' },
};

export function CustomerLifecycleListPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canWrite = hasRole('finance') || hasRole('admin');

  const [items, setItems] = useState<CustomerLifecycleItem[]>([]);
  const [kpis, setKpis] = useState<LifecycleKPIs | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStage, setSelectedStage] = useState<string>('all');
  const [selectedHealth, setSelectedHealth] = useState<string>('all');

  // Stage update modal
  const [editItem, setEditItem] = useState<CustomerLifecycleItem | null>(null);
  const [editStage, setEditStage] = useState<CustomerLifecycleStage>('active');
  const [editHealth, setEditHealth] = useState<HealthStatus>('healthy');
  const [editScore, setEditScore] = useState<number>(85);
  const [editNextAction, setEditNextAction] = useState<string>('');
  const [editNotes, setEditNotes] = useState<string>('');

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [kpiData, listData] = await Promise.all([
        lifecycleService.kpis(),
        lifecycleService.list({
          stage: selectedStage !== 'all' ? (selectedStage as CustomerLifecycleStage) : undefined,
          health: selectedHealth !== 'all' ? (selectedHealth as HealthStatus) : undefined,
          search: searchQuery || undefined,
        }),
      ]);
      setKpis(kpiData);
      setItems(listData);
    } catch (err: any) {
      showToast('error', err.message || 'Failed to load customer lifecycle data');
    } finally {
      setLoading(false);
    }
  }, [selectedStage, selectedHealth, searchQuery, showToast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleOpenEditModal = (item: CustomerLifecycleItem) => {
    setEditItem(item);
    setEditStage(item.lifecycle_stage);
    setEditHealth(item.health_status);
    setEditScore(item.health_score);
    setEditNextAction(item.next_action || '');
    setEditNotes(item.notes || '');
  };

  const handleSaveStage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editItem) return;
    try {
      setActionLoading(true);
      const updatePayload: CustomerLifecycleUpdate = {
        lifecycle_stage: editStage,
        health_status: editHealth,
        health_score: editScore,
        next_action: editNextAction || null,
        notes: editNotes || null,
      };
      await lifecycleService.update(editItem.customer_id, updatePayload);
      showToast('success', `Updated lifecycle stage for ${editItem.customer_name}`);
      setEditItem(null);
      loadData();
    } catch (err: any) {
      showToast('error', err.message || 'Failed to update lifecycle stage');
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-1">
            <HeartHandshake className="w-4 h-4" />
            Customer Experience
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Customer Lifecycle</h1>
          <p className="text-sm text-slate-500 mt-1">
            Track customer relationship stages, revenue health, and operational engagement in one unified place.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => loadData()}>
            <RefreshCw className="w-4 h-4 mr-1.5" />
            Refresh
          </Button>
          <Button variant="primary" size="sm" onClick={() => navigate('/customers/new')}>
            New Customer
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard
          title="Total Customers"
          value={kpis?.total_customers ?? 0}
          icon={<UserCheck className="w-4 h-4" />}
        />
        <StatCard
          title="Onboarding"
          value={kpis?.new_onboarding_count ?? 0}
          icon={<Clock className="w-4 h-4" />}
        />
        <StatCard
          title="Active Accounts"
          value={kpis?.active_customers_count ?? 0}
          icon={<ShieldCheck className="w-4 h-4" />}
        />
        <StatCard
          title="Renewals Due"
          value={kpis?.renewal_due_count ?? 0}
          icon={<Repeat className="w-4 h-4" />}
        />
        <StatCard
          title="At-Risk Accounts"
          value={kpis?.at_risk_count ?? 0}
          icon={<AlertTriangle className="w-4 h-4" />}
        />
        <StatCard
          title="Expansion Deals"
          value={kpis?.expansion_count ?? 0}
          icon={<TrendingUp className="w-4 h-4" />}
        />
      </div>

      {/* Filters & Search */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search customer name, account number, company, email..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-colors"
            />
          </div>
          <div className="flex items-center gap-2 w-full md:w-auto">
            <select
              value={selectedStage}
              onChange={(e) => setSelectedStage(e.target.value)}
              className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Stages</option>
              <option value="prospect">Prospect</option>
              <option value="onboarding">Onboarding</option>
              <option value="active">Active</option>
              <option value="renewal_due">Renewal Due</option>
              <option value="expansion">Expansion</option>
              <option value="at_risk">At Risk</option>
              <option value="churned">Churned</option>
            </select>
            <select
              value={selectedHealth}
              onChange={(e) => setSelectedHealth(e.target.value)}
              className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Health</option>
              <option value="healthy">Healthy</option>
              <option value="neutral">Neutral</option>
              <option value="at_risk">At Risk</option>
              <option value="critical">Critical</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-16">
            <LoadingState message="Loading customer lifecycles..." />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            title="No customer lifecycles found"
            description="No customers match your current filter criteria."
            icon={<UserCheck className="w-8 h-8 text-slate-400" />}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-5 py-3.5">Customer</th>
                  <th className="px-5 py-3.5">Lifecycle Stage</th>
                  <th className="px-5 py-3.5">Health Score</th>
                  <th className="px-5 py-3.5">Total Revenue</th>
                  <th className="px-5 py-3.5">Amount Due</th>
                  <th className="px-5 py-3.5">Active Subs</th>
                  <th className="px-5 py-3.5">Logged Hours</th>
                  <th className="px-5 py-3.5">Next Action</th>
                  <th className="px-5 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item) => {
                  const stageConf = STAGE_CONFIG[item.lifecycle_stage] || STAGE_CONFIG.active;
                  const healthConf = HEALTH_CONFIG[item.health_status] || HEALTH_CONFIG.healthy;
                  const hasOverdue = parseFloat(item.amount_due) > 0;

                  return (
                    <tr
                      key={item.id}
                      className="hover:bg-slate-50/70 transition-colors cursor-pointer group"
                      onClick={() => navigate(`/customer-lifecycle/${item.customer_id}`)}
                    >
                      <td className="px-5 py-4">
                        <div className="font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">
                          {item.customer_name}
                        </div>
                        <div className="text-xs text-slate-400 flex items-center gap-1.5 mt-0.5">
                          <span>{item.customer_number}</span>
                          {item.company_name && (
                            <>
                              <span>•</span>
                              <span>{item.company_name}</span>
                            </>
                          )}
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <Badge variant={stageConf.badge}>
                          {stageConf.label}
                        </Badge>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div
                              className={`h-full ${healthConf.bg} transition-all duration-300`}
                              style={{ width: `${item.health_score}%` }}
                            />
                          </div>
                          <span className="text-xs font-semibold text-slate-700">
                            {item.health_score}%
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-4 font-medium text-slate-900">
                        {formatMoney(item.total_spent)}
                      </td>
                      <td className="px-5 py-4 font-medium">
                        <span className={hasOverdue ? 'text-rose-600 font-semibold' : 'text-slate-500'}>
                          {formatMoney(item.amount_due)}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-slate-700 font-medium">
                        {item.active_subscriptions_count}
                      </td>
                      <td className="px-5 py-4 text-slate-700">
                        {item.total_billable_hours} hrs
                      </td>
                      <td className="px-5 py-4 max-w-xs truncate text-xs text-slate-500">
                        {item.next_action ? (
                          <div className="flex items-center gap-1 text-slate-700 font-medium truncate">
                            <Clock className="w-3 h-3 text-slate-400 flex-shrink-0" />
                            <span className="truncate">{item.next_action}</span>
                          </div>
                        ) : (
                          <span className="text-slate-400 italic">None scheduled</span>
                        )}
                      </td>
                      <td className="px-5 py-4 text-right">
                        <div
                          className="flex items-center justify-end gap-2"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {canWrite && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-xs"
                              onClick={() => handleOpenEditModal(item)}
                            >
                              Update
                            </Button>
                          )}
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-xs flex items-center gap-1"
                            onClick={() => navigate(`/customer-lifecycle/${item.customer_id}`)}
                          >
                            <span>360°</span>
                            <ChevronRight className="w-3 h-3" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Stage Transition Modal */}
      {editItem && (
        <Modal
          isOpen={!!editItem}
          onClose={() => setEditItem(null)}
          title={`Update Lifecycle: ${editItem.customer_name}`}
        >
          <form onSubmit={handleSaveStage} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Lifecycle Stage
              </label>
              <select
                value={editStage}
                onChange={(e) => setEditStage(e.target.value as CustomerLifecycleStage)}
                className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              >
                <option value="prospect">Prospect</option>
                <option value="onboarding">Onboarding</option>
                <option value="active">Active Customer</option>
                <option value="renewal_due">Renewal Due</option>
                <option value="expansion">Expansion / Upsell</option>
                <option value="at_risk">At Risk</option>
                <option value="churned">Churned</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Health Status
                </label>
                <select
                  value={editHealth}
                  onChange={(e) => setEditHealth(e.target.value as HealthStatus)}
                  className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                >
                  <option value="healthy">Healthy</option>
                  <option value="neutral">Neutral</option>
                  <option value="at_risk">At Risk</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Health Score (0 - 100%)
                </label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={editScore}
                  onChange={(e) => setEditScore(parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Next Expected Action
              </label>
              <input
                type="text"
                placeholder="e.g. Schedule quarterly business review"
                value={editNextAction}
                onChange={(e) => setEditNextAction(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Internal Account Notes
              </label>
              <textarea
                rows={3}
                placeholder="Key relationship updates, executive sponsor notes, commercial details..."
                value={editNotes}
                onChange={(e) => setEditNotes(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
              <Button variant="ghost" size="sm" type="button" onClick={() => setEditItem(null)}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" type="submit" disabled={actionLoading}>
                {actionLoading ? 'Saving...' : 'Save Lifecycle'}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
