import axios from 'axios';
import { API_BASE_URL, absoluteUrl, toApiError } from './apiClient';
import type {
  HealthResponse,
  IntegrationsMeta,
  PublicInvoice,
  PublicQuote,
  RazorpayOrderResponse,
  RazorpayVerifyRequest,
  RazorpayVerifyResponse,
} from '../types/api';

/**
 * Public endpoints never carry a bearer token and must not trigger the
 * refresh/logout interceptor, so they use a bare axios instance.
 */
const publicClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 20000,
});

publicClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => Promise.reject(toApiError(error))
);

const t = (token: string) => encodeURIComponent(token);

export const publicService = {
  getInvoice: async (token: string): Promise<PublicInvoice> => {
    const { data } = await publicClient.get<PublicInvoice>(`/public/invoices/${t(token)}`);
    return data;
  },

  /** Public PDF — no token required; safe to use as a plain link. */
  invoicePdfUrl: (token: string): string => absoluteUrl(`/public/invoices/${t(token)}/pdf`),

  createRazorpayOrder: async (token: string, amount?: string): Promise<RazorpayOrderResponse> => {
    const { data } = await publicClient.post<RazorpayOrderResponse>(
      `/public/invoices/${t(token)}/razorpay-order`,
      amount !== undefined ? { amount } : {}
    );
    return data;
  },

  verifyRazorpayPayment: async (
    token: string,
    body: RazorpayVerifyRequest
  ): Promise<RazorpayVerifyResponse> => {
    const { data } = await publicClient.post<RazorpayVerifyResponse>(
      `/public/invoices/${t(token)}/razorpay-verify`,
      body
    );
    return data;
  },

  getQuote: async (token: string): Promise<PublicQuote> => {
    const { data } = await publicClient.get<PublicQuote>(`/public/quotes/${t(token)}`);
    return data;
  },

  /** Idempotent: repeating it returns the quote's current accepted/converted status. */
  acceptQuote: async (token: string, accepted_by_name: string): Promise<{ status: string }> => {
    const { data } = await publicClient.post<{ status: string }>(
      `/public/quotes/${t(token)}/accept`,
      { accepted_by_name }
    );
    return data;
  },

  declineQuote: async (token: string, reason?: string): Promise<{ status: string }> => {
    const { data } = await publicClient.post<{ status: string }>(
      `/public/quotes/${t(token)}/decline`,
      { reason }
    );
    return data;
  },

  integrations: async (): Promise<IntegrationsMeta> => {
    const { data } = await publicClient.get<IntegrationsMeta>('/meta/integrations');
    return data;
  },

  health: async (): Promise<HealthResponse> => {
    const { data } = await publicClient.get<HealthResponse>('/health');
    return data;
  },
};
