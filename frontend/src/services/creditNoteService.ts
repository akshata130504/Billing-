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
  /** Note: the backend currently returns the number of items in this page. */
  total: number;
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
