/** Shared render helper for the Mobile / Desktop platform visual-editor spec tests. */
import type { ReactElement } from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext, type AuthContextValue } from '../../hooks/useAuth';
import { ToastProvider } from '../../components/common/Toast';
import { UiConfigOverride, type UiSelection } from '../../appUi/UiConfigContext';
import type { PageConfigs } from '../../appUi/registry';

const NOW = '2026-01-01T00:00:00Z';
const fail = async (): Promise<never> => {
  throw new Error('not used');
};
const fakeAuth: AuthContextValue = {
  user: { id: 'u', email: 'asha@example.in', full_name: 'Asha Rao', last_login_at: null, created_at: NOW, two_factor_enabled: false },
  organization: null,
  membership: { id: 'm', role: 'owner', status: 'active', joined_at: NOW },
  organizations: [],
  isAuthenticated: true,
  isLoading: false,
  login: fail,
  completeMfaLogin: fail,
  logout: async () => undefined,
  switchOrganization: fail,
  refreshMe: async () => null,
  applyTokens: fail,
  hasRole: () => true,
};

const selection: UiSelection = { selectedId: null, select: () => undefined };

export function renderPlatformPage(page: ReactElement, path: string, pages?: PageConfigs) {
  const body = pages ? (
    <UiConfigOverride pages={pages} selection={selection}>
      {page}
    </UiConfigOverride>
  ) : (
    page
  );
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthContext.Provider value={fakeAuth}>
        <ToastProvider>{body}</ToastProvider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

export const columnHeaders = () => screen.getAllByRole('columnheader').map((th) => th.textContent);

export const uiIds = (container: HTMLElement, prefix: string) =>
  Array.from(container.querySelectorAll(`[data-ui-id^="${prefix}"]`)).map((el) => el.getAttribute('data-ui-id'));
