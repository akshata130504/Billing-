export type QuoteStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'sent'
  | 'viewed'
  | 'accepted'
  | 'declined'
  | 'expired'
  | 'invoiced'
  | 'partially_invoiced'
  | 'converted'
  | 'DRAFT'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'SENT'
  | 'VIEWED'
  | 'ACCEPTED'
  | 'DECLINED'
  | 'EXPIRED'
  | 'INVOICED'
  | 'PARTIALLY_INVOICED'
  | 'CONVERTED';

export interface QuoteCustomerRef {
  id: string;
  customer_number: string;
  display_name: string;
  displayName?: string;
  name?: string;
  email?: string;
  phone?: string;
}

export interface QuoteItemOut {
  id: string;
  offering_id?: string;
  product_id?: string;
  plan_id?: string;
  description: string;
  name?: string;
  quantity: string | number;
  unit_price: string | number;
  rate?: string | number;
  discount_percentage?: string | number;
  discount_amount?: string | number;
  tax_rate_pct?: string | number;
  tax_rate?: string | number;
  tax_amount?: string | number;
  amount: string | number;
  total_amount?: string | number;
  position: number;
  pricing_explanation?: string;
}

export interface QuoteItemIn {
  offering_id?: string;
  product_id?: string;
  plan_id?: string;
  description: string;
  name?: string;
  quantity: number;
  unit_price: number;
  rate?: number;
  discount_percentage?: number;
  tax_rate_pct?: number;
  tax_rate?: number;
  pricing_explanation?: string;
}

export interface Quote {
  id: string;
  quote_number: string;
  customer_id?: string;
  customer: QuoteCustomerRef;
  status: QuoteStatus;
  title?: string;
  subject?: string;
  issue_date: string;
  quote_date?: string;
  expiry_date?: string;
  currency: string;
  subtotal: string | number;
  discount_pct: string | number;
  discount_amount: string | number;
  tax_amount: string | number;
  adjustment?: string | number;
  total: string | number;
  total_amount?: string | number;
  invoiced_amount?: number;
  salesperson?: string;
  reference_number?: string;
  notes?: string;
  customer_notes?: string;
  terms?: string;
  terms_and_conditions?: string;
  items: QuoteItemOut[];
  public_url?: string;
  sent_at?: string;
  accepted_at?: string;
  declined_at?: string;
  converted_invoice_id?: string;
  approval_request_id?: string;
  /** Only set on the send response: false when the customer email could not be delivered. */
  email_sent?: boolean | null;
  approved_by?: string;
  approved_at?: string;
  rejection_reason?: string;
  created_by?: {
    id: string;
    full_name: string;
    email: string;
  };
  created_at: string;
  updated_at: string;
}

export interface QuoteCreateInput {
  customer_id: string;
  title?: string;
  issue_date?: string;
  expiry_date?: string;
  currency?: string;
  discount_pct?: number;
  notes?: string;
  terms?: string;
  items: QuoteItemIn[];
}

export interface QuoteUpdateInput {
  customer_id?: string;
  title?: string;
  issue_date?: string;
  expiry_date?: string;
  currency?: string;
  discount_pct?: number;
  notes?: string;
  terms?: string;
  items?: QuoteItemIn[];
}

export interface QuoteConvertInput {
  issue_date?: string;
  due_date?: string;
}
