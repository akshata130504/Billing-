import { apiClient } from './apiClient';
import type {
  SubscriptionChangeApplyIn,
  SubscriptionChangeOut,
  SubscriptionChangePreviewIn,
  SubscriptionChangePreviewOut,
} from '../types/proration';

export const prorationService = {
  /** Read-only calculation; nothing is persisted. Viewer role and above. */
  preview: async (
    subscriptionId: string,
    body: SubscriptionChangePreviewIn
  ): Promise<SubscriptionChangePreviewOut> => {
    const { data } = await apiClient.post<SubscriptionChangePreviewOut>(
      `/subscriptions/${subscriptionId}/changes/preview`,
      body
    );
    return data;
  },

  /** Applies (immediate / scheduled) or defers (end_of_term) a change. Finance role and above. */
  apply: async (subscriptionId: string, body: SubscriptionChangeApplyIn): Promise<SubscriptionChangeOut> => {
    const { data } = await apiClient.post<SubscriptionChangeOut>(
      `/subscriptions/${subscriptionId}/changes`,
      body
    );
    return data;
  },

  /** Full change history for one subscription, newest first (not paginated). */
  list: async (subscriptionId: string): Promise<SubscriptionChangeOut[]> => {
    const { data } = await apiClient.get<SubscriptionChangeOut[]>(`/subscriptions/${subscriptionId}/changes`);
    return data;
  },

  /** Only `scheduled` changes can be cancelled. Admin role and above. */
  cancel: async (subscriptionId: string, changeId: string): Promise<SubscriptionChangeOut> => {
    const { data } = await apiClient.post<SubscriptionChangeOut>(
      `/subscriptions/${subscriptionId}/changes/${changeId}/cancel`
    );
    return data;
  },
};
