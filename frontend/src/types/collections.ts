import type { CustomerRef, InvoiceStatus, PageParams, UserRef } from './api';

export type CollectionStatus =
  | 'current'
  | 'due_soon'
  | 'overdue'
  | 'in_follow_up'
  | 'promise_to_pay'
  | 'disputed'
  | 'escalated'
  | 'collected'
  | 'written_off';

export type AgingBucket = 'current' | '1_30' | '31_60' | '61_90' | '90_plus';

export type CollectionActivityType =
  | 'email_sent'
  | 'phone_call'
  | 'reminder'
  | 'payment_promise'
  | 'customer_contacted'
  | 'dispute_raised'
  | 'dispute_resolved'
  | 'internal_note';

export type PromiseToPayStatus = 'pending' | 'kept' | 'broken' | 'cancelled';

export interface CollectionsKPIs {
  total_outstanding: string;
  overdue_amount: string;
  current_due: string;
  due_in_7_days: string;
  due_in_30_days: string;
  collection_rate: string | null;
  overdue_invoice_count: number;
}

export interface AgingBucketOut {
  bucket: AgingBucket;
  count: number;
  amount: string;
}

export interface CollectionPipelineEntry {
  status: CollectionStatus;
  count: number;
  amount: string;
}

export interface CollectionActivityOut {
  id: string;
  invoice_id: string;
  activity_type: CollectionActivityType;
  note: string | null;
  activity_at: string;
  next_follow_up_at: string | null;
  created_by: UserRef | null;
  created_at: string;
}

export interface TopOverdueCustomer {
  customer: CustomerRef;
  outstanding_amount: string;
  overdue_amount: string;
  invoice_count: number;
}

export interface UpcomingDueInvoice {
  id: string;
  invoice_number: string;
  customer: CustomerRef;
  due_date: string;
  amount_due: string;
}

export interface CollectionsDashboardOut {
  kpis: CollectionsKPIs;
  aging_summary: AgingBucketOut[];
  pipeline: CollectionPipelineEntry[];
  recent_activities: CollectionActivityOut[];
  top_overdue_customers: TopOverdueCustomer[];
  upcoming_due_invoices: UpcomingDueInvoice[];
}

export interface CollectionInvoiceOut {
  id: string;
  invoice_number: string;
  customer: CustomerRef;
  invoice_status: InvoiceStatus;
  issue_date: string;
  due_date: string;
  total: string;
  amount_paid: string;
  amount_due: string;
  days_overdue: number;
  aging_bucket: AgingBucket;
  collection_status: CollectionStatus;
  last_contact_at: string | null;
  next_follow_up_at: string | null;
}

export interface PromiseToPayOut {
  id: string;
  invoice_id: string;
  promised_amount: string;
  promised_date: string;
  note: string | null;
  status: PromiseToPayStatus;
  created_by: UserRef | null;
  created_at: string;
  updated_at: string;
}

export interface CollectionInvoiceDetailOut extends CollectionInvoiceOut {
  activities: CollectionActivityOut[];
  promises: PromiseToPayOut[];
}

export interface CollectionInvoiceListParams extends PageParams {
  search?: string;
  status?: CollectionStatus;
  aging_bucket?: AgingBucket;
  customer_id?: string;
  date_from?: string;
  date_to?: string;
  amount_min?: string | number;
  amount_max?: string | number;
}

export interface CollectionActivityIn {
  activity_type: CollectionActivityType;
  note?: string;
  activity_at?: string;
  next_follow_up_at?: string;
}

export interface PromiseToPayIn {
  promised_amount: string;
  promised_date: string;
  note?: string;
}

export interface PromiseToPayUpdate {
  status: Exclude<PromiseToPayStatus, 'pending'>;
}

export interface CollectionStatusUpdate {
  status: Exclude<CollectionStatus, 'collected'>;
  note?: string;
}
