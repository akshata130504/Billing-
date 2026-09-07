import axios, { AxiosError } from 'axios';
import { ApiError } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
});

// Response interceptor to format errors uniformly
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ error?: ApiError }>) => {
    const customError: ApiError = error.response?.data?.error || {
      code: error.code || 'NETWORK_ERROR',
      message: error.message || 'An unexpected error occurred while contacting the server.',
      details: error.response?.data ? (error.response.data as Record<string, unknown>) : undefined,
    };
    return Promise.reject(customError);
  }
);
