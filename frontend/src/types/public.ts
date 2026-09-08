/**
 * Hosted public pages (/pay/:token, /quote/:token).
 *
 * The backend (backend/app/schemas/public.py, schemas/quotes.py) returns a few
 * more fields than the shared `PublicInvoice` / `PublicQuote` contracts in
 * ./api.ts declare. These types widen them without touching the shared file;
 * `publicService` results are asserted to these (a safe narrowing — every
 * field here is a superset of the shared type).
 */
import type { PublicCustomer, PublicInvoice, PublicOrganization, PublicQuote } from './api';

export interface PublicOrganizationFull extends PublicOrganization {
  website: string | null;
  pan: string | null;
}

export interface PublicCustomerFull extends PublicCustomer {
  phone: string | null;
  gstin: string | null;
}

export interface PublicInvoiceFull extends Omit<PublicInvoice, 'organization' | 'customer'> {
  discount_pct: string;
  period_start: string | null;
  period_end: string | null;
  days_overdue: number;
  /** Relative API path — prefer `publicService.invoicePdfUrl(token)`. */
  pdf_url: string;
  organization: PublicOrganizationFull;
  customer: PublicCustomerFull;
}

export interface PublicQuoteOrganization {
  name: string;
  legal_name: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  gstin: string | null;
  logo_url: string | null;
}

export interface PublicQuoteCustomer {
  display_name: string;
  company_name: string | null;
  email: string | null;
  billing_address_line1: string | null;
  billing_address_line2: string | null;
  billing_city: string | null;
  billing_state: string | null;
  billing_postal_code: string | null;
  billing_country: string | null;
}

export interface PublicQuoteFull extends Omit<PublicQuote, 'organization' | 'customer'> {
  sent_at: string | null;
  organization: PublicQuoteOrganization;
  customer: PublicQuoteCustomer;
}
