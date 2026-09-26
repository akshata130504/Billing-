import { apiClient, cleanParams } from './apiClient';

// Types mirror backend/app/schemas/credits.py. GST / invoice fields are optional
// so the UI keeps working while the backend adds them.

export type CreditNoteStatus = 'draft' | 'issued' | 'partially_applied' | 'applied' | 'void';

export interface CreditNoteCustomerRef {
  id: string;
  customer_number: string;
  display_name: string;
  email?: string | null;
}

export interface CreditNoteLine {
  id: string;
  description: string;
  amount: string;
  quantity?: string | null;
  unit_price?: string | null;
  tax_rate_pct?: string | null;
}

export interface CreditNoteApplication {
  id: string;
  invoice_id: string;
  amount: string;
  applied_at: string;
}

export interface CreditNote {
  id: string;
  credit_note_number: string;
  customer_id: string;
  customer?: CreditNoteCustomerRef | null;
  status: CreditNoteStatus;
  currency: string;
  invoice_id?: string | null;
  subtotal: string;
  tax_amount?: string;
  cgst_amount?: string;
  sgst_amount?: string;
  igst_amount?: string;
  supply_type?: string | null;
  place_of_supply_name?: string | null;
  total: string;
  balance_remaining: string;
  reason?: string | null;
  notes?: string | null;
  reference?: string | null;
  created_at: string;
  lines?: CreditNoteLine[];
  applications?: CreditNoteApplication[];
}

export interface CreditNoteList {
  items: CreditNote[];
  /** Number of credit notes matching the filters (across all pages). */
  total: number;
  limit?: number | null;
  offset?: number | null;
}

export interface CreditNoteCurrencySummary {
  currency: string;
  count: number;
  /** Non-draft, non-void notes. */
  issued_total: string;
  applied_total: string;
  /** Spendable credit still available. */
  remaining_balance: string;
  voided_total: string;
  draft_total: string;
  count_by_status: Record<CreditNoteStatus, number>;
}

export interface CreditNoteSummary {
  total_count: number;
  count_by_status: Record<CreditNoteStatus, number>;
  /** One entry per currency — amounts are never summed across currencies. */
  currencies: CreditNoteCurrencySummary[];
  filters: { customer_id?: string | null; date_from?: string | null; date_to?: string | null };
}

export interface CreditNoteSummaryParams {
  customer_id?: string;
  /** Issue date on or after (YYYY-MM-DD). */
  from?: string;
  /** Issue date on or before (YYYY-MM-DD). */
  to?: string;
}

export interface CreditNoteLineIn {
  description: string;
  /** Pre-tax line amount. */
  amount: number;
  tax_rate_pct?: number;
}

export interface CreditNoteCreateIn {
  customer_id: string;
  invoice_id?: string;
  reason?: string;
  reference?: string;
  currency?: string;
  lines: CreditNoteLineIn[];
}

export interface CreditNoteListParams {
  customer_id?: string;
  status?: CreditNoteStatus;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export const creditNoteService = {
  list: async (params?: CreditNoteListParams): Promise<CreditNoteList> => {
    const { data } = await apiClient.get<CreditNoteList>('/credit-notes', {
      params: cleanParams(params),
    });
    return data;
  },

  summary: async (params?: CreditNoteSummaryParams): Promise<CreditNoteSummary> => {
    const { data } = await apiClient.get<CreditNoteSummary>('/credit-notes/summary', {
      params: cleanParams(params),
    });
    return data;
  },

  get: async (id: string): Promise<CreditNote> => {
    const { data } = await apiClient.get<CreditNote>(`/credit-notes/${id}`);
    return data;
  },

  create: async (body: CreditNoteCreateIn): Promise<CreditNote> => {
    const { data } = await apiClient.post<CreditNote>('/credit-notes', body);
    return data;
  },

  apply: async (id: string, body: { invoice_id: string; amount: number }): Promise<CreditNote> => {
    const { data } = await apiClient.post<CreditNote>(`/credit-notes/${id}/apply`, body);
    return data;
  },

  void: async (id: string, reason?: string): Promise<CreditNote> => {
    const { data } = await apiClient.post<CreditNote>(`/credit-notes/${id}/void`, null, {
      params: cleanParams({ reason }),
    });
    return data;
  },
};
