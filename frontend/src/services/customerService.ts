import { apiClient, cleanParams } from './apiClient';
import type {
  ContactIn,
  CustomerIn,
  CustomerListParams,
  CustomerOut,
  InvoiceOut,
  PageParams,
  Paginated,
  PaymentOut,
  SubscriptionOut,
} from '../types/api';
import type { CustomerPortalAccessStatusOut, CustomerPortalInvitationOut } from '../types/portal';

export const customerService = {
  list: async (params?: CustomerListParams): Promise<Paginated<CustomerOut>> => {
    const { data } = await apiClient.get<Paginated<CustomerOut>>('/customers', {
      params: cleanParams(params),
    });
    return data;
  },

  get: async (id: string): Promise<CustomerOut> => {
    const { data } = await apiClient.get<CustomerOut>(`/customers/${id}`);
    return data;
  },

  create: async (body: CustomerIn): Promise<CustomerOut> => {
    const { data } = await apiClient.post<CustomerOut>('/customers', body);
    return data;
  },

  update: async (id: string, body: Partial<CustomerIn>): Promise<CustomerOut> => {
    const { data } = await apiClient.patch<CustomerOut>(`/customers/${id}`, body);
    return data;
  },

  remove: async (id: string): Promise<void> => {
    await apiClient.delete(`/customers/${id}`);
  },

  setContacts: async (id: string, contacts: ContactIn[]): Promise<CustomerOut> => {
    const { data } = await apiClient.put<CustomerOut>(`/customers/${id}/contacts`, contacts);
    return data;
  },

  invoices: async (id: string, params?: PageParams): Promise<Paginated<InvoiceOut>> => {
    const { data } = await apiClient.get<Paginated<InvoiceOut>>(`/customers/${id}/invoices`, {
      params: cleanParams(params),
    });
    return data;
  },

  payments: async (id: string, params?: PageParams): Promise<Paginated<PaymentOut>> => {
    const { data } = await apiClient.get<Paginated<PaymentOut>>(`/customers/${id}/payments`, {
      params: cleanParams(params),
    });
    return data;
  },

  subscriptions: async (id: string, params?: PageParams): Promise<Paginated<SubscriptionOut>> => {
    const { data } = await apiClient.get<Paginated<SubscriptionOut>>(
      `/customers/${id}/subscriptions`,
      { params: cleanParams(params) }
    );
    return data;
  },

  getPortalAccess: async (id: string): Promise<CustomerPortalAccessStatusOut> => {
    const { data } = await apiClient.get<CustomerPortalAccessStatusOut>(`/customers/${id}/portal-access`);
    return data;
  },

  inviteToPortal: async (id: string, email?: string): Promise<CustomerPortalInvitationOut> => {
    const { data } = await apiClient.post<CustomerPortalInvitationOut>(`/customers/${id}/portal-invite`, {
      email: email || undefined,
    });
    return data;
  },

  revokePortalAccess: async (id: string): Promise<CustomerPortalAccessStatusOut> => {
    const { data } = await apiClient.post<CustomerPortalAccessStatusOut>(`/customers/${id}/portal-revoke`);
    return data;
  },

  reactivatePortalAccess: async (id: string): Promise<CustomerPortalAccessStatusOut> => {
    const { data } = await apiClient.post<CustomerPortalAccessStatusOut>(`/customers/${id}/portal-reactivate`);
    return data;
  },
};
