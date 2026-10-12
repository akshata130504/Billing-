import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PortalLoginPage } from './PortalLoginPage';

vi.mock('../../services/portalCustomerService', () => ({ portalCustomerService: {} }));

describe('<PortalLoginPage /> labels (BUG-22)', () => {
  it('associates the email, password and organization labels with their inputs', () => {
    render(
      <MemoryRouter>
        <PortalLoginPage />
      </MemoryRouter>
    );
    expect(screen.getByLabelText(/^Email Address/i)).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText(/^Password/i)).toHaveAttribute('type', 'password');
    expect(screen.getByLabelText(/^Organization ID/i)).toHaveAttribute('type', 'text');
  });
});
