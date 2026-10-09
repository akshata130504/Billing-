import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { authService } from '../services/authService';
import { ACCESS_CHANGED_EVENT, LOGOUT_EVENT, TRIAL_EXPIRED_EVENT, tokenStorage } from '../services/apiClient';
import type {
  LoginRequest,
  MeMembership,
  MeOrganizationSummary,
  OrganizationAccess,
  MeResponse,
  MeUser,
  MemberRole,
  OrganizationOut,
  TrialInfo,
} from '../types/api';

const ROLE_RANK: Record<MemberRole, number> = {
  viewer: 0,
  finance: 1,
  admin: 2,
  owner: 3,
};

export function roleAtLeast(role: MemberRole | null | undefined, min: MemberRole): boolean {
  if (!role) return false;
  return ROLE_RANK[role] >= ROLE_RANK[min];
}

/** Result of the password step: signed in, or a TOTP code is still needed (2FA accounts). */
export type LoginOutcome =
  | { status: 'signed_in'; me: MeResponse }
  | { status: 'mfa_required'; mfaToken: string };

export interface AuthContextValue {
  user: MeUser | null;
  organization: OrganizationOut | null;
  membership: MeMembership | null;
  organizations: MeOrganizationSummary[];
  /** Trial state, modules and seats (absent in previews and older test doubles: no restriction). */
  access?: OrganizationAccess | null;
  /** The organization's own free trial, or null when it has none (absent in previews and older test doubles). */
  trial?: TrialInfo | null;
  /** Server clock minus browser clock (ms), measured when /auth/me was last loaded (absent: 0). */
  serverClockOffsetMs?: number;
  isAuthenticated: boolean;
  /** True while the initial GET /auth/me (or an org switch) is in flight. */
  isLoading: boolean;
  login: (body: LoginRequest) => Promise<LoginOutcome>;
  /** Second step of a two-factor sign-in. */
  completeMfaLogin: (mfaToken: string, code: string) => Promise<MeResponse>;
  logout: () => Promise<void>;
  switchOrganization: (organizationId: string) => Promise<MeResponse>;
  refreshMe: () => Promise<MeResponse | null>;
  /** Apply tokens obtained elsewhere (e.g. accept-invitation, reset flows) and load /auth/me. */
  applyTokens: (tokens: { access_token: string; refresh_token: string }) => Promise<MeResponse>;
  hasRole: (min: MemberRole) => boolean;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [serverClockOffsetMs, setServerClockOffsetMs] = useState(0);
  const [isLoading, setIsLoading] = useState<boolean>(() => tokenStorage.hasSession());
  const mounted = useRef(true);

  const clearSession = useCallback(() => {
    tokenStorage.clear();
    setMe(null);
    queryClient.clear();
  }, [queryClient]);

  const loadMe = useCallback(async (): Promise<MeResponse> => {
    const data = await authService.me();
    if (mounted.current) {
      const serverMs = data.trial ? Date.parse(data.trial.server_time) : NaN;
      setServerClockOffsetMs(Number.isNaN(serverMs) ? 0 : serverMs - Date.now());
      setMe(data);
    }
    return data;
  }, []);

  // Initial hydration from an existing session.
  useEffect(() => {
    mounted.current = true;
    if (!tokenStorage.hasSession()) {
      setIsLoading(false);
      return () => {
        mounted.current = false;
      };
    }
    setIsLoading(true);
    loadMe()
      .catch(() => {
        // The interceptor already tried a refresh; anything left means no session.
        if (mounted.current) clearSession();
      })
      .finally(() => {
        if (mounted.current) setIsLoading(false);
      });
    return () => {
      mounted.current = false;
    };
  }, [loadMe, clearSession]);

  // The API client fires this when a refresh fails or a 401 cannot be recovered.
  useEffect(() => {
    const onForcedLogout = () => {
      setMe(null);
      queryClient.clear();
    };
    window.addEventListener(LOGOUT_EVENT, onForcedLogout);
    return () => window.removeEventListener(LOGOUT_EVENT, onForcedLogout);
  }, [queryClient]);

  const applyTokens = useCallback(
    async (tokens: { access_token: string; refresh_token: string }): Promise<MeResponse> => {
      tokenStorage.set(tokens);
      queryClient.clear();
      return loadMe();
    },
    [loadMe, queryClient]
  );

  const login = useCallback(
    async (body: LoginRequest): Promise<LoginOutcome> => {
      const result = await authService.login(body);
      if (result.mfa_required) {
        return { status: 'mfa_required', mfaToken: result.mfa_token };
      }
      return { status: 'signed_in', me: await applyTokens(result) };
    },
    [applyTokens]
  );

  const completeMfaLogin = useCallback(
    async (mfaToken: string, code: string): Promise<MeResponse> => {
      const tokens = await authService.loginMfa(mfaToken, code);
      return applyTokens(tokens);
    },
    [applyTokens]
  );

  // Signup is not exposed here: accounts are only created through the email-verified OTP
  // flow (authService.requestSignupVerification + verifySignupOtp, then applyTokens) that
  // SignupPage drives. The unverified POST /auth/signup endpoint was removed (410 Gone).

  const logout = useCallback(async (): Promise<void> => {
    const refreshToken = tokenStorage.getRefreshToken();
    try {
      if (refreshToken) await authService.logout(refreshToken);
    } catch {
      // Server-side revocation is best effort; the client session is cleared regardless.
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const switchOrganization = useCallback(
    async (organizationId: string): Promise<MeResponse> => {
      setIsLoading(true);
      try {
        const tokens = await authService.switchOrganization(organizationId);
        return await applyTokens(tokens);
      } finally {
        if (mounted.current) setIsLoading(false);
      }
    },
    [applyTokens]
  );

  const refreshMe = useCallback(async (): Promise<MeResponse | null> => {
    if (!tokenStorage.hasSession()) return null;
    return loadMe();
  }, [loadMe]);

  // The API refused a request because access changed (e.g. the trial just ended): reload /auth/me.
  useEffect(() => {
    let pending = false;
    const onAccessChanged = () => {
      if (pending || !tokenStorage.hasSession()) return;
      pending = true;
      void loadMe()
        .catch(() => undefined)
        .finally(() => {
          pending = false;
        });
    };
    window.addEventListener(ACCESS_CHANGED_EVENT, onAccessChanged);
    return () => window.removeEventListener(ACCESS_CHANGED_EVENT, onAccessChanged);
  }, [loadMe]);

  // A write was refused because the trial ended: re-read /auth/me so the whole UI follows.
  useEffect(() => {
    const onTrialExpired = () => {
      if (tokenStorage.hasSession()) void loadMe().catch(() => undefined);
    };
    window.addEventListener(TRIAL_EXPIRED_EVENT, onTrialExpired);
    return () => window.removeEventListener(TRIAL_EXPIRED_EVENT, onTrialExpired);
  }, [loadMe]);

  const hasRole = useCallback(
    (min: MemberRole) => roleAtLeast(me?.membership.role, min),
    [me]
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user: me?.user ?? null,
      organization: me?.organization ?? null,
      membership: me?.membership ?? null,
      organizations: me?.organizations ?? [],
      access: me?.access ?? null,
      trial: me?.trial ?? null,
      serverClockOffsetMs,
      isAuthenticated: me !== null,
      isLoading,
      login,
      completeMfaLogin,
      logout,
      switchOrganization,
      refreshMe,
      applyTokens,
      hasRole,
    }),
    [me, serverClockOffsetMs, isLoading, login, completeMfaLogin, logout, switchOrganization, refreshMe, applyTokens, hasRole]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
