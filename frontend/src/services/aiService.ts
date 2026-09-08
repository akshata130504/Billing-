import { apiClient, cleanParams } from './apiClient';
import type {
  AIDraftConfirmResponse,
  AIDraftRequest,
  AIDraftResponse,
  AIHistoryItem,
  AIHistoryParams,
  AIQueryRequest,
  AIQueryResponse,
  AIWritingRequest,
  AIWritingResponse,
} from '../types/ai';

/**
 * AI in Billing. The backend is a deterministic, source-grounded assistant
 * (keyword intent classifier over live tenant data + template writing) — it does
 * not call an external model provider, and drafts never mutate the ledger until
 * explicitly confirmed.
 */
export const aiService = {
  /** POST /ai/queries — read-only natural-language question over billing data. */
  ask: async (body: AIQueryRequest): Promise<AIQueryResponse> => {
    const { data } = await apiClient.post<AIQueryResponse>('/ai/queries', body);
    return data;
  },

  /** POST /ai/drafts — propose a structured action; validated but not executed. Finance+ only. */
  proposeDraft: async (body: AIDraftRequest): Promise<AIDraftResponse> => {
    const { data } = await apiClient.post<AIDraftResponse>('/ai/drafts', body);
    return data;
  },

  /** POST /ai/drafts/{id}/confirm — re-validates and executes via the owning domain service. */
  confirmDraft: async (draftId: string): Promise<AIDraftConfirmResponse> => {
    const { data } = await apiClient.post<AIDraftConfirmResponse>(`/ai/drafts/${draftId}/confirm`);
    return data;
  },

  /** POST /ai/writing — generates editable email/note text. */
  generateWriting: async (body: AIWritingRequest): Promise<AIWritingResponse> => {
    const { data } = await apiClient.post<AIWritingResponse>('/ai/writing', body);
    return data;
  },

  /** GET /ai/history — tenant-scoped AI activity log (newest first). */
  history: async (params?: AIHistoryParams): Promise<AIHistoryItem[]> => {
    const { data } = await apiClient.get<AIHistoryItem[]>('/ai/history', {
      params: cleanParams(params),
    });
    return data;
  },
};
