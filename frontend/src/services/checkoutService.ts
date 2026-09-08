import axios from 'axios';
import { API_BASE_URL, apiClient, cleanParams, toApiError } from './apiClient';
import type { Paginated } from '../types/api';
import type {
  CheckoutConfirmIn,
  CheckoutConfirmOut,
  CheckoutSession,
  CheckoutSessionCreate,
  CheckoutSessionListParams,
  CheckoutTemplate,
  CheckoutTemplateCreate,
  PublicCheckoutView,
} from '../types/checkout';

/**
 * Public checkout endpoints are token-in-URL and must never carry the admin
 * bearer token or trigger the refresh/logout interceptor — same pattern as
 * publicService.ts.
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

export const checkoutService = {
  // --- Admin (bearer auth) --------------------------------------------------

  listSessions: async (params?: CheckoutSessionListParams): Promise<Paginated<CheckoutSession>> => {
    const { data } = await apiClient.get<Paginated<CheckoutSession>>('/checkout/sessions', {
      params: cleanParams(params),
    });
    return data;
  },

  /** Requires finance role. The returned `token` is the raw one-time shareable token. */
  createSession: async (body: CheckoutSessionCreate): Promise<CheckoutSession> => {
    const { data } = await apiClient.post<CheckoutSession>('/checkout/sessions', body);
    return data;
  },

  listTemplates: async (): Promise<CheckoutTemplate[]> => {
    const { data } = await apiClient.get<CheckoutTemplate[]>('/checkout/templates');
    return data;
  },

  /** Requires finance role. */
  createTemplate: async (body: CheckoutTemplateCreate): Promise<CheckoutTemplate> => {
    const { data } = await apiClient.post<CheckoutTemplate>('/checkout/templates', body);
    return data;
  },

  // --- Public (token auth) --------------------------------------------------

  getPublic: async (token: string): Promise<PublicCheckoutView> => {
    const { data } = await publicClient.get<PublicCheckoutView>(`/checkout/public/${t(token)}`);
    return data;
  },

  confirmPublic: async (token: string, body: CheckoutConfirmIn): Promise<CheckoutConfirmOut> => {
    const { data } = await publicClient.post<CheckoutConfirmOut>(
      `/checkout/public/${t(token)}/confirm`,
      body
    );
    return data;
  },

  // --- Helpers ----------------------------------------------------------------

  /** Absolute SPA URL a customer opens: `${origin}/checkout/<token>`. */
  publicUrl: (token: string): string => `${window.location.origin}/checkout/${t(token)}`,
};
