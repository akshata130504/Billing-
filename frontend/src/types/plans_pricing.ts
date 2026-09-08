export type PlanPricingModel = 'flat' | 'per_unit' | 'volume' | 'tiered' | 'package';
export type PlanBillingFrequency = 'one_time' | 'monthly' | 'quarterly' | 'semiannual' | 'yearly';
export type PlanStatus = 'active' | 'draft' | 'archived';

export interface PlanPricingTier {
  min_qty?: number;
  max_qty?: number;
  unit_price?: number;
  package_qty?: number;
  package_price?: number;
}

export interface PlanPricingItem {
  id: string;
  name: string;
  code: string;
  sku: string;
  description?: string;
  product_id?: string;
  product_name?: string;
  category?: string;
  unit: string;
  currency: string;
  pricing_model: PlanPricingModel;
  base_price: number | string;
  tax_rate_pct: number | string;
  billing_frequency: PlanBillingFrequency;
  status: PlanStatus;
  is_active: boolean;
  pricing_tiers?: PlanPricingTier[];
  created_at: string;
  updated_at: string;
}

export interface CreatePlanPricingInput {
  name: string;
  code?: string;
  sku?: string;
  description?: string;
  product_id?: string;
  category?: string;
  unit?: string;
  currency?: string;
  pricing_model: PlanPricingModel;
  base_price: number;
  tax_rate_pct?: number;
  billing_frequency: PlanBillingFrequency;
  is_active?: boolean;
  status?: PlanStatus;
  pricing_tiers?: PlanPricingTier[];
}

export interface PricingSimulationRequest {
  offering_id?: string;
  plan_id?: string;
  customer_id?: string;
  price_book_id?: string;
  quantity: number;
  discount_pct?: number;
}

export interface PricingSimulationResponse {
  offering_id: string;
  offering_name: string;
  offering_sku: string;
  pricing_model: string;
  quantity: string;
  effective_unit_price: string;
  subtotal: string;
  discount_pct: string;
  discount_amount: string;
  net_amount: string;
  tax_rate_pct: string;
  tax_amount: string;
  total_amount: string;
  explanation: {
    catalog_base_price: string;
    price_book_adjustment?: string | null;
    pricing_model: string;
    effective_unit_price: string;
    tier_explanation?: string;
    quantity: string;
    subtotal_pre_discount: string;
    discount_pct: string;
    discount_amount: string;
    net_line_amount: string;
    tax_rate_pct: string;
    tax_amount: string;
    total_line_amount: string;
  };
}
