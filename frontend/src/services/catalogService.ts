import { apiClient, cleanParams } from './apiClient';
import type {
  Paginated,
  PlanIn,
  PlanListParams,
  PlanOut,
  ProductIn,
  ProductListParams,
  ProductOut,
} from '../types/api';

export const catalogService = {
  listProducts: async (params?: ProductListParams): Promise<Paginated<ProductOut>> => {
    const { data } = await apiClient.get<Paginated<ProductOut>>('/products', {
      params: cleanParams(params),
    });
    return data;
  },

  getProduct: async (id: string): Promise<ProductOut> => {
    const { data } = await apiClient.get<ProductOut>(`/products/${id}`);
    return data;
  },

  createProduct: async (body: ProductIn): Promise<ProductOut> => {
    const { data } = await apiClient.post<ProductOut>('/products', body);
    return data;
  },

  updateProduct: async (id: string, body: Partial<ProductIn>): Promise<ProductOut> => {
    const { data } = await apiClient.patch<ProductOut>(`/products/${id}`, body);
    return data;
  },

  deleteProduct: async (id: string): Promise<void> => {
    await apiClient.delete(`/products/${id}`);
  },

  listPlans: async (params?: PlanListParams): Promise<Paginated<PlanOut>> => {
    const { data } = await apiClient.get<Paginated<PlanOut>>('/plans', {
      params: cleanParams(params),
    });
    return data;
  },

  getPlan: async (id: string): Promise<PlanOut> => {
    const { data } = await apiClient.get<PlanOut>(`/plans/${id}`);
    return data;
  },

  createPlan: async (body: PlanIn): Promise<PlanOut> => {
    const { data } = await apiClient.post<PlanOut>('/plans', body);
    return data;
  },

  updatePlan: async (id: string, body: Partial<PlanIn>): Promise<PlanOut> => {
    const { data } = await apiClient.patch<PlanOut>(`/plans/${id}`, body);
    return data;
  },

  deletePlan: async (id: string): Promise<void> => {
    await apiClient.delete(`/plans/${id}`);
  },
};
