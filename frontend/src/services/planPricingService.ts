import { apiClient } from './apiClient';
import type {
  PlanPricingItem,
  CreatePlanPricingInput,
  PricingSimulationRequest,
  PricingSimulationResponse,
} from '../types/plans_pricing';

export const planPricingService = {
  async listPlans(params?: {
    search?: string;
    status?: string;
    is_active?: boolean;
    page?: number;
    page_size?: number;
  }): Promise<{ items: PlanPricingItem[]; total: number }> {
    // Check offerings API for plans
    const q = new URLSearchParams();
    q.set('type', 'plan');
    if (params?.search) q.set('search', params.search);
    if (params?.is_active !== undefined) q.set('is_active', String(params.is_active));
    if (params?.page) q.set('page', String(params.page));
    if (params?.page_size) q.set('page_size', String(params.page_size));

    try {
      const res = await apiClient.get<{ items: any[]; total: number }>(`/catalog/offerings?${q.toString()}`);
      const items: PlanPricingItem[] = (res.data.items || []).map((o) => ({
        id: o.id,
        name: o.name,
        code: o.sku || o.name.toLowerCase().replace(/\s+/g, '-'),
        sku: o.sku,
        description: o.description,
        category: o.category || 'Subscriptions',
        unit: o.unit || 'subscription',
        currency: o.currency || 'INR',
        pricing_model: o.pricing_model || 'per_unit',
        base_price: o.base_price || 0,
        tax_rate_pct: o.tax_rate_pct || 18,
        billing_frequency: o.billing_frequency || 'monthly',
        status: o.is_active ? 'active' : 'archived',
        is_active: Boolean(o.is_active),
        pricing_tiers: o.pricing_tiers || [],
        created_at: o.created_at,
        updated_at: o.updated_at,
      }));
      return { items, total: res.data.total || items.length };
    } catch {
      return { items: [], total: 0 };
    }
  },

  async getPlans(params?: any) {
    return this.listPlans(params);
  },

  async getPlan(id: string): Promise<PlanPricingItem> {
    const res = await apiClient.get<any>(`/catalog/offerings/${id}`);
    const o = res.data;
    return {
      id: o.id,
      name: o.name,
      code: o.sku,
      sku: o.sku,
      description: o.description,
      category: o.category || 'Subscriptions',
      unit: o.unit || 'subscription',
      currency: o.currency || 'INR',
      pricing_model: o.pricing_model || 'per_unit',
      base_price: o.base_price || 0,
      tax_rate_pct: o.tax_rate_pct || 18,
      billing_frequency: o.billing_frequency || 'monthly',
      status: o.is_active ? 'active' : 'archived',
      is_active: Boolean(o.is_active),
      pricing_tiers: o.pricing_tiers || [],
      created_at: o.created_at,
      updated_at: o.updated_at,
    };
  },

  async createPlan(data: CreatePlanPricingInput): Promise<PlanPricingItem> {
    const payload = {
      name: data.name,
      sku: data.code || data.sku,
      type: 'plan',
      category: data.category || 'Subscriptions',
      unit: data.unit || 'subscription',
      currency: data.currency || 'INR',
      pricing_model: data.pricing_model,
      base_price: data.base_price,
      tax_rate_pct: data.tax_rate_pct ?? 18,
      billing_frequency: data.billing_frequency,
      is_active: data.is_active ?? (data.status !== 'archived'),
      pricing_tiers: data.pricing_tiers,
      description: data.description,
    };
    const res = await apiClient.post<any>('/catalog/offerings', payload);
    const o = res.data;
    return {
      id: o.id,
      name: o.name,
      code: o.sku,
      sku: o.sku,
      description: o.description,
      category: o.category,
      unit: o.unit,
      currency: o.currency,
      pricing_model: o.pricing_model,
      base_price: o.base_price,
      tax_rate_pct: o.tax_rate_pct,
      billing_frequency: o.billing_frequency,
      status: o.is_active ? 'active' : 'archived',
      is_active: Boolean(o.is_active),
      pricing_tiers: o.pricing_tiers || [],
      created_at: o.created_at,
      updated_at: o.updated_at,
    };
  },

  async updatePlan(id: string, data: Partial<CreatePlanPricingInput>): Promise<PlanPricingItem> {
    const payload: any = {};
    if (data.name !== undefined) payload.name = data.name;
    if (data.description !== undefined) payload.description = data.description;
    if (data.category !== undefined) payload.category = data.category;
    if (data.unit !== undefined) payload.unit = data.unit;
    if (data.currency !== undefined) payload.currency = data.currency;
    if (data.pricing_model !== undefined) payload.pricing_model = data.pricing_model;
    if (data.base_price !== undefined) payload.base_price = data.base_price;
    if (data.tax_rate_pct !== undefined) payload.tax_rate_pct = data.tax_rate_pct;
    if (data.billing_frequency !== undefined) payload.billing_frequency = data.billing_frequency;
    if (data.is_active !== undefined) payload.is_active = data.is_active;
    if (data.status !== undefined) payload.is_active = data.status === 'active';
    if (data.pricing_tiers !== undefined) payload.pricing_tiers = data.pricing_tiers;

    const res = await apiClient.patch<any>(`/catalog/offerings/${id}`, payload);
    const o = res.data;
    return {
      id: o.id,
      name: o.name,
      code: o.sku,
      sku: o.sku,
      description: o.description,
      category: o.category,
      unit: o.unit,
      currency: o.currency,
      pricing_model: o.pricing_model,
      base_price: o.base_price,
      tax_rate_pct: o.tax_rate_pct,
      billing_frequency: o.billing_frequency,
      status: o.is_active ? 'active' : 'archived',
      is_active: Boolean(o.is_active),
      pricing_tiers: o.pricing_tiers || [],
      created_at: o.created_at,
      updated_at: o.updated_at,
    };
  },

  async clonePlan(id: string): Promise<PlanPricingItem> {
    const original = await this.getPlan(id);
    const suffix = Math.random().toString(36).substring(2, 6).toUpperCase();
    return this.createPlan({
      name: `${original.name} (Copy)`,
      code: `${original.code}-COPY-${suffix}`,
      description: original.description,
      category: original.category,
      unit: original.unit,
      currency: original.currency,
      pricing_model: original.pricing_model,
      base_price: Number(original.base_price),
      tax_rate_pct: Number(original.tax_rate_pct),
      billing_frequency: original.billing_frequency,
      status: 'draft',
      is_active: true,
      pricing_tiers: original.pricing_tiers,
    });
  },

  async deletePlan(id: string): Promise<void> {
    await apiClient.delete(`/catalog/offerings/${id}`);
  },

  async simulatePricing(req: PricingSimulationRequest): Promise<PricingSimulationResponse> {
    const res = await apiClient.post<PricingSimulationResponse>('/pricing/simulate', req);
    return res.data;
  },

  async calculatePricing(
    items: Array<{
      offering_id?: string;
      quantity: number;
      price_book_id?: string;
      discount_pct?: number;
    }>,
    customer_id?: string,
    price_book_id?: string,
    deal_discount_pct?: number
  ): Promise<any> {
    const res = await apiClient.post<any>('/pricing/calculate', {
      items,
      customer_id,
      price_book_id,
      deal_discount_pct,
    });
    return res.data;
  },

  async calculatePrice(req: { plan_id?: string; offering_id?: string; quantity: number }): Promise<{
    unit_rate: number;
    pricing_model: string;
    pricing_explanation: string;
    subtotal: number;
    total_amount: number;
  }> {
    const item = {
      offering_id: req.offering_id || req.plan_id,
      quantity: req.quantity,
    };
    const res = await apiClient.post<any>('/pricing/calculate', { items: [item] });
    const line = res.data?.lines && res.data.lines[0];
    return {
      unit_rate: line ? Number(line.unit_price || 0) : 0,
      pricing_model: line ? line.pricing_model : 'FLAT',
      pricing_explanation: line ? line.pricing_explanation : '',
      subtotal: line ? Number(line.subtotal || 0) : 0,
      total_amount: line ? Number(line.total || 0) : 0,
    };
  },
};
