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
import { LOGOUT_EVENT, tokenStorage } from '../services/apiClient';
import type {
  LoginRequest,
  MeMembership,
  MeOrganizationSummary,
  MeResponse,
  MeUser,
  MemberRole,
  OrganizationOut,
  SignupRequest,
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

export interface AuthContextValue {
  user: MeUser | null;
  organization: OrganizationOut | null;
  membership: MeMembership | null;
  organizations: MeOrganizationSummary[];
  isAuthenticated: boolean;
  /** True while the initial GET /auth/me (or an org switch) is in flight. */
  isLoading: boolean;
  login: (body: LoginRequest) => Promise<MeResponse>;
  signup: (body: SignupRequest) => Promise<MeResponse>;
  logout: () => Promise<void>;
  switchOrganization: (organizationId: string) => Promise<MeResponse>;
  refreshMe: () => Promise<MeResponse | null>;
  /** Apply tokens obtained elsewhere (e.g. accept-invitation, reset flows) and load /auth/me. */
  applyTokens: (tokens: { access_token: string; refresh_token: string }) => Promise<MeResponse>;
  hasRole: (min: MemberRole) => boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(() => tokenStorage.hasSession());
  const mounted = useRef(true);

  const clearSession = useCallback(() => {
    tokenStorage.clear();
    setMe(null);
    queryClient.clear();
  }, [queryClient]);

  const loadMe = useCallback(async (): Promise<MeResponse> => {
    const data = await authService.me();
    if (mounted.current) setMe(data);
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
    async (body: LoginRequest): Promise<MeResponse> => {
      const tokens = await authService.login(body);
      return applyTokens(tokens);
    },
    [applyTokens]
  );

  const signup = useCallback(
    async (body: SignupRequest): Promise<MeResponse> => {
      const response = await authService.signup(body);
      tokenStorage.set(response);
      queryClient.clear();
      if (mounted.current) setMe(response.me);
      return response.me;
    },
    [queryClient]
  );

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
      isAuthenticated: me !== null,
      isLoading,
      login,
      signup,
      logout,
      switchOrganization,
      refreshMe,
      applyTokens,
      hasRole,
    }),
    [me, isLoading, login, signup, logout, switchOrganization, refreshMe, applyTokens, hasRole]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
