import { apiClient } from './apiClient';
import type {
  AcceptInvitationRequest,
  AuthTokens,
  ForgotPasswordResponse,
  InvitationDetails,
  LoginRequest,
  MeResponse,
  SignupRequest,
  SignupResponse,
} from '../types/api';

export const authService = {
  signup: async (body: SignupRequest): Promise<SignupResponse> => {
    const { data } = await apiClient.post<SignupResponse>('/auth/signup', body);
    return data;
  },

  login: async (body: LoginRequest): Promise<AuthTokens> => {
    const { data } = await apiClient.post<AuthTokens>('/auth/login', body);
    return data;
  },

  refresh: async (refresh_token: string): Promise<AuthTokens> => {
    const { data } = await apiClient.post<AuthTokens>('/auth/refresh', { refresh_token });
    return data;
  },

  logout: async (refresh_token: string): Promise<void> => {
    await apiClient.post('/auth/logout', { refresh_token });
  },

  me: async (): Promise<MeResponse> => {
    const { data } = await apiClient.get<MeResponse>('/auth/me');
    return data;
  },

  switchOrganization: async (organization_id: string): Promise<AuthTokens> => {
    const { data } = await apiClient.post<AuthTokens>('/auth/switch-organization', {
      organization_id,
    });
    return data;
  },

  changePassword: async (current_password: string, new_password: string): Promise<void> => {
    await apiClient.post('/auth/change-password', { current_password, new_password });
  },

  forgotPassword: async (email: string): Promise<ForgotPasswordResponse> => {
    const { data } = await apiClient.post<ForgotPasswordResponse>('/auth/forgot-password', {
      email,
    });
    return data;
  },

  resetPassword: async (token: string, new_password: string): Promise<void> => {
    await apiClient.post('/auth/reset-password', { token, new_password });
  },

  getInvitation: async (token: string): Promise<InvitationDetails> => {
    const { data } = await apiClient.get<InvitationDetails>(
      `/auth/invitations/${encodeURIComponent(token)}`
    );
    return data;
  },

  acceptInvitation: async (body: AcceptInvitationRequest): Promise<AuthTokens> => {
    const { data } = await apiClient.post<AuthTokens>('/auth/accept-invitation', body);
    return data;
  },
};
