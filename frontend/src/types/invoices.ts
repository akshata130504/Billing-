export type InvoiceStatus =
  | 'draft'
  | 'sent'
  | 'partially_paid'
  | 'paid'
  | 'overdue'
  | 'void'
  | 'DRAFT'
  | 'SENT'
  | 'PARTIALLY_PAID'
  | 'PAID'
  | 'OVERDUE'
  | 'VOID';

export interface InvoiceKPIs {
  total_invoices: number;
  draft_count: number;
  sent_count: number;
  partially_paid_count: number;
  paid_count: number;
  overdue_count: number;
  total_outstanding: number;
  total_revenue: number;
  void_count?: number;
}

export interface InvoiceCustomerRef {
  id: string;
  customer_number: string;
  display_name: string;
  displayName?: string;
  name?: string;
  email?: string;
  phone?: string;
}

export interface InvoiceLineItemOut {
  id: string;
  offering_id?: string;
  plan_id?: string;
  name?: string;
  description: string;
  quantity: number | string;
  rate?: number | string;
  unit_price: number | string;
  discount_percentage?: number | string;
  discount_amount?: number | string;
  tax_rate_pct: number | string;
  tax_rate?: number | string;
  tax_amount?: number | string;
  cgst_amount?: number | string;
  sgst_amount?: number | string;
  igst_amount?: number | string;
  cgst_rate_pct?: number | string;
  sgst_rate_pct?: number | string;
  igst_rate_pct?: number | string;
  hsn_sac_code?: string | null;
  amount: number | string;
  total_amount?: number | string;
  position: number;
  pricing_explanation?: string;
}

export interface InvoiceLineItemIn {
  /** Stored id of an existing line of this invoice that is being kept; never set on new lines. */
  id?: string;
  offering_id?: string;
  plan_id?: string;
  name: string;
  description?: string;
  quantity: number;
  rate: number;
  discount_percentage?: number;
  tax_rate?: number;
  pricing_model?: string;
  pricing_explanation?: string;
}

export interface PaymentRecordIn {
  amount: number;
  payment_date: string;
  payment_method: string;
  reference_number?: string;
  notes?: string;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  customer_id: string;
  customer: InvoiceCustomerRef;
  status: InvoiceStatus;
  issue_date: string;
  invoice_date?: string;
  due_date: string;
  currency: string;
  payment_terms?: string;
  reference?: string;
  salesperson?: string;
  subtotal: number | string;
  discount_pct: number | string;
  discount_amount: number | string;
  tax_amount: number | string;
  /** GST heads; cgst+sgst+igst reconcile to tax_amount. */
  cgst_amount?: number | string;
  sgst_amount?: number | string;
  igst_amount?: number | string;
  supply_type?: string | null;
  place_of_supply_code?: string | null;
  place_of_supply_name?: string | null;
  customer_gstin?: string | null;
  supplier_gstin?: string | null;
  adjustment?: number | string;
  total: number | string;
  total_amount?: number | string;
  amount_paid: number | string;
  paid_amount?: number | string;
  amount_due: number | string;
  balance_due?: number | string;
  notes?: string;
  customer_notes?: string;
  terms?: string;
  terms_and_conditions?: string;
  items: InvoiceLineItemOut[];
  payments?: any[];
  public_url?: string;
  public_token?: string;
  pdf_url?: string;
  /** Only set right after /send or /send-reminder; absent on a plain fetch. */
  email_delivery_failed?: boolean | null;
  created_at: string;
  updated_at: string;
}

export interface InvoiceListResponse {
  items: Invoice[];
  total: number;
  page: number;
  page_size: number;
  kpis?: InvoiceKPIs;
}

export interface InvoiceFormState {
  customer_id: string;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  payment_terms: string;
  reference?: string;
  salesperson?: string;
  customer_notes?: string;
  terms_and_conditions?: string;
  adjustment?: number;
  items: InvoiceLineItemIn[];
}
