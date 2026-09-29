/**
 * TypeScript interface definitions for Product Catalog and CPQ.
 */

export type OfferingType = 'product' | 'service' | 'plan' | 'bundle';
export type OfferingPricingModel = 'flat' | 'per_unit' | 'volume' | 'tiered' | 'package';
export type PriceBookStatus = 'active' | 'draft' | 'archived';
export type CPQDealStatus = 'draft' | 'configured' | 'pending_approval' | 'approved' | 'rejected' | 'converted';
export type CPQRuleType = 'requires' | 'excludes' | 'recommends' | 'tier_discount';

export interface PricingTier {
  min_qty: number;
  max_qty?: number | null;
  unit_price: number;
}

export interface BundleComponent {
  id?: string;
  component_offering_id: string;
  component_name?: string;
  component_sku?: string;
  component_base_price?: string;
  is_required: boolean;
  default_quantity: string | number;
  min_quantity: string | number;
  max_quantity?: string | number | null;
  discount_pct: string | number;
}

export interface OfferingOut {
  id: string;
  name: string;
  sku: string;
  description: string | null;
  type: OfferingType;
  category: string | null;
  unit: string;
  currency: string;
  pricing_model: OfferingPricingModel;
  base_price: string;
  tax_rate_pct: string;
  hsn_sac_code: string | null;
  billing_frequency: string;
  is_active: boolean;
  pricing_tiers?: PricingTier[] | null;
  bundle_components: BundleComponent[];
  created_at: string;
  updated_at: string;
}

export interface OfferingIn {
  name: string;
  sku?: string;
  description?: string;
  type: OfferingType;
  category?: string;
  unit?: string;
  currency?: string;
  pricing_model: OfferingPricingModel;
  base_price: number | string;
  tax_rate_pct?: number | string;
  hsn_sac_code?: string;
  billing_frequency?: string;
  is_active?: boolean;
  pricing_tiers?: PricingTier[];
  bundle_components?: Array<{
    component_offering_id: string;
    is_required?: boolean;
    default_quantity?: number;
    min_quantity?: number;
    max_quantity?: number | null;
    discount_pct?: number;
  }>;
}

export interface PriceBookEntryOut {
  id: string;
  offering_id: string;
  offering_name: string;
  offering_sku: string;
  catalog_base_price: string;
  custom_price: string | null;
  discount_pct: string | null;
  is_active: boolean;
}

export interface PriceBookOut {
  id: string;
  name: string;
  description: string | null;
  currency: string;
  customer_segment: string | null;
  is_default: boolean;
  status: PriceBookStatus;
  effective_from: string | null;
  effective_until: string | null;
  entries_count: number;
  entries: PriceBookEntryOut[];
  created_at: string;
  updated_at: string;
}

export interface PriceBookIn {
  name: string;
  description?: string;
  currency?: string;
  customer_segment?: string;
  is_default?: boolean;
  status?: PriceBookStatus;
  effective_from?: string | null;
  effective_until?: string | null;
  entries?: Array<{
    offering_id: string;
    custom_price?: number | null;
    discount_pct?: number | null;
    is_active?: boolean;
  }>;
}

export interface CPQRuleOut {
  id: string;
  name: string;
  description: string | null;
  rule_type: CPQRuleType;
  is_active: boolean;
  priority: number;
  conditions: Record<string, any>;
  actions: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface PriceSimulationRequest {
  customer_id?: string;
  price_book_id?: string;
  items: Array<{
    offering_id: string;
    quantity: number | string;
    custom_discount_pct?: number | string;
  }>;
  deal_discount_pct?: number | string;
}

export interface PriceLineBreakdown {
  offering_id: string;
  offering_name: string;
  sku: string;
  quantity: string;
  pricing_model: string;
  catalog_base_price: string;
  price_book_name: string | null;
  price_book_adjusted_unit_price: string;
  volume_tier_applied: string | null;
  effective_unit_price: string;
  line_subtotal: string;
  discount_pct: string;
  discount_amount: string;
  line_net_amount: string;
  tax_rate_pct: string;
  tax_amount: string;
  line_total: string;
  rule_messages: string[];
}

export interface PriceSimulationResponse {
  currency: string;
  price_book_applied: string | null;
  items: PriceLineBreakdown[];
  subtotal: string;
  discount_pct: string;
  discount_amount: string;
  tax_amount: string;
  total: string;
  approval_required: boolean;
  approval_reasons: string[];
  recommendations: Array<{
    offering_id: string;
    name: string;
    sku: string;
    base_price: string;
    reason: string;
  }>;
  rule_warnings: string[];
}

export interface CPQDealItemOut {
  id: string;
  offering_id: string;
  offering_name: string;
  offering_sku: string;
  description: string;
  quantity: string;
  catalog_base_price: string;
  unit_price: string;
  discount_pct: string;
  discount_amount: string;
  tax_rate_pct: string;
  tax_amount: string;
  total_amount: string;
  is_bundle_parent: boolean;
  parent_item_id: string | null;
  item_explanation?: Record<string, any> | null;
  position: number;
}

export interface CPQDealOut {
  id: string;
  deal_number: string;
  title: string;
  customer_id: string;
  customer_name: string;
  customer_number: string;
  price_book_id: string | null;
  price_book_name: string | null;
  status: CPQDealStatus;
  currency: string;
  subtotal: string;
  discount_pct: string;
  discount_amount: string;
  tax_amount: string;
  total: string;
  pricing_explanation?: PriceSimulationResponse | null;
  approval_required: boolean;
  approval_reason: string | null;
  approval_status: string | null;
  approved_by: string | null;
  approved_at: string | null;
  converted_quote_id: string | null;
  created_by_id?: string | null;
  notes: string | null;
  terms: string | null;
  items: CPQDealItemOut[];
  created_at: string;
  updated_at: string;
}

export interface CPQDealIn {
  title: string;
  customer_id: string;
  price_book_id?: string;
  currency?: string;
  discount_pct?: number;
  notes?: string;
  terms?: string;
  items: Array<{
    offering_id: string;
    quantity: number;
    discount_pct?: number;
    description?: string;
  }>;
}
