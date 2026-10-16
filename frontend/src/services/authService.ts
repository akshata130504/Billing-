import { apiClient, tokenStorage } from './apiClient';
import type {
  AcceptInvitationRequest,
  AuthTokens,
  ForgotPasswordResponse,
  InvitationDetails,
  LoginRequest,
  MeResponse,
  SignupCompleteRequest,
  SignupConfirmEmailRequest,
  SignupConfirmEmailResponse,
  SignupResponse,
  SignupVerificationRequest,
  SignupVerificationResponse,
  SignupVerifyOtpRequest,
} from '../types/api';

/** POST /auth/login either signs in, or asks for a TOTP code when 2FA is enabled. */
export type LoginResult =
  | (AuthTokens & { mfa_required?: false })
  | { mfa_required: true; mfa_token: string; expires_in: number };

export interface TotpSetup {
  secret: string;
  otpauth_uri: string;
}

export interface AuthSession {
  id: string;
  organization_id: string | null;
  created_at: string;
  last_active_at: string;
  expires_at: string;
  user_agent: string | null;
  ip_address: string | null;
  current: boolean;
}

export const authService = {
  requestSignupVerification: async (body: SignupVerificationRequest): Promise<SignupVerificationResponse> => {
    const { data } = await apiClient.post<SignupVerificationResponse>('/auth/signup/request-verification', body);
    return data;
  },

  resendSignupOtp: async (email: string): Promise<SignupVerificationResponse> => {
    const { data } = await apiClient.post<SignupVerificationResponse>('/auth/signup/resend-otp', { email });
    return data;
  },

  confirmSignupEmail: async (body: SignupConfirmEmailRequest): Promise<SignupConfirmEmailResponse> => {
    const { data } = await apiClient.post<SignupConfirmEmailResponse>('/auth/signup/confirm-email', body);
    return data;
  },

  completeSignup: async (body: SignupCompleteRequest): Promise<SignupResponse> => {
    const { data } = await apiClient.post<SignupResponse>('/auth/signup/complete', body);
    return data;
  },

  verifySignupOtp: async (body: SignupVerifyOtpRequest): Promise<SignupResponse> => {
    const { data } = await apiClient.post<SignupResponse>('/auth/signup/verify-otp', body);
    return data;
  },

  login: async (body: LoginRequest): Promise<LoginResult> => {
    const { data } = await apiClient.post<LoginResult>('/auth/login', body);
    return data;
  },

  loginMfa: async (mfa_token: string, code: string): Promise<AuthTokens> => {
    const { data } = await apiClient.post<AuthTokens>('/auth/login/mfa', { mfa_token, code });
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
    // Send our own refresh token so the server keeps this session and only revokes the others.
    const refresh_token = tokenStorage.getRefreshToken() ?? undefined;
    await apiClient.post('/auth/change-password', { current_password, new_password, refresh_token });
  },

  forgotPassword: async (email: string): Promise<ForgotPasswordResponse> => {
    const { data } = await apiClient.post<ForgotPasswordResponse>('/auth/forgot-password', {
      email,
    });
    return data;
  },

  /** Resolves when the reset link is still usable; rejects with 422 when it is invalid, expired or used. */
  validateResetToken: async (token: string): Promise<void> => {
    await apiClient.post('/auth/reset-password/validate', { token });
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

  // --- two-factor authentication -----------------------------------------------------

  setupTwoFactor: async (): Promise<TotpSetup> => {
    const { data } = await apiClient.post<TotpSetup>('/auth/2fa/setup');
    return data;
  },

  enableTwoFactor: async (code: string): Promise<void> => {
    await apiClient.post('/auth/2fa/enable', { code });
  },

  disableTwoFactor: async (password: string, code: string): Promise<void> => {
    await apiClient.post('/auth/2fa/disable', { password, code });
  },

  // --- sessions ------------------------------------------------------------------------

  listSessions: async (): Promise<AuthSession[]> => {
    const { data } = await apiClient.get<AuthSession[]>('/auth/sessions');
    return data;
  },

  revokeSession: async (sessionId: string): Promise<void> => {
    await apiClient.delete(`/auth/sessions/${encodeURIComponent(sessionId)}`);
  },
};
