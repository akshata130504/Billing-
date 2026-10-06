import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { ToastProvider } from '../../../components/common/Toast';
import { ConsoleContext, type ConsoleSession } from '../ConsoleContext';
import { PlatformApiError, platformApi, type PlatformRole } from '../../platformApi';
import { appUiApi, type AppUiPageState } from '../../appUiApi';
import { OVERVIEW_KPI_DEFS, type PageKey } from '../../../appUi/registry';
import { VisualEditorPage } from './VisualEditorPage';

vi.mock('../../platformApi', async () => {
  const actual = await vi.importActual<typeof import('../../platformApi')>('../../platformApi');
  return {
    ...actual,
    platformApi: { me: vi.fn(), refresh: vi.fn(), logout: vi.fn(), stepUp: vi.fn(), sessions: vi.fn() },
  };
});
vi.mock('../../appUiApi', async () => {
  const actual = await vi.importActual<typeof import('../../appUiApi')>('../../appUiApi');
  return {
    ...actual,
    appUiApi: {
      pages: vi.fn(), state: vi.fn(), saveDraft: vi.fn(), discardDraft: vi.fn(), publish: vi.fn(),
      versions: vi.fn(), version: vi.fn(), rollback: vi.fn(), restore: vi.fn(),
    },
  };
});

type Mocked<T> = { [K in keyof T]: ReturnType<typeof vi.fn> };
const auth = platformApi as unknown as Mocked<typeof platformApi>;
const api = appUiApi as unknown as Mocked<typeof appUiApi>;

const meta = (over: object = {}) => ({
  id: 'v', state: 'published' as const, version: 3, revision: 1, content_sha256: 'x', note: null,
  based_on_version: null, created_at: null, created_by_staff_id: null, updated_at: null, updated_by_staff_id: null,
  published_at: '2026-10-01T09:00:00Z', published_by_staff_id: 'staff-123456789', ...over,
});

function pageState(
  key: PageKey = 'overview',
  opts: { published?: Record<string, unknown> | null; draft?: Record<string, unknown> | null; revision?: number; version?: number } = {},
): AppUiPageState {
  const { published = null, draft = null, revision = 1, version = 3 } = opts;
  return {
    key,
    title: key,
    published: published ? ({ ...meta({ version }), content: published } as AppUiPageState['published']) : null,
    defaults: {},
    draft: draft
      ? ({ ...meta({ id: 'd', state: 'draft', version: null, revision }), content: draft, changes: [] } as AppUiPageState['draft'])
      : null,
    updated_at: null,
    updated_by_staff_id: null,
  };
}

function session(role: PlatformRole): ConsoleSession {
  return {
    me: { staff: { id: 's', email: 'a@rooman.test', full_name: 'Ada Admin', role }, session_id: 'x', session_expires_at: '2026-10-02T00:00:00Z', access_expires_in: 600 },
    role,
    hasRole: (...roles) => roles.includes(role),
    signOut: async () => undefined,
  };
}

function renderEditor(role: PlatformRole = 'platform_administrator') {
  return render(
    <ToastProvider>
      <ConsoleContext.Provider value={session(role)}>
        <VisualEditorPage />
      </ConsoleContext.Provider>
    </ToastProvider>,
  );
}

const frame = () => screen.getByTitle('Application preview') as HTMLIFrameElement;
const properties = () => screen.getByRole('complementary', { name: 'Properties' });
const tree = () => screen.getByRole('navigation', { name: 'Components' });

function post(data: unknown, opts: { origin?: string; source?: Window | null } = {}) {
  act(() => {
    window.dispatchEvent(new MessageEvent('message', {
      data,
      origin: opts.origin ?? window.location.origin,
      source: opts.source === undefined ? frame().contentWindow : opts.source,
    }));
  });
}

async function loaded() {
  await screen.findByTitle('Application preview');
}

beforeEach(() => {
  vi.clearAllMocks();
  api.pages.mockResolvedValue({ items: [], can_edit: true });
  api.state.mockImplementation((key: PageKey) => Promise.resolve(pageState(key)));
});

// Rendering the full editor (with a jsdom iframe window) is slow on loaded CI machines.
describe('visual editor', { timeout: 20000 }, () => {
  it('loads the overview page with the preview frame', async () => {
    renderEditor();
    await loaded();
    expect(api.state).toHaveBeenCalledWith('overview');
    expect(frame()).toHaveAttribute('src', '/superadmin/ui-preview');
    expect(frame().getAttribute('sandbox')).toBe('allow-scripts allow-same-origin');
    expect(screen.getByLabelText('Page')).toHaveValue('overview');
    expect(screen.getByText('Live: built-in defaults')).toBeInTheDocument();
    expect(within(properties()).getByText(/Select a component/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Save draft/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Publish/ })).toBeDisabled();
  });

  it('switches page', async () => {
    renderEditor();
    await loaded();
    fireEvent.change(screen.getByLabelText('Page'), { target: { value: 'customers' } });
    await waitFor(() => expect(api.state).toHaveBeenCalledWith('customers'));
    expect(await within(tree()).findByRole('button', { name: 'Table columns' })).toBeInTheDocument();
    expect(within(tree()).queryByRole('button', { name: 'KPI cards' })).not.toBeInTheDocument();
  });

  it('selecting a group shows its properties', async () => {
    renderEditor();
    await loaded();
    fireEvent.click(within(tree()).getByRole('button', { name: 'Page header' }));
    expect(within(properties()).getByRole('heading', { name: 'Page header' })).toBeInTheDocument();
    expect(within(properties()).getByDisplayValue('Welcome back, {first_name}!')).toBeInTheDocument();
    fireEvent.click(within(tree()).getByRole('button', { name: 'KPI cards' }));
    expect(within(properties()).getByRole('heading', { name: 'KPI cards' })).toBeInTheDocument();
    expect(within(properties()).getByLabelText('Total Revenue label')).toHaveValue('Total Revenue');
    // Items of the selected group are listed in the tree.
    expect(within(tree()).getByRole('button', { name: 'Churn Rate' })).toBeInTheDocument();
  });

  it('edits a label, summarises it, supports undo/redo and saves the draft', async () => {
    api.saveDraft.mockImplementation((key: PageKey, content: Record<string, unknown>) =>
      Promise.resolve(pageState(key, { draft: content, revision: 1 })));
    renderEditor();
    await loaded();
    fireEvent.click(within(tree()).getByRole('button', { name: 'KPI cards' }));
    fireEvent.change(within(properties()).getByLabelText('Total Revenue label'), { target: { value: 'Gross revenue' } });
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    expect(within(properties()).getByText(/KPI cards: “Total Revenue” renamed to “Gross revenue”/)).toBeInTheDocument();
    expect(within(properties()).getByText('Differences from live (1)')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(within(properties()).getByLabelText('Total Revenue label')).toHaveValue('Total Revenue');
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Redo' }));
    expect(within(properties()).getByLabelText('Total Revenue label')).toHaveValue('Gross revenue');
    expect(screen.getByRole('button', { name: 'Redo' })).toBeDisabled();

    fireEvent.click(within(properties()).getByRole('button', { name: 'Hide Churn Rate' }));
    fireEvent.click(screen.getByRole('button', { name: /Save draft/ }));
    await waitFor(() => expect(api.saveDraft).toHaveBeenCalledTimes(1));
    const [page, content, revision] = api.saveDraft.mock.calls[0];
    expect(page).toBe('overview');
    expect(revision).toBe(0);
    expect(content).toEqual({
      kpis: OVERVIEW_KPI_DEFS.map((d) =>
        d.key === 'total_revenue' ? { key: d.key, label: 'Gross revenue' } : d.key === 'churn_rate' ? { key: d.key, hidden: true } : { key: d.key }),
    });
    expect(await screen.findByText('Draft saved. It is not live yet.')).toBeInTheDocument();
    expect(screen.getByText('Saved draft')).toBeInTheDocument();
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Publish/ })).toBeEnabled();
  });

  it('changes the preview width per viewport', async () => {
    renderEditor();
    await loaded();
    expect(frame().style.width).toBe('1280px');
    fireEvent.click(screen.getByRole('button', { name: 'tablet' }));
    expect(frame().style.width).toBe('820px');
    expect(screen.getByRole('button', { name: 'tablet' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'mobile' }));
    expect(frame().style.width).toBe('390px');
    expect(screen.getByText('390px')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'desktop' }));
    expect(frame().style.width).toBe('1280px');
  });

  it('shows validation problems from the server', async () => {
    api.saveDraft.mockRejectedValue(new PlatformApiError('The request contains invalid fields.', 422, 'VALIDATION_ERROR', {
      problems: [{ field: 'header.title', message: 'markup characters are not allowed' }],
    }));
    renderEditor();
    await loaded();
    fireEvent.click(within(tree()).getByRole('button', { name: 'Page header' }));
    fireEvent.change(within(properties()).getByDisplayValue('Welcome back, {first_name}!'), { target: { value: '<b>Hi</b>' } });
    fireEvent.click(screen.getByRole('button', { name: /Save draft/ }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The request contains invalid fields. header.title: markup characters are not allowed');
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument(); // edits are kept
  });

  it('publishes the saved draft with a reason and step-up', async () => {
    const draft = { header: { title: 'Hello {first_name}' } };
    api.state.mockResolvedValue(pageState('overview', { draft, revision: 4 }));
    api.publish
      .mockRejectedValueOnce(new PlatformApiError('Confirm it is you.', 403, 'STEP_UP_REQUIRED'))
      .mockResolvedValueOnce(pageState('overview', { published: draft, version: 5 }));
    auth.stepUp.mockResolvedValue({ step_up_expires_at: 'x', expires_in: 900 });
    renderEditor();
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: /Publish/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('1 change will go live for every organization.')).toBeInTheDocument();
    expect(within(dialog).getByText('Page header – Heading: “Welcome back, {first_name}!” → “Hello {first_name}”')).toBeInTheDocument();
    const confirm = within(dialog).getByRole('button', { name: 'Publish' });
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'too short' } });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'New greeting for launch' } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    fireEvent.change(await within(dialog).findByLabelText(/^Password/), { target: { value: 'Platform-Passw0rd-2026!' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Verify and publish' }));
    await waitFor(() => expect(api.publish).toHaveBeenCalledTimes(2));
    expect(auth.stepUp).toHaveBeenCalledWith('Platform-Passw0rd-2026!');
    expect(api.publish).toHaveBeenLastCalledWith('overview', 4, 'New greeting for launch');
    expect(await screen.findByText(/Published version 5/)).toBeInTheDocument();
    expect(screen.getByText('Live: version 5')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('lists history, previews a version read-only and rolls back with step-up', async () => {
    api.state.mockResolvedValue(pageState('overview', { published: { header: { title: 'Live v3' } }, version: 3 }));
    api.versions.mockResolvedValue({ items: [
      { ...meta({ id: 'v3', version: 3, note: 'Current look' }), live: true },
      { ...meta({ id: 'v2', version: 2, note: 'Older look' }), live: false },
    ], total: 2 });
    api.version.mockResolvedValue({ ...meta({ version: 2 }), content: { header: { title: 'Old v2' } } });
    api.rollback
      .mockRejectedValueOnce(new PlatformApiError('Confirm it is you.', 403, 'STEP_UP_REQUIRED'))
      .mockResolvedValueOnce(pageState('overview', { published: { header: { title: 'Old v2' } }, version: 4 }));
    auth.stepUp.mockResolvedValue({});
    renderEditor();
    await loaded();
    fireEvent.click(screen.getByRole('button', { name: 'History' }));
    const row = (await screen.findByText('Older look')).closest('tr')!;
    const liveRow = screen.getByText('Current look').closest('tr')!;
    expect(within(liveRow).queryByRole('button', { name: 'Roll back' })).not.toBeInTheDocument();
    expect(api.versions).toHaveBeenCalledWith('overview');

    fireEvent.click(within(row).getByRole('button', { name: 'Preview' }));
    expect(await screen.findByText(/Previewing version 2 \(read-only\)/)).toBeInTheDocument();
    expect(api.version).toHaveBeenCalledWith('overview', 2);
    fireEvent.click(within(tree()).getByRole('button', { name: 'Page header' }));
    expect(within(properties()).getByDisplayValue('Live v3')).toBeDisabled();
    expect(screen.getByRole('button', { name: /Save draft/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Back to editing' }));
    expect(within(properties()).getByDisplayValue('Live v3')).toBeEnabled();

    fireEvent.click(within(row).getByRole('button', { name: 'Roll back' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Roll back to version 2')).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Revert the new header' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Roll back' }));
    fireEvent.change(await within(dialog).findByLabelText(/^Password/), { target: { value: 'pw-123456789' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Verify and roll back' }));
    await waitFor(() => expect(api.rollback).toHaveBeenCalledTimes(2));
    expect(api.rollback).toHaveBeenLastCalledWith('overview', 2, 'Revert the new header');
    expect(await screen.findByText('Rolled back. Version 4 is live.')).toBeInTheDocument();
  });

  it('is read-only for roles that cannot edit', async () => {
    api.pages.mockResolvedValue({ items: [], can_edit: false });
    renderEditor('platform_support');
    await loaded();
    expect(screen.getByText(/Read-only: your platform role/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Save draft/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Publish/ })).not.toBeInTheDocument();
    fireEvent.click(within(tree()).getByRole('button', { name: 'KPI cards' }));
    expect(within(properties()).getByLabelText('Total Revenue label')).toBeDisabled();
    expect(within(properties()).getByRole('button', { name: 'Hide Churn Rate' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
  });

  it('shows an error with retry when loading fails', async () => {
    api.pages.mockRejectedValueOnce(new PlatformApiError('The service is unavailable.', 503, 'UNAVAILABLE'));
    renderEditor();
    expect(await screen.findByText('The service is unavailable.')).toBeInTheDocument();
    expect(screen.queryByTitle('Application preview')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Retry/ }));
    await loaded();
    expect(api.pages).toHaveBeenCalledTimes(2);
  });

  it('talks to the preview frame only through trusted same-origin messages', async () => {
    renderEditor();
    await loaded();
    const target = frame().contentWindow!;
    const postToFrame = vi.spyOn(target, 'postMessage').mockImplementation(() => undefined);

    // Before "ready", nothing is sent; a ready from the wrong origin is ignored.
    post({ type: 'rb-ui-preview:ready' }, { origin: 'https://evil.example' });
    expect(postToFrame).not.toHaveBeenCalled();
    post({ type: 'rb-ui-preview:ready' });
    await waitFor(() => expect(postToFrame).toHaveBeenCalled());
    expect(postToFrame).toHaveBeenLastCalledWith(
      { type: 'rb-ui-preview:render', page: 'overview', pages: { overview: {} }, selectedId: null },
      window.location.origin,
    );

    // Selection from another origin or another window is ignored.
    post({ type: 'rb-ui-preview:select', id: 'overview.kpi.mrr' }, { origin: 'https://evil.example' });
    post({ type: 'rb-ui-preview:select', id: 'overview.kpi.mrr' }, { source: window });
    expect(within(properties()).getByText(/Select a component/)).toBeInTheDocument();

    post({ type: 'rb-ui-preview:select', id: 'overview.kpi.mrr' });
    expect(within(properties()).getByRole('heading', { name: 'KPI cards' })).toBeInTheDocument();
    await waitFor(() =>
      expect(postToFrame).toHaveBeenLastCalledWith(
        expect.objectContaining({ type: 'rb-ui-preview:render', selectedId: 'overview.kpi.mrr' }),
        window.location.origin,
      ),
    );

    // Edits are pushed to the preview immediately.
    fireEvent.change(within(properties()).getByLabelText('MRR ({currency}) label'), { target: { value: 'Monthly' } });
    await waitFor(() => {
      const last = postToFrame.mock.calls.at(-1)![0] as { pages: { overview: { kpis: { key: string; label?: string }[] } } };
      expect(last.pages.overview.kpis.find((k) => k.key === 'mrr')!.label).toBe('Monthly');
    });

    // Malformed selection messages are ignored.
    post({ type: 'rb-ui-preview:select', id: 'x'.repeat(200) });
    expect(within(properties()).getByRole('heading', { name: 'KPI cards' })).toBeInTheDocument();
  });
});
