/**
 * Customers module types that are not part of the shared API contract file.
 * Mirrors backend/app/schemas/payment_methods.py.
 */
import type { PaymentGateway } from './api';

export type CustomerPaymentMethodStatus = 'active' | 'expired' | 'revoked';

export interface CustomerPaymentMethodOut {
  id: string;
  customer_id: string;
  gateway: PaymentGateway;
  gateway_customer_id: string | null;
  type: string;
  card_brand: string | null;
  last4: string | null;
  exp_month: number | null;
  exp_year: number | null;
  is_default: boolean;
  is_autocharge_eligible: boolean;
  status: CustomerPaymentMethodStatus;
  created_at: string;
}

export interface CustomerPaymentMethodCreateIn {
  gateway?: PaymentGateway;
  gateway_token: string;
  gateway_customer_id?: string | null;
  type?: string;
  card_brand?: string | null;
  last4?: string | null;
  exp_month?: number | null;
  exp_year?: number | null;
  is_default?: boolean;
  is_autocharge_eligible?: boolean;
}

/** Sort keys accepted by GET /customers (see customer_service.CUSTOMER_SORT_FIELDS). */
export type CustomerSortKey =
  | '-created_at'
  | 'created_at'
  | 'display_name'
  | '-display_name'
  | 'customer_number'
  | '-customer_number'
  | '-updated_at';

export type CustomerDetailTab =
  | 'overview'
  | 'contacts'
  | 'invoices'
  | 'payments'
  | 'subscriptions'
  | 'payment-methods';
