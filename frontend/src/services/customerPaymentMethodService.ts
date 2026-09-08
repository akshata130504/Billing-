import { apiClient } from './apiClient';
import type {
  CustomerPaymentMethodCreateIn,
  CustomerPaymentMethodOut,
} from '../types/customers';

/** Vaulted payment methods for a customer — /customers/{id}/payment-methods. */
export const customerPaymentMethodService = {
  list: async (customerId: string): Promise<CustomerPaymentMethodOut[]> => {
    const { data } = await apiClient.get<CustomerPaymentMethodOut[]>(
      `/customers/${customerId}/payment-methods`
    );
    return data;
  },

  create: async (
    customerId: string,
    body: CustomerPaymentMethodCreateIn
  ): Promise<CustomerPaymentMethodOut> => {
    const { data } = await apiClient.post<CustomerPaymentMethodOut>(
      `/customers/${customerId}/payment-methods`,
      body
    );
    return data;
  },

  setDefault: async (
    customerId: string,
    paymentMethodId: string
  ): Promise<CustomerPaymentMethodOut> => {
    const { data } = await apiClient.post<CustomerPaymentMethodOut>(
      `/customers/${customerId}/payment-methods/${paymentMethodId}/set-default`
    );
    return data;
  },

  /** Revokes (soft-deletes) the method; the API returns the updated row. */
  revoke: async (
    customerId: string,
    paymentMethodId: string
  ): Promise<CustomerPaymentMethodOut> => {
    const { data } = await apiClient.delete<CustomerPaymentMethodOut>(
      `/customers/${customerId}/payment-methods/${paymentMethodId}`
    );
    return data;
  },
};
