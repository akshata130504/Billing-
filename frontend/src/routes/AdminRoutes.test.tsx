import { render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/common/Toast';
import tenantRoutesSource from './index.tsx?raw';

// A signed-out visitor of the tenant app (tenant auth state comes only from the tenant AuthProvider).
vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: false,
    isLoading: false,
    login: vi.fn(),
    completeMfaLogin: vi.fn(),
    hasRole: () => false,
  }),
}));

import { AppRoutes } from './index';

function Where() {
  const location = useLocation();
  const from = (location.state as { from?: { pathname: string; search?: string } } | null)?.from;
  return (
    <output data-testid="where">
      {location.pathname + location.search}
      {from ? ` from ${from.pathname}${from.search ?? ''}` : ''}
    </output>
  );
}

function renderAt(path: string) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
        <Where />
      </MemoryRouter>
    </ToastProvider>
  );
}

describe('/admin - the tenant app entry point', () => {
  beforeEach(() => vi.clearAllMocks());

  it('/admin opens the tenant sign-in directly', async () => {
    renderAt('/admin');
    expect(await screen.findByText('Sign in to your Rooman Billing workspace.')).toBeInTheDocument();
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/admin$/);
  });

  it('/admin/ (trailing slash) is the same entry point', async () => {
    renderAt('/admin/');
    expect(await screen.findByText('Sign in to your Rooman Billing workspace.')).toBeInTheDocument();
  });

  it('/admin/<page> is the tenant page itself, behind tenant sign-in', async () => {
    renderAt('/admin/customers?status=active');
    expect(await screen.findByText('Sign in to your Rooman Billing workspace.')).toBeInTheDocument();
    // ProtectedRoute sent the visitor to sign-in and remembers the page to return to
    expect(screen.getByTestId('where')).toHaveTextContent('/login from /customers?status=active');
  });

  it('the tenant app has no /superadmin route: the console is a separate document', () => {
    expect(tenantRoutesSource).not.toMatch(/path="\/superadmin/);
    expect(tenantRoutesSource).not.toMatch(/from '\.\.\/platform\//);
  });
});
