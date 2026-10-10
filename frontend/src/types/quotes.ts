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

export interface QuoteToSubscriptionInput {
  start_date?: string;
  /** Omit to use the plan's default trial. */
  trial_days?: number;
  auto_renewal?: boolean;
  generate_first_invoice?: boolean;
  notes?: string;
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
  /** Stored id of an existing line of this quote that is being kept; never set on new lines. */
  id?: string;
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

export interface QuoteDecision {
  outcome: 'accepted' | 'declined';
  actor_type: 'customer' | 'staff';
  /** "Accepted by customer" | "Declined by customer" | "Marked accepted by admin" | "Marked declined by admin". */
  title?: string | null;
  /** Who acted, e.g. "Priya Sharma (Acme Corp)" for the customer or the admin's name. */
  actor_display?: string | null;
  /** The name the customer signed with, or the staff member who recorded the override. */
  name?: string | null;
  reason?: string | null;
  at?: string | null;
}

/** Server-side GST treatment for an organization -> customer supply (GET /quotes/supply-preview). */
export interface SupplyPreview {
  supply_type: 'intra_state' | 'inter_state' | 'export';
  /** False when no GST is charged: the organization has no GSTIN, or the supply is an export. */
  charges_gst: boolean;
  place_of_supply_code?: string | null;
  place_of_supply_name?: string | null;
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
  /** Set when the accepted quote was converted into a subscription. */
  converted_subscription_id?: string | null;
  approval_request_id?: string;
  /** Only set on the send response: false when the customer email could not be delivered. */
  email_sent?: boolean | null;
  approved_by?: string;
  approved_at?: string;
  /** Detail responses only: how the accept/decline was recorded (customer link vs admin override). */
  customer_decision?: QuoteDecision | null;
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
