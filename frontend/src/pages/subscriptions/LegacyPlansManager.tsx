import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pencil, Power, Repeat, Search } from 'lucide-react';
import { Modal } from '../../components/common/Modal';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { LoadingState } from '../../components/common/LoadingState';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { catalogService } from '../../services/catalogService';
import type { PlanOut, ProductOut } from '../../types/api';
import { formatMoney } from '../../utils/format';

/**
 * Manage the legacy subscription catalog (/products + /plans) that subscriptions bill
 * from: edit commercial fields and activate/deactivate products and plans.
 *
 * Structural plan fields (interval, interval count, pricing model, currency) are not
 * editable here - the API rejects them (409) while a plan has live subscriptions;
 * create a new plan and move subscribers instead.
 */
interface LegacyPlansManagerProps {
  isOpen: boolean;
  onClose: () => void;
  /** Called after any successful change so callers can refresh plan pickers. */
  onChanged?: () => void;
}

interface PlanDraft {
  name: string;
  description: string;
  unit_amount: string;
  setup_fee: string;
  trial_days: string;
}

const MONEY_RE = /^\d{1,12}(\.\d{1,2})?$/;

function apiError(err: any): string {
  return err?.response?.data?.error?.message || err?.message || 'Request failed';
}

export function LegacyPlansManager({ isOpen, onClose, onChanged }: LegacyPlansManagerProps) {
  const { showToast } = useToast();
  const { hasRole } = useAuth();
  const canWrite = hasRole('finance');

  const [products, setProducts] = useState<ProductOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editing, setEditing] = useState<PlanOut | null>(null);
  const [draft, setDraft] = useState<PlanDraft | null>(null);
  const [draftErrors, setDraftErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await catalogService.listProducts({ page_size: 100 });
      setProducts(res.items ?? []);
    } catch (err: any) {
      showToast('error', 'Failed to load catalog', apiError(err));
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    if (isOpen) {
      setEditing(null);
      setDraft(null);
      load();
    }
  }, [isOpen, load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return products;
    return products
      .map((p) => {
        const productHit = p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q);
        const plans = productHit
          ? p.plans
          : p.plans.filter((pl) => pl.name.toLowerCase().includes(q) || pl.code.toLowerCase().includes(q));
        return { ...p, plans };
      })
      .filter((p) => p.plans.length > 0 || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q));
  }, [products, search]);

  const toggleProduct = async (product: ProductOut) => {
    try {
      setBusyId(product.id);
      await catalogService.updateProduct(product.id, { is_active: !product.is_active });
      showToast('success', product.is_active ? 'Product deactivated' : 'Product activated', product.name);
      await load();
      onChanged?.();
    } catch (err: any) {
      showToast('error', 'Update failed', apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const togglePlan = async (plan: PlanOut) => {
    try {
      setBusyId(plan.id);
      await catalogService.updatePlan(plan.id, { is_active: !plan.is_active });
      showToast(
        'success',
        plan.is_active ? 'Plan deactivated' : 'Plan activated',
        plan.is_active && plan.active_subscriptions > 0
          ? `${plan.name}: existing ${plan.active_subscriptions} subscription(s) keep billing; no new ones can start.`
          : plan.name
      );
      await load();
      onChanged?.();
    } catch (err: any) {
      showToast('error', 'Update failed', apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const toggleAutopay = async (plan: PlanOut) => {
    try {
      setBusyId(plan.id);
      await catalogService.updatePlan(plan.id, { autopay_enabled: !plan.autopay_enabled });
      showToast(
        'success',
        plan.autopay_enabled ? 'AutoPay turned off' : 'AutoPay turned on',
        plan.autopay_enabled
          ? `${plan.name}: no new AutoPay mandates; existing ones keep collecting until stopped.`
          : `${plan.name}: subscriptions can now be collected by UPI AutoPay / e-mandate.`
      );
      await load();
      onChanged?.();
    } catch (err: any) {
      showToast('error', 'Update failed', apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const startEdit = (plan: PlanOut) => {
    setEditing(plan);
    setDraftErrors({});
    setDraft({
      name: plan.name,
      description: plan.description ?? '',
      unit_amount: plan.unit_amount,
      setup_fee: plan.setup_fee,
      trial_days: String(plan.trial_days ?? 0),
    });
  };

  const saveEdit = async () => {
    if (!editing || !draft) return;
    const errs: Record<string, string> = {};
    if (!draft.name.trim()) errs.name = 'Name is required.';
    else if (draft.name.trim().length > 200) errs.name = 'Name must be 200 characters or fewer.';
    if (!MONEY_RE.test(draft.unit_amount.trim())) errs.unit_amount = 'Enter a non-negative amount (max 2 decimals).';
    if (!MONEY_RE.test(draft.setup_fee.trim())) errs.setup_fee = 'Enter a non-negative amount (max 2 decimals).';
    const trial = Number(draft.trial_days);
    if (!Number.isInteger(trial) || trial < 0 || trial > 3650) errs.trial_days = 'Whole number of days, 0-3650.';
    setDraftErrors(errs);
    if (Object.keys(errs).length) return;
    try {
      setBusyId(editing.id);
      await catalogService.updatePlan(editing.id, {
        name: draft.name.trim(),
        description: draft.description.trim() || null,
        unit_amount: draft.unit_amount.trim(),
        setup_fee: draft.setup_fee.trim(),
        trial_days: trial,
      } as any);
      showToast(
        'success',
        'Plan updated',
        editing.active_subscriptions > 0
          ? 'New price applies to new subscriptions; existing ones keep their contracted price snapshot.'
          : draft.name.trim()
      );
      setEditing(null);
      setDraft(null);
      await load();
      onChanged?.();
    } catch (err: any) {
      showToast('error', 'Update failed', apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const inputCls =
    'w-full text-xs p-2 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 text-slate-900';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={editing ? `Edit plan ${editing.code}` : 'Subscription Plans & Products'}
      description={
        editing
          ? 'Interval, pricing model and currency are locked while a plan has live subscriptions.'
          : 'The legacy catalog subscriptions bill from. Deactivated items cannot be used for new subscriptions.'
      }
      size="xl"
      footer={
        editing ? (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setEditing(null);
                setDraft(null);
              }}
              disabled={busyId === editing.id}
            >
              Back
            </Button>
            <Button variant="primary" size="sm" onClick={saveEdit} isLoading={busyId === editing.id}>
              Save Plan
            </Button>
          </>
        ) : (
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        )
      }
    >
      {editing && draft ? (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="sm:col-span-2">
              <label className="block text-xs font-medium text-slate-700 mb-1">Name</label>
              <input className={inputCls} value={draft.name} maxLength={200} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              {draftErrors.name && <p className="mt-1 text-[11px] text-rose-600">{draftErrors.name}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Unit amount ({editing.currency})</label>
              <input className={inputCls} inputMode="decimal" value={draft.unit_amount} onChange={(e) => setDraft({ ...draft, unit_amount: e.target.value })} />
              {draftErrors.unit_amount && <p className="mt-1 text-[11px] text-rose-600">{draftErrors.unit_amount}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Setup fee ({editing.currency})</label>
              <input className={inputCls} inputMode="decimal" value={draft.setup_fee} onChange={(e) => setDraft({ ...draft, setup_fee: e.target.value })} />
              {draftErrors.setup_fee && <p className="mt-1 text-[11px] text-rose-600">{draftErrors.setup_fee}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Trial days</label>
              <input className={inputCls} type="number" min={0} max={3650} step={1} value={draft.trial_days} onChange={(e) => setDraft({ ...draft, trial_days: e.target.value })} />
              {draftErrors.trial_days && <p className="mt-1 text-[11px] text-rose-600">{draftErrors.trial_days}</p>}
            </div>
            <div className="text-[11px] text-slate-500 self-end pb-2">
              {editing.billing_interval} x{editing.interval_count} Â· {editing.pricing_model} Â· {editing.active_subscriptions} live subscription(s)
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs font-medium text-slate-700 mb-1">Description</label>
              <textarea className={inputCls} rows={2} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
            </div>
          </div>
        </div>
      ) : loading ? (
        <div className="py-10">
          <LoadingState message="Loading catalog..." />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search products or plans..."
              className="pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 w-full text-slate-900"
            />
          </div>
          {filtered.length === 0 ? (
            <p className="text-xs text-slate-500 py-6 text-center">No products or plans found.</p>
          ) : (
            <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
              {filtered.map((product) => (
                <div key={product.id} className="rounded-lg border border-slate-200">
                  <div className="flex items-center justify-between gap-3 px-3 py-2 bg-slate-50 rounded-t-lg">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-slate-900 truncate">
                        {product.name} <span className="font-mono text-slate-400">{product.sku}</span>
                      </p>
                      <p className="text-[11px] text-slate-500">Tax {product.tax_rate_pct}%</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={product.is_active ? 'success' : 'neutral'} size="sm">
                        {product.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                      {canWrite && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleProduct(product)}
                          isLoading={busyId === product.id}
                          leadingIcon={<Power className="w-3.5 h-3.5" />}
                        >
                          {product.is_active ? 'Deactivate' : 'Activate'}
                        </Button>
                      )}
                    </div>
                  </div>
                  {product.plans.length === 0 ? (
                    <p className="px-3 py-2 text-[11px] text-slate-400">No plans.</p>
                  ) : (
                    <table className="w-full text-left text-xs">
                      <tbody className="divide-y divide-slate-100">
                        {product.plans.map((plan) => (
                          <tr key={plan.id}>
                            <td className="px-3 py-2">
                              <div className="font-medium text-slate-900">{plan.name}</div>
                              <div className="text-[11px] text-slate-400 font-mono">{plan.code}</div>
                            </td>
                            <td className="px-3 py-2 text-slate-600 capitalize">
                              {plan.billing_interval} Â· {plan.pricing_model.replace('_', ' ')}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums text-slate-900">
                              {formatMoney(plan.unit_amount, plan.currency)}
                            </td>
                            <td className="px-3 py-2 text-slate-500">{plan.active_subscriptions} live</td>
                            <td className="px-3 py-2">
                              <Badge variant={plan.is_active ? 'success' : 'neutral'} size="sm">
                                {plan.is_active ? 'Active' : 'Inactive'}
                              </Badge>
                              {plan.autopay_enabled && (
                                <Badge variant="info" size="sm" className="ml-1">
                                  AutoPay
                                </Badge>
                              )}
                            </td>
                            <td className="px-3 py-2 text-right">
                              {canWrite && (
                                <div className="flex items-center justify-end gap-1">
                                  <button
                                    onClick={() => startEdit(plan)}
                                    className="p-1 text-slate-400 hover:text-brand-600 rounded"
                                    title="Edit plan"
                                  >
                                    <Pencil className="w-3.5 h-3.5" />
                                  </button>
                                  {plan.billing_interval !== 'one_time' && plan.currency === 'INR' && (
                                    <button
                                      onClick={() => toggleAutopay(plan)}
                                      disabled={busyId === plan.id}
                                      className={`p-1 rounded disabled:opacity-50 ${
                                        plan.autopay_enabled ? 'text-brand-600 hover:text-slate-500' : 'text-slate-400 hover:text-brand-600'
                                      }`}
                                      title={plan.autopay_enabled ? 'Turn off UPI AutoPay / e-mandate' : 'Allow UPI AutoPay / e-mandate'}
                                      aria-pressed={Boolean(plan.autopay_enabled)}
                                    >
                                      <Repeat className="w-3.5 h-3.5" />
                                    </button>
                                  )}
                                  <button
                                    onClick={() => togglePlan(plan)}
                                    disabled={busyId === plan.id}
                                    className="p-1 text-slate-400 hover:text-rose-600 rounded disabled:opacity-50"
                                    title={plan.is_active ? 'Deactivate plan' : 'Activate plan'}
                                  >
                                    <Power className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

export default LegacyPlansManager;
