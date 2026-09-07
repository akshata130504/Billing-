import { apiClient } from './apiClient';
import { HealthResponse } from '../types';

export const healthService = {
  getHealth: async (): Promise<HealthResponse> => {
    const response = await apiClient.get<HealthResponse>('/health');
    return response.data;
  },
};
