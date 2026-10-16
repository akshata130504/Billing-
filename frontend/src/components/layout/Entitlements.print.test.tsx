import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ access: { status: 'trial', trial_ends_at: null } }),
}));

import { TrialBanner } from './Entitlements';

// QA (new-bugs PDF, "Quotes - Quote Details - Print"): printing a quote must give only the document.
// The global @media print rule hides `.no-print`; the trial banner sits above every page.
describe('TrialBanner', () => {
  it('is excluded from printed documents', () => {
    render(<MemoryRouter><TrialBanner /></MemoryRouter>);
    expect(screen.getByRole('status')).toHaveClass('no-print');
  });
});
