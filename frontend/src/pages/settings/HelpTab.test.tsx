import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

// No support mailbox configured for this test run.
vi.mock('../../utils/supportEmail', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../utils/supportEmail')>();
  return { ...actual, SUPPORT_EMAIL: '' };
});

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

import { HelpTab } from './HelpTab';

describe('<HelpTab /> without VITE_SUPPORT_EMAIL', () => {
  it('tells the user to contact their administrator and renders no mailto link', () => {
    const { container } = render(
      <MemoryRouter>
        <HelpTab />
      </MemoryRouter>
    );

    expect(screen.getByText('Contact support by email')).toBeInTheDocument();
    expect(screen.getAllByText(/Contact your administrator/i).length).toBeGreaterThan(0);
    expect(container.querySelector('a[href^="mailto:"]')).toBeNull();
    expect(screen.getByRole('button', { name: 'Email support' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Email a problem report' })).toBeDisabled();
    expect(screen.queryByText(/ticket/i)).toBeNull();
  });
});
