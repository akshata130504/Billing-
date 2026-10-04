import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { LoginPage } from './LoginPage';

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: false,
    isLoading: false,
    login: vi.fn(),
    completeMfaLogin: vi.fn(),
  }),
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

function renderLogin() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>
  );
}

describe('LoginPage layout', () => {
  it('renders the tagline in flow (not absolutely positioned) before the form card', () => {
    renderLogin();
    const tagline = screen.getByTestId('login-tagline');
    const card = screen.getByTestId('login-card');
    expect(tagline.className).not.toMatch(/\babsolute\b/);
    expect(tagline.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(tagline).toHaveTextContent('SIMPLE BILLING.');
    expect(tagline).toHaveTextContent('STRONGER TOMORROW.');
  });

  it('keeps the tagline hidden on small screens', () => {
    renderLogin();
    const tagline = screen.getByTestId('login-tagline');
    expect(tagline).toHaveClass('hidden', 'lg:block');
  });

  it('renders the fields and Sign in button', () => {
    renderLogin();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });
});
