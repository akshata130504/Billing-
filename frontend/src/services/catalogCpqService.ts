import { apiClient, cleanParams } from './apiClient';
import type { Paginated } from '../types/api';
import type {
  CPQDealIn,
  CPQDealOut,
  CPQRuleOut,
  OfferingIn,
  OfferingOut,
  PriceBookIn,
  PriceBookOut,
  PriceSimulationRequest,
  PriceSimulationResponse,
} from '../types/catalog_cpq';
import type { QuoteOut } from '../types/api';

export const catalogCpqService = {
  // --- Offerings ---
  listOfferings: async (params?: {
    search?: string;
    is_active?: boolean;
    type?: string;
    category?: string;
    page?: number;
    page_size?: number;
  }): Promise<Paginated<OfferingOut>> => {
    const { data } = await apiClient.get<Paginated<OfferingOut>>('/catalog/offerings', {
      params: cleanParams(params),
    });
    return data;
  },

  getOffering: async (id: string): Promise<OfferingOut> => {
    const { data } = await apiClient.get<OfferingOut>(`/catalog/offerings/${id}`);
    return data;
  },

  createOffering: async (body: OfferingIn): Promise<OfferingOut> => {
    const { data } = await apiClient.post<OfferingOut>('/catalog/offerings', body);
    return data;
  },

  updateOffering: async (id: string, body: Partial<OfferingIn>): Promise<OfferingOut> => {
    const { data } = await apiClient.patch<OfferingOut>(`/catalog/offerings/${id}`, body);
    return data;
  },

  archiveOffering: async (id: string): Promise<void> => {
    await apiClient.delete(`/catalog/offerings/${id}`);
  },

  /** Reverse an archive (admin); idempotent. */
  unarchiveOffering: async (id: string): Promise<OfferingOut> => {
    const { data } = await apiClient.post<OfferingOut>(`/catalog/offerings/${id}/unarchive`);
    return data;
  },

  // --- Price Books ---
  listPriceBooks: async (params?: {
    search?: string;
    status?: string;
    page?: number;
    page_size?: number;
  }): Promise<Paginated<PriceBookOut>> => {
    const { data } = await apiClient.get<Paginated<PriceBookOut>>('/catalog/price-books', {
      params: cleanParams(params),
    });
    return data;
  },

  getPriceBook: async (id: string): Promise<PriceBookOut> => {
    const { data } = await apiClient.get<PriceBookOut>(`/catalog/price-books/${id}`);
    return data;
  },

  createPriceBook: async (body: PriceBookIn): Promise<PriceBookOut> => {
    const { data } = await apiClient.post<PriceBookOut>('/catalog/price-books', body);
    return data;
  },

  updatePriceBook: async (id: string, body: Partial<PriceBookIn>): Promise<PriceBookOut> => {
    const { data } = await apiClient.patch<PriceBookOut>(`/catalog/price-books/${id}`, body);
    return data;
  },

  // --- CPQ Simulator & Rules ---
  simulatePricing: async (body: PriceSimulationRequest): Promise<PriceSimulationResponse> => {
    const { data } = await apiClient.post<PriceSimulationResponse>('/cpq/simulate', body);
    return data;
  },

  listRules: async (): Promise<CPQRuleOut[]> => {
    const { data } = await apiClient.get<CPQRuleOut[]>('/cpq/rules');
    return data;
  },

  // --- CPQ Deals ---
  listDeals: async (params?: {
    customer_id?: string;
    status?: string;
    page?: number;
    page_size?: number;
  }): Promise<Paginated<CPQDealOut>> => {
    const { data } = await apiClient.get<Paginated<CPQDealOut>>('/cpq/deals', {
      params: cleanParams(params),
    });
    return data;
  },

  getDeal: async (id: string): Promise<CPQDealOut> => {
    const { data } = await apiClient.get<CPQDealOut>(`/cpq/deals/${id}`);
    return data;
  },

  createDeal: async (body: CPQDealIn): Promise<CPQDealOut> => {
    const { data } = await apiClient.post<CPQDealOut>('/cpq/deals', body);
    return data;
  },

  approveDeal: async (id: string): Promise<CPQDealOut> => {
    const { data } = await apiClient.post<CPQDealOut>(`/cpq/deals/${id}/approve`);
    return data;
  },

  rejectDeal: async (id: string, reason?: string): Promise<CPQDealOut> => {
    const { data } = await apiClient.post<CPQDealOut>(`/cpq/deals/${id}/reject`, null, {
      params: cleanParams({ reason }),
    });
    return data;
  },

  convertToQuote: async (id: string): Promise<QuoteOut> => {
    const { data } = await apiClient.post<QuoteOut>(`/cpq/deals/${id}/convert-quote`);
    return data;
  },
};
