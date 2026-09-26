import { apiClient, cleanParams } from './apiClient';
import type {
  InvoiceOut,
  PageParams,
  Paginated,
  SubscriptionCancelRequest,
  SubscriptionIn,
  SubscriptionListParams,
  SubscriptionOut,
  SubscriptionSummaryOut,
  SubscriptionUpdate,
} from '../types/api';

/** POST /subscriptions/{id}/cancel body, incl. the optional prorated-credit flag. */
export type SubscriptionCancelBody = SubscriptionCancelRequest & {
  /** Immediate cancellation only: credit the unused, already-invoiced part of the period. */
  prorate_credit?: boolean;
};

export interface TrialConvertBody {
  payment_method_id?: string | null;
  generate_first_invoice?: boolean;
}

export interface TrialConversionResult {
  subscription_id: string;
  status: string;
  converted_at: string;
  invoice_id: string | null;
  payment_attempt_id: string | null;
  payment_succeeded: boolean;
  message: string;
}

export interface TrialExtendBody {
  days?: number;
  new_expiration_date?: string;
  reason?: string;
  admin_override?: boolean;
}

export interface TrialPeriodSummary {
  id: string;
  subscription_id: string;
  trial_start_date: string;
  trial_end_date: string;
  extension_count: number;
  max_extensions_allowed: number;
  status: string;
  fallback_plan_id?: string | null;
}

export const subscriptionService = {
  summary: async (): Promise<SubscriptionSummaryOut> => {
    const { data } = await apiClient.get<SubscriptionSummaryOut>('/subscriptions/summary');
    return data;
  },

  list: async (params?: SubscriptionListParams): Promise<Paginated<SubscriptionOut>> => {
    const { data } = await apiClient.get<Paginated<SubscriptionOut>>('/subscriptions', {
      params: cleanParams(params),
    });
    return data;
  },

  get: async (id: string): Promise<SubscriptionOut> => {
    const { data } = await apiClient.get<SubscriptionOut>(`/subscriptions/${id}`);
    return data;
  },

  create: async (body: SubscriptionIn): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>('/subscriptions', body);
    return data;
  },

  update: async (id: string, body: SubscriptionUpdate): Promise<SubscriptionOut> => {
    const { data } = await apiClient.patch<SubscriptionOut>(`/subscriptions/${id}`, body);
    return data;
  },

  activate: async (id: string): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>(`/subscriptions/${id}/activate`);
    return data;
  },

  pause: async (id: string): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>(`/subscriptions/${id}/pause`);
    return data;
  },

  resume: async (id: string): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>(`/subscriptions/${id}/resume`);
    return data;
  },

  renew: async (id: string): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>(`/subscriptions/${id}/renew`);
    return data;
  },

  cancel: async (id: string, body: SubscriptionCancelBody): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>(`/subscriptions/${id}/cancel`, body);
    return data;
  },

  generateInvoice: async (id: string): Promise<InvoiceOut> => {
    const { data } = await apiClient.post<InvoiceOut>(`/subscriptions/${id}/generate-invoice`);
    return data;
  },

  invoices: async (id: string, params?: PageParams): Promise<Paginated<InvoiceOut>> => {
    const { data } = await apiClient.get<Paginated<InvoiceOut>>(
      `/subscriptions/${id}/invoices`,
      { params: cleanParams(params) }
    );
    return data;
  },

  /** Convert a trial through the trial service (charges the card on file when given). */
  convertTrial: async (id: string, body: TrialConvertBody = {}): Promise<TrialConversionResult> => {
    const { data } = await apiClient.post<TrialConversionResult>(`/trials/${id}/convert`, {
      generate_first_invoice: true,
      ...body,
    });
    return data;
  },

  extendTrial: async (id: string, body: TrialExtendBody): Promise<TrialPeriodSummary> => {
    const { data } = await apiClient.post<TrialPeriodSummary>(`/trials/${id}/extend`, body);
    return data;
  },

  /** Move a trial to a free / fallback plan (same organization and currency). */
  moveTrialToFallback: async (id: string, fallbackPlanId?: string | null): Promise<SubscriptionOut> => {
    const { data } = await apiClient.post<SubscriptionOut>(`/trials/${id}/fallback`, {
      fallback_plan_id: fallbackPlanId || null,
    });
    return data;
  },
};
