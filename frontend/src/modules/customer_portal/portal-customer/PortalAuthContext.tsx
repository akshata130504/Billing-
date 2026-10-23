import React, { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  portalCustomerService,
  portalTokenStorage,
} from '../../../services/portalCustomerService';
import type { PortalLoginIn, PortalUserOut } from '../../../types/portal';

interface PortalAuthContextType {
  user: PortalUserOut | null;
  customerName: string;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: PortalLoginIn) => Promise<void>;
  logout: () => Promise<void>;
}

const PortalAuthContext = createContext<PortalAuthContextType | undefined>(undefined);

export const PortalAuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<PortalUserOut | null>(portalTokenStorage.getUser());
  const [customerName, setCustomerName] = useState<string>(portalTokenStorage.getCustomerName());
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(portalTokenStorage.hasSession());
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const navigate = useNavigate();

  useEffect(() => {
    const hasToken = portalTokenStorage.hasSession();
    setIsAuthenticated(hasToken);
    if (hasToken) {
      setUser(portalTokenStorage.getUser());
      setCustomerName(portalTokenStorage.getCustomerName());
    }
    setIsLoading(false);
  }, []);

  const login = async (credentials: PortalLoginIn) => {
    const res = await portalCustomerService.login(credentials);
    setUser(res.user);
    setCustomerName(res.customer_display_name || '');
    setIsAuthenticated(true);
  };

  const logout = async () => {
    await portalCustomerService.logout();
    setUser(null);
    setCustomerName('');
    setIsAuthenticated(false);
    navigate('/portal/login', { replace: true });
  };

  return (
    <PortalAuthContext.Provider
      value={{
        user,
        customerName,
        isAuthenticated,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </PortalAuthContext.Provider>
  );
};

export const usePortalAuth = (): PortalAuthContextType => {
  const context = useContext(PortalAuthContext);
  if (!context) {
    throw new Error('usePortalAuth must be used within a PortalAuthProvider');
  }
  return context;
};
