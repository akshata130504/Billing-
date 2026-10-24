import { useState, useEffect, useCallback } from 'react';
import {
  Calculator,
  Plus,
  CheckCircle2,
  Clock,
  ArrowRight,
  FileText,
  Info,
  ChevronDown,
  ChevronUp,
  UserPlus,
  Search,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../../../components/common/Button';
import { ConfirmDialog } from '../../../components/common/ConfirmDialog';
import { LoadingState } from '../../../components/common/LoadingState';
import { ErrorState } from '../../../components/common/ErrorState';
import { Pagination } from '../../../components/common/Pagination';
import { useToast } from '../../../components/common/Toast';
import { useAuth } from '../../../hooks/useAuth';
import { cpqDealActions } from './cpqDealActions';
import { toApiError } from '../../../services/apiClient';
import { catalogCpqService } from '../../../services/catalogCpqService';
import { dashboardSummaryService } from '../../../services/dashboardSummaryService';
import { customerService } from '../../../services/customerService';
import type { CPQDealOut, OfferingOut, PriceBookOut, PriceSimulationResponse } from '../../../types/catalog_cpq';
import type { CustomerOut } from '../../../types/api';
import { usePageSpec } from '../../../appUi/usePageSpec';
import { formatMoney } from '../../../utils/format';

const PAGE_SIZE = 20;

export function CPQPage() {
  const ui = usePageSpec('cpq');
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { hasRole, user } = useAuth();
  const canEdit = hasRole('finance');
  const canApprove = hasRole('admin');

  const [deals, setDeals] = useState<CPQDealOut[]>([]);
  const [dealsTotal, setDealsTotal] = useState(0);
  const [dealCounts, setDealCounts] = useState({ total: 0, pending: 0, approved: 0, converted: 0 });
  const [page, setPage] = useState(1);
  // Customer search results for the wizard (queried from the server as the user types).
  const [customers, setCustomers] = useState<CustomerOut[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerOut | null>(null);
  const [offerings, setOfferings] = useState<OfferingOut[]>([]);
  const [priceBooks, setPriceBooks] = useState<PriceBookOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Deal Builder Wizard State
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState<number>(1);
  const [dealTitle, setDealTitle] = useState('');
  const [selectedCustomerId, setSelectedCustomerId] = useState('');
  const [customerSearchText, setCustomerSearchText] = useState('');
  const [isCustomerDropdownOpen, setIsCustomerDropdownOpen] = useState(false);
  const [showQuickCreateCustomer, setShowQuickCreateCustomer] = useState(false);
  const [newCustomerName, setNewCustomerName] = useState('');
  const [newCustomerEmail, setNewCustomerEmail] = useState('');
  const [isCreatingCustomer, setIsCreatingCustomer] = useState(false);
  const [selectedPriceBookId, setSelectedPriceBookId] = useState('');
  const [dealItems, setDealItems] = useState<Array<{ offering_id: string; quantity: number; discount_pct: number }>>([]);
  const [dealDiscountPct, setDealDiscountPct] = useState<number>(0);
  const [simulation, setSimulation] = useState<PriceSimulationResponse | null>(null);
  const [expandedExplanation, setExpandedExplanation] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [dealToConvert, setDealToConvert] = useState<string | null>(null);
  const [isConverting, setIsConverting] = useState(false);

  // Load existing deals and prerequisites
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const [dealData, offeringData, pbData, summary] =
        await Promise.all([
          catalogCpqService.listDeals({ page, page_size: PAGE_SIZE }),
          catalogCpqService.listOfferings({ is_active: true, page_size: 100 }),
          catalogCpqService.listPriceBooks({ status: 'active', page_size: 100 }),
          dashboardSummaryService.deals(),
        ]);
      setDeals(dealData.items || []);
      setDealsTotal(dealData.total ?? 0);
      setDealCounts({
        total: summary.total_count,
        pending: summary.groups.pending,
        approved: summary.groups.approved,
        converted: summary.groups.converted,
      });
      setOfferings(offeringData.items || []);
      setPriceBooks(pbData.items || []);
    } catch (err) {
      setLoadError(toApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Server-side customer search for the wizard, so every customer is findable.
  const selectedCustomerLabel = selectedCustomer
    ? `${selectedCustomer.display_name} (${selectedCustomer.customer_number})`
    : '';
  useEffect(() => {
    if (!isWizardOpen || !isCustomerDropdownOpen) return;
    const text = customerSearchText.trim();
    const search = text && text !== selectedCustomerLabel ? text : undefined;
    let cancelled = false;
    const timer = setTimeout(() => {
      customerService
        .list({ search, page: 1, page_size: 20 })
        .then((res) => {
          if (!cancelled) setCustomers(res.items || []);
        })
        .catch((err) => {
          if (!cancelled) showToast('error', 'Could not search customers', toApiError(err).message);
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [isWizardOpen, isCustomerDropdownOpen, customerSearchText, selectedCustomerLabel, showToast]);

  // Run simulation whenever items or price book changes in Step 3 / 4
  const triggerSimulation = async () => {
    if (dealItems.length === 0) return;
    try {
      const res = await catalogCpqService.simulatePricing({
        customer_id: selectedCustomerId || undefined,
        price_book_id: selectedPriceBookId || undefined,
        items: dealItems.map((item) => ({
          offering_id: item.offering_id,
          quantity: item.quantity,
          custom_discount_pct: item.discount_pct,
        })),
        deal_discount_pct: dealDiscountPct,
      });
      setSimulation(res);
    } catch (err) {
      showToast('error', 'Price simulation failed', toApiError(err).message);
    }
  };

  const handleAddItem = (offeringId: string) => {
    const existingIdx = dealItems.findIndex((i) => i.offering_id === offeringId);
    if (existingIdx >= 0) {
      const updated = [...dealItems];
      updated[existingIdx].quantity += 1;
      setDealItems(updated);
    } else {
      setDealItems([...dealItems, { offering_id: offeringId, quantity: 1, discount_pct: 0 }]);
    }
  };

  const handleRemoveItem = (offeringId: string) => {
    setDealItems(dealItems.filter((i) => i.offering_id !== offeringId));
  };

  const handleCreateDeal = async () => {
    try {
      setIsSubmitting(true);
      await catalogCpqService.createDeal({
        title: dealTitle || `Deal for ${selectedCustomer?.display_name ?? 'customer'}`,
        customer_id: selectedCustomerId,
        price_book_id: selectedPriceBookId || undefined,
        discount_pct: dealDiscountPct,
        items: dealItems,
      });
      setIsWizardOpen(false);
      resetWizard();
      showToast('success', 'Deal created');
      await loadData();
    } catch (err) {
      showToast('error', 'Failed to create deal', toApiError(err).message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Results are already filtered by the server-side search above.
  const filteredCustomers = customers;

  const handleQuickCreateCustomer = async () => {
    if (!newCustomerName.trim()) return;
    try {
      setIsCreatingCustomer(true);
      const created = await customerService.create({
        display_name: newCustomerName.trim(),
        email: newCustomerEmail.trim() || undefined,
        currency: 'INR',
      });
      // Select the newly created customer
      setCustomers((prev) => [created, ...prev]);
      setSelectedCustomer(created);
      setSelectedCustomerId(created.id);
      setCustomerSearchText(`${created.display_name} (${created.customer_number})`);
      setShowQuickCreateCustomer(false);
      setNewCustomerName('');
      setNewCustomerEmail('');
    } catch (err) {
      showToast('error', 'Failed to create customer', toApiError(err).message);
    } finally {
      setIsCreatingCustomer(false);
    }
  };

  const resetWizard = () => {
    setWizardStep(1);
    setDealTitle('');
    setSelectedCustomerId('');
    setSelectedCustomer(null);
    setCustomerSearchText('');
    setIsCustomerDropdownOpen(false);
    setShowQuickCreateCustomer(false);
    setNewCustomerName('');
    setNewCustomerEmail('');
    setSelectedPriceBookId('');
    setDealItems([]);
    setDealDiscountPct(0);
    setSimulation(null);
  };

  const handleConvertToQuote = (dealId: string) => {
    setDealToConvert(dealId);
  };

  const handleConfirmConvert = async () => {
    if (!dealToConvert) return;
    try {
      setIsConverting(true);
      const quote = await catalogCpqService.convertToQuote(dealToConvert);
      setDealToConvert(null);
      navigate(`/quotes/${quote.id}`);
    } catch (err) {
      showToast('error', 'Failed to convert deal to quote', toApiError(err).message);
    } finally {
      setIsConverting(false);
    }
  };

  const handleApproveDeal = async (dealId: string) => {
    try {
      await catalogCpqService.approveDeal(dealId);
      showToast('success', 'Deal approved');
      await loadData();
    } catch (err) {
      showToast('error', 'Failed to approve deal', toApiError(err).message);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-emerald-50 rounded-xl text-emerald-600 border border-emerald-100">
              <Calculator className="w-5 h-5" />
            </div>
            <h1 className="text-xl font-bold text-slate-900" {...ui.edit('header')}>{ui.text('header', 'title')}</h1>
          </div>
          <p className="text-xs text-slate-500 mt-1" {...ui.edit('header')}>
            {ui.text('header', 'subtitle')}
          </p>
        </div>

        {canEdit && (
          <div className="shrink-0">
            <Button
              variant="primary"
              size="sm"
              leadingIcon={<Plus className="w-4 h-4" />}
              onClick={() => {
                resetWizard();
                setIsWizardOpen(true);
              }}
              className="whitespace-nowrap px-4 py-2 font-semibold shadow-xs"
            >
              Start New Deal
            </Button>
          </div>
        )}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5" {...ui.edit('kpis')}>
        {ui.render('kpis', {
          total: (item, edit) => (
            <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-xl font-bold text-slate-900 mt-1">{dealCounts.total}</p>
              {item.caption && <p className="text-[10px] text-slate-400 mt-0.5">{item.caption}</p>}
            </div>
          ),
          pending: (item, edit) => (
            <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-xl font-bold text-amber-600 mt-1">{dealCounts.pending}</p>
              {item.caption && <p className="text-[10px] text-slate-400 mt-0.5">{item.caption}</p>}
            </div>
          ),
          approved: (item, edit) => (
            <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-xl font-bold text-emerald-600 mt-1">{dealCounts.approved}</p>
              {item.caption && <p className="text-[10px] text-slate-400 mt-0.5">{item.caption}</p>}
            </div>
          ),
          converted: (item, edit) => (
            <div className="p-4 bg-white rounded-xl border border-slate-200/80 shadow-2xs" {...edit}>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{item.label}</p>
              <p className="text-xl font-bold text-brand-600 mt-1">{dealCounts.converted}</p>
              {item.caption && <p className="text-[10px] text-slate-400 mt-0.5">{item.caption}</p>}
            </div>
          ),
        })}
      </div>

      {/* Deals List */}
      {loadError ? (
        <ErrorState title="Couldn't load CPQ deals" message={loadError} onRetry={() => void loadData()} />
      ) : loading ? (
        <div className="py-12 bg-white rounded-xl border border-slate-200/80 flex items-center justify-center">
          <LoadingState message="Loading configured deals..." />
        </div>
      ) : (
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
              {deals.length === 0 ? (
                <tr>
                  <td colSpan={ui.shown('columns').length} className="px-4 py-10 text-center text-slate-400 italic" {...ui.edit('empty')}>
                    {ui.text('empty', 'none')}
                  </td>
                </tr>
              ) : (
                deals.map((deal) => (
                  <tr key={deal.id} className="hover:bg-slate-50/80 transition-colors">
                    {ui.shown('columns').map((col) => {
                      if (col.key === 'deal') {
                        return (
                          <td key="deal" className="px-4 py-3">
                            <p className="font-semibold text-slate-900">{deal.title}</p>
                            <p className="text-[10px] font-mono text-slate-400">{deal.deal_number}</p>
                          </td>
                        );
                      }
                      if (col.key === 'customer') {
                        return (
                          <td key="customer" className="px-4 py-3">
                            <p className="font-medium text-slate-800">{deal.customer_name}</p>
                            <p className="text-[10px] text-slate-400">{deal.customer_number}</p>
                          </td>
                        );
                      }
                      if (col.key === 'price_book') {
                        return (
                          <td key="price_book" className="px-4 py-3">
                            {deal.price_book_name ? (
                              <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700">
                                {deal.price_book_name}
                              </span>
                            ) : (
                              <span className="text-slate-400">Standard Catalog</span>
                            )}
                          </td>
                        );
                      }
                      if (col.key === 'total') {
                        return (
                          <td key="total" className="px-4 py-3 font-semibold text-slate-900">
                            {formatMoney(deal.total, deal.currency)}
                          </td>
                        );
                      }
                      if (col.key === 'status') {
                        return (
                          <td key="status" className="px-4 py-3">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                              deal.status === 'converted'
                                ? 'bg-blue-50 text-blue-700 border border-blue-200'
                                : deal.status === 'approved'
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : deal.status === 'pending_approval'
                                ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                : 'bg-slate-100 text-slate-700 border border-slate-200'
                            }`}>
                              {deal.status.replace('_', ' ')}
                            </span>
                          </td>
                        );
                      }
                      if (col.key === 'actions') {
                        const actions = cpqDealActions(deal, { userId: user?.id, canEdit, canApprove });
                        return (
                          <td key="actions" className="px-4 py-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              {actions.showApprove && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleApproveDeal(deal.id)}
                                  className="text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                                >
                                  Approve
                                </Button>
                              )}
                              {actions.showConvert && (
                                <Button
                                  variant="primary"
                                  size="sm"
                                  onClick={() => handleConvertToQuote(deal.id)}
                                  className="flex items-center gap-1"
                                >
                                  <FileText className="w-3.5 h-3.5" /> Convert to Quote
                                </Button>
                              )}
                              {actions.note === 'Quote Generated' ? (
                                <span className="text-[11px] font-semibold text-blue-600 flex items-center gap-1">
                                  <CheckCircle2 className="w-3.5 h-3.5" /> Quote Generated
                                </span>
                              ) : actions.note ? (
                                <span className="text-[11px] text-slate-400">{actions.note}</span>
                              ) : null}
                            </div>
                          </td>
                        );
                      }
                      return null;
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
          </div>
          <Pagination page={page} pageSize={PAGE_SIZE} total={dealsTotal} onPageChange={setPage} itemLabel="deals" />
        </div>
      )}

      {/* Guided Deal Builder Wizard Modal */}
      {isWizardOpen && (
        <div className="fixed inset-0 z-50 !m-0 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs overflow-y-auto">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-4xl overflow-hidden my-8 flex flex-col max-h-[90vh]">
            {/* Wizard Header & Stepper */}
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="p-2 bg-brand-50 rounded-lg text-brand-600">
                    <Calculator className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-slate-900">CPQ Deal Builder</h3>
                    <p className="text-xs text-slate-500">Step {wizardStep} of 4: Customer, Offerings, and Rules</p>
                  </div>
                </div>
                <button
                  onClick={() => setIsWizardOpen(false)}
                  className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100"
                >
                  ✕
                </button>
              </div>

              {/* Progress Steps */}
              <div className="grid grid-cols-4 gap-2 text-center text-xs font-semibold">
                <div className={`p-2 rounded-lg ${wizardStep >= 1 ? 'bg-brand-50 text-brand-700 border border-brand-200' : 'bg-white text-slate-400'}`}>
                  1. Customer & Segment
                </div>
                <div className={`p-2 rounded-lg ${wizardStep >= 2 ? 'bg-brand-50 text-brand-700 border border-brand-200' : 'bg-white text-slate-400'}`}>
                  2. Offerings & Add-ons
                </div>
                <div className={`p-2 rounded-lg ${wizardStep >= 3 ? 'bg-brand-50 text-brand-700 border border-brand-200' : 'bg-white text-slate-400'}`}>
                  3. Pricing & Discounts
                </div>
                <div className={`p-2 rounded-lg ${wizardStep >= 4 ? 'bg-brand-50 text-brand-700 border border-brand-200' : 'bg-white text-slate-400'}`}>
                  4. "Why This Price?"
                </div>
              </div>
            </div>

            {/* Wizard Body */}
            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              {/* STEP 1: Customer Selection & Price Book */}
              {wizardStep === 1 && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Deal Title *</label>
                    <input
                      type="text"
                      value={dealTitle}
                      onChange={(e) => setDealTitle(e.target.value)}
                      placeholder="e.g. Acme Corp Cloud Transformation Q3"
                      className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                  </div>

                  {/* Searchable Customer Combobox & Inline Quick-Create */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="block text-xs font-semibold text-slate-700">Select Customer *</label>
                      <button
                        type="button"
                        onClick={() => setShowQuickCreateCustomer(!showQuickCreateCustomer)}
                        className="text-[11px] font-semibold text-brand-600 hover:text-brand-700 flex items-center gap-1"
                      >
                        <UserPlus className="w-3.5 h-3.5 shrink-0" />
                        {showQuickCreateCustomer ? 'Cancel New Customer' : '+ New Customer'}
                      </button>
                    </div>

                    {showQuickCreateCustomer ? (
                      <div className="p-3 bg-brand-50/50 rounded-xl border border-brand-200/80 space-y-2.5 animate-in fade-in duration-150">
                        <p className="text-[11px] font-bold text-brand-900">Quick Add Customer</p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <input
                            type="text"
                            placeholder="Customer / Company Name *"
                            value={newCustomerName}
                            onChange={(e) => setNewCustomerName(e.target.value)}
                            className="px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500 font-medium"
                          />
                          <input
                            type="email"
                            placeholder="Email Address"
                            value={newCustomerEmail}
                            onChange={(e) => setNewCustomerEmail(e.target.value)}
                            className="px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                          />
                        </div>
                        <div className="flex justify-end">
                          <Button
                            variant="primary"
                            size="sm"
                            type="button"
                            disabled={isCreatingCustomer || !newCustomerName.trim()}
                            onClick={handleQuickCreateCustomer}
                            className="text-xs h-7 px-3"
                          >
                            {isCreatingCustomer ? 'Creating...' : 'Save & Select'}
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="relative">
                        <div className="relative">
                          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                          <input
                            type="text"
                            placeholder="Type to search or write customer name..."
                            value={customerSearchText}
                            onChange={(e) => {
                              setCustomerSearchText(e.target.value);
                              setIsCustomerDropdownOpen(true);
                            }}
                            onFocus={() => setIsCustomerDropdownOpen(true)}
                            className="w-full pl-8 pr-8 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
                          />
                          {customerSearchText && (
                            <button
                              type="button"
                              onClick={() => {
                                setCustomerSearchText('');
                                setSelectedCustomerId('');
                                setSelectedCustomer(null);
                                setIsCustomerDropdownOpen(false);
                              }}
                              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs"
                            >
                              ✕
                            </button>
                          )}
                        </div>

                        {/* Dropdown Options */}
                        {isCustomerDropdownOpen && (
                          <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-white rounded-xl shadow-lg border border-slate-200 max-h-48 overflow-y-auto py-1 text-xs divide-y divide-slate-50">
                            {filteredCustomers.length === 0 ? (
                              <div className="px-3 py-2.5 text-center text-slate-500 space-y-1">
                                <p className="text-xs">No customer matches "{customerSearchText}"</p>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setNewCustomerName(customerSearchText);
                                    setShowQuickCreateCustomer(true);
                                    setIsCustomerDropdownOpen(false);
                                  }}
                                  className="text-[11px] font-semibold text-brand-600 hover:text-brand-700 underline"
                                >
                                  + Create "{customerSearchText}" as new customer
                                </button>
                              </div>
                            ) : (
                              filteredCustomers.map((c) => (
                                <div
                                  key={c.id}
                                  onClick={() => {
                                    setSelectedCustomerId(c.id);
                                    setSelectedCustomer(c);
                                    setCustomerSearchText(`${c.display_name} (${c.customer_number})`);
                                    setIsCustomerDropdownOpen(false);
                                  }}
                                  className={`px-3 py-2 cursor-pointer hover:bg-slate-50 flex items-center justify-between ${
                                    selectedCustomerId === c.id ? 'bg-brand-50/70 font-semibold text-brand-700' : 'text-slate-800'
                                  }`}
                                >
                                  <div>
                                    <p className="font-semibold text-slate-900">{c.display_name}</p>
                                    <p className="text-[10px] text-slate-400">{c.customer_number} {c.email ? `• ${c.email}` : ''}</p>
                                  </div>
                                  {selectedCustomerId === c.id && (
                                    <CheckCircle2 className="w-3.5 h-3.5 text-brand-600" />
                                  )}
                                </div>
                              ))
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Price Book Layer (Optional Customer Segment List)
                    </label>
                    <select
                      value={selectedPriceBookId}
                      onChange={(e) => setSelectedPriceBookId(e.target.value)}
                      className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
                    >
                      <option value="">Standard Catalog Price (Default)</option>
                      {priceBooks.map((pb) => (
                        <option key={pb.id} value={pb.id}>
                          {pb.name} ({pb.customer_segment || 'General'})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {/* STEP 2: Offering Selection */}
              {wizardStep === 2 && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-bold text-slate-800">Select Offerings to Configure into Deal</p>
                    <span className="text-xs text-slate-500">{dealItems.length} items configured</span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-72 overflow-y-auto pr-1">
                    {offerings.map((o) => {
                      const isSelected = dealItems.some((i) => i.offering_id === o.id);
                      return (
                        <div
                          key={o.id}
                          className={`p-3 rounded-xl border transition-all flex items-center justify-between ${
                            isSelected ? 'bg-brand-50/60 border-brand-300' : 'bg-white border-slate-200 hover:border-slate-300'
                          }`}
                        >
                          <div>
                            <p className="text-xs font-bold text-slate-900">{o.name}</p>
                            <p className="text-[10px] text-slate-400 font-mono">{o.sku} • {o.type}</p>
                            <p className="text-xs font-semibold text-emerald-600 mt-1">{formatMoney(o.base_price, o.currency || 'INR')}</p>
                          </div>
                          {isSelected ? (
                            <button
                              onClick={() => handleRemoveItem(o.id)}
                              className="px-2.5 py-1 rounded text-xs font-semibold bg-red-50 text-red-600 hover:bg-red-100"
                            >
                              Remove
                            </button>
                          ) : (
                            <button
                              onClick={() => handleAddItem(o.id)}
                              className="px-2.5 py-1 rounded text-xs font-semibold bg-brand-50 text-brand-700 hover:bg-brand-100"
                            >
                              + Add
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* STEP 3: Quantity & Line Discounts */}
              {wizardStep === 3 && (
                <div className="space-y-4">
                  <p className="text-xs font-bold text-slate-800">Configure Quantities & Commercial Discounts</p>
                  <div className="space-y-2">
                    {dealItems.map((item, idx) => {
                      const off = offerings.find((o) => o.id === item.offering_id);
                      return (
                        <div key={idx} className="p-3 bg-white rounded-xl border border-slate-200 flex items-center justify-between gap-4">
                          <div className="min-w-[180px]">
                            <p className="text-xs font-bold text-slate-900">{off?.name}</p>
                            <p className="text-[10px] text-slate-400">Base: {formatMoney(off?.base_price, off?.currency || 'INR')} ({off?.pricing_model})</p>
                          </div>

                          <div className="flex items-center gap-2">
                            <span className="text-xs text-slate-500">Qty:</span>
                            <input
                              type="number"
                              min="1"
                              value={item.quantity}
                              onChange={(e) => {
                                const updated = [...dealItems];
                                updated[idx].quantity = Math.max(1, Number(e.target.value));
                                setDealItems(updated);
                              }}
                              className="w-16 px-2 py-1 text-xs border rounded font-semibold text-slate-800"
                            />
                          </div>

                          <div className="flex items-center gap-2">
                            <span className="text-xs text-slate-500">Line Disc %:</span>
                            <input
                              type="number"
                              min="0"
                              max="100"
                              value={item.discount_pct}
                              onChange={(e) => {
                                const updated = [...dealItems];
                                updated[idx].discount_pct = Number(e.target.value);
                                setDealItems(updated);
                              }}
                              className="w-16 px-2 py-1 text-xs border rounded text-slate-800"
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="pt-3 border-t border-slate-200 flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-700">Overall Deal Discount (%):</span>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={dealDiscountPct}
                      onChange={(e) => setDealDiscountPct(Number(e.target.value))}
                      className="w-20 px-2 py-1 text-xs border rounded font-semibold text-slate-800"
                    />
                  </div>
                </div>
              )}

              {/* STEP 4: "Why This Price?" Transparent Waterfall Tree */}
              {wizardStep === 4 && simulation && (
                <div className="space-y-4">
                  {/* Approval Alert if required */}
                  {simulation.approval_required && (
                    <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 flex items-start gap-2.5">
                      <Clock className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                      <div>
                        <p className="font-bold">Deal Requires Finance / Manager Approval</p>
                        <p className="text-[11px] text-amber-700 mt-0.5">
                          {simulation.approval_reasons.join('; ')}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Recommendations */}
                  {simulation.recommendations.length > 0 && (
                    <div className="p-3 bg-purple-50 rounded-xl border border-purple-200 text-xs text-purple-900 space-y-1.5">
                      <p className="font-bold">Rule-Based Add-on Recommendations:</p>
                      {simulation.recommendations.map((rec) => (
                        <div key={rec.offering_id} className="flex items-center justify-between bg-white p-2 rounded-lg border border-purple-100">
                          <div>
                            <span className="font-semibold">{rec.name}</span>: {rec.reason}
                          </div>
                          <span className="font-semibold text-purple-700">{formatMoney(rec.base_price, simulation.currency)}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* "Why This Price?" Line Breakdown */}
                  <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-3">
                    <div
                      className="flex items-center justify-between cursor-pointer"
                      onClick={() => setExpandedExplanation(!expandedExplanation)}
                    >
                      <h4 className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                        <Info className="w-4 h-4 text-brand-600" /> "Why This Price?" Mathematical Breakdown Tree
                      </h4>
                      {expandedExplanation ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                    </div>

                    {expandedExplanation && (
                      <div className="space-y-2.5 pt-2">
                        {simulation.items.map((item) => (
                          <div key={item.offering_id} className="bg-white p-3 rounded-lg border border-slate-200 text-xs space-y-1">
                            <div className="flex items-center justify-between font-bold text-slate-800">
                              <span>{item.offering_name} (× {item.quantity})</span>
                              <span className="text-emerald-700">{formatMoney(item.line_total, simulation.currency)} (incl. tax)</span>
                            </div>
                            <div className="text-[11px] text-slate-500 space-y-0.5">
                              <p>• Base Price: {formatMoney(item.catalog_base_price, simulation.currency)} ({item.pricing_model})</p>
                              {item.price_book_name && (
                                <p className="text-blue-600">• Price Book Layer: {item.price_book_adjusted_unit_price}</p>
                              )}
                              {item.volume_tier_applied && (
                                <p className="text-purple-600">• {item.volume_tier_applied}</p>
                              )}
                              <p>• Effective Unit Price: {formatMoney(item.effective_unit_price, simulation.currency)}</p>
                              {Number(item.discount_amount) > 0 && (
                                <p className="text-red-600">• Line Discount ({item.discount_pct}%): -{formatMoney(item.discount_amount, simulation.currency)}</p>
                              )}
                              <p>• GST {item.tax_rate_pct}%: +{formatMoney(item.tax_amount, simulation.currency)}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Summary Totals */}
                  <div className="bg-white p-4 rounded-xl border border-slate-200 space-y-2 text-xs">
                    <div className="flex justify-between text-slate-600">
                      <span>Subtotal:</span>
                      <span className="font-semibold">{formatMoney(simulation.subtotal, simulation.currency)}</span>
                    </div>
                    {Number(simulation.discount_amount) > 0 && (() => {
                      const subtotalNum = Number(simulation.subtotal) || 0;
                      const discountNum = Number(simulation.discount_amount) || 0;
                      const calculatedPct = subtotalNum > 0 ? (discountNum / subtotalNum) * 100 : (Number(simulation.discount_pct) || 0);
                      const displayPct = Number.isInteger(calculatedPct)
                        ? calculatedPct.toString()
                        : calculatedPct.toFixed(1).replace(/\.0$/, '');
                      return (
                        <div className="flex justify-between text-red-600 font-medium">
                          <span>Total Discounts ({displayPct}%):</span>
                          <span>-{formatMoney(simulation.discount_amount, simulation.currency)}</span>
                        </div>
                      );
                    })()}
                    <div className="flex justify-between text-slate-600">
                      <span>Tax (GST):</span>
                      <span className="font-semibold">+{formatMoney(simulation.tax_amount, simulation.currency)}</span>
                    </div>
                    <div className="flex justify-between text-sm font-bold text-slate-900 pt-2 border-t border-slate-100">
                      <span>Final Net Deal Total:</span>
                      <span className="text-brand-700">{formatMoney(simulation.total, simulation.currency)}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Wizard Footer */}
            <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between">
              {wizardStep > 1 ? (
                <Button variant="outline" size="sm" onClick={() => setWizardStep(wizardStep - 1)}>
                  Back
                </Button>
              ) : <div />}

              {wizardStep < 4 ? (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={async () => {
                    if (wizardStep === 1 && !selectedCustomerId) {
                      showToast('warning', 'Please select a customer.');
                      return;
                    }
                    if (wizardStep === 2 && dealItems.length === 0) {
                      showToast('warning', 'Please select at least one offering.');
                      return;
                    }
                    if (wizardStep === 3) {
                      await triggerSimulation();
                    }
                    setWizardStep(wizardStep + 1);
                  }}
                  className="flex items-center gap-1.5"
                >
                  Continue <ArrowRight className="w-3.5 h-3.5" />
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleCreateDeal}
                  disabled={isSubmitting}
                  className="bg-emerald-600 hover:bg-emerald-700"
                >
                  {isSubmitting ? 'Finalizing Deal...' : 'Save & Configure Deal'}
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Styled Convert to Quote Confirmation Modal */}
      <ConfirmDialog
        isOpen={!!dealToConvert}
        onClose={() => !isConverting && setDealToConvert(null)}
        onConfirm={handleConfirmConvert}
        title="Convert Deal to Quote"
        description="Convert this configured deal into a formal customer Quote? You will be redirected to the generated quote document."
        confirmLabel="Convert to Quote"
        isLoading={isConverting}
      />
    </div>
  );
}

export default CPQPage;
