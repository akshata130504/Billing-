import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('../../components/common/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));

import { PreferencesTab } from './PreferencesTab';

// QA (new-bugs PDF, "Settings - Account Preferences"): choosing Dark, leaving the tab and coming
// back switched the app to Light. The choice must be stored when it is made, and re-applied.
describe('PreferencesTab theme persistence', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('dark');
    window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }) as never;
  });
  afterEach(() => document.documentElement.classList.remove('dark'));

  it('keeps Dark after the tab is left and opened again, without pressing Save', () => {
    const first = render(<PreferencesTab />);
    fireEvent.click(screen.getByText('Dark'));
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    first.unmount();

    // Navigating elsewhere and back remounts the tab.
    render(<PreferencesTab />);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(JSON.parse(localStorage.getItem('rooman_account_preferences') || '{}').theme).toBe('dark');
  });
});
