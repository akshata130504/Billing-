import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '../../../components/common/Toast';
import { DEFAULT_LANDING_CONTENT } from '../../../pages/public/landing/content';
import type { LandingContent } from '../../../pages/public/landing/types';
import { PlatformRoutes } from '../../PlatformApp';
import { PlatformApiError, platformApi, type PlatformRole } from '../../platformApi';
import { websiteApi, type WebsitePageState } from '../../websiteApi';

vi.mock('../../platformApi', async () => {
  const actual = await vi.importActual<typeof import('../../platformApi')>('../../platformApi');
  return {
    ...actual,
    platformApi: { me: vi.fn(), refresh: vi.fn(), logout: vi.fn(), stepUp: vi.fn(), sessions: vi.fn() },
  };
});
vi.mock('../../websiteApi', async () => {
  const actual = await vi.importActual<typeof import('../../websiteApi')>('../../websiteApi');
  return {
    ...actual,
    websiteApi: {
      state: vi.fn(), saveDraft: vi.fn(), discardDraft: vi.fn(), compare: vi.fn(), publish: vi.fn(), versions: vi.fn(),
      version: vi.fn(), rollback: vi.fn(), restore: vi.fn(), uploadAsset: vi.fn(),
    },
  };
});

class NoopObserver {
  observe() {}
  disconnect() {}
  unobserve() {}
}
vi.stubGlobal('IntersectionObserver', NoopObserver);
vi.stubGlobal('matchMedia', (query: string) => ({
  matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {},
  addListener: () => {}, removeListener: () => {}, onchange: null, dispatchEvent: () => false,
}));

type Mocked<T> = { [K in keyof T]: ReturnType<typeof vi.fn> };
const auth = platformApi as unknown as Mocked<typeof platformApi>;
const api = websiteApi as unknown as Mocked<typeof websiteApi>;

const clone = (c: LandingContent): LandingContent => JSON.parse(JSON.stringify(c));
const meta = (over: object = {}) => ({
  id: 'v', state: 'published', version: 3, revision: 1, content_sha256: 'x', note: null, based_on_version: null,
  created_at: null, created_by_staff_id: null, updated_at: null, updated_by_staff_id: null,
  published_at: '2026-10-01T09:00:00Z', published_by_staff_id: null, ...over,
});

function pageState(draft: LandingContent | null, revision = 2): WebsitePageState {
  return {
    key: 'landing',
    published: { ...meta(), content: DEFAULT_LANDING_CONTENT } as WebsitePageState['published'],
    draft: draft ? ({ ...meta({ id: 'd', state: 'draft', version: null, revision }), content: draft, changed_sections: ['hero'] } as WebsitePageState['draft']) : null,
    updated_at: null,
    updated_by_staff_id: null,
  };
}

function renderAt(path: string, role: PlatformRole = 'platform_administrator') {
  auth.me.mockResolvedValue({ staff: { id: 's', email: 'a@rooman.test', full_name: 'Ada Admin', role }, session_id: 'x', session_expires_at: '2026-10-02T00:00:00Z', access_expires_in: 600 });
  return render(<ToastProvider><MemoryRouter initialEntries={[path]}><PlatformRoutes /></MemoryRouter></ToastProvider>);
}

beforeEach(() => vi.clearAllMocks());

describe('website CMS editor', () => {
  it('is hidden from and blocked for non-administrators', async () => {
    renderAt('/website', 'platform_operations');
    expect(await screen.findByText('Not available for your role')).toBeInTheDocument();
    expect(api.state).not.toHaveBeenCalled();
    const nav = screen.getByRole('navigation', { name: 'Platform console' });
    expect(within(nav).queryByRole('link', { name: 'Website' })).not.toBeInTheDocument();
  });

  it('edits the hero and saves a draft with the current revision', async () => {
    api.state.mockResolvedValue(pageState(null));
    const edited = clone(DEFAULT_LANDING_CONTENT);
    edited.hero.headline = 'Billing that grows with you.';
    api.saveDraft.mockResolvedValue(pageState(edited, 1));
    renderAt('/website');
    const headline = await screen.findByLabelText('Headline');
    expect(headline).toHaveValue('Powerful billing.');
    expect(screen.getByRole('button', { name: /Publish/ })).toBeDisabled(); // nothing to publish yet
    fireEvent.change(headline, { target: { value: 'Billing that grows with you.' } });
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Save draft/ }));
    await waitFor(() => expect(api.saveDraft).toHaveBeenCalledTimes(1));
    const [content, revision] = api.saveDraft.mock.calls[0];
    expect(revision).toBe(0);
    expect(content.hero.headline).toBe('Billing that grows with you.');
    expect(content.faq).toEqual(DEFAULT_LANDING_CONTENT.faq); // untouched sections unchanged
    expect(await screen.findByText(/Draft r1/)).toBeInTheDocument();
  });

  it('shows server validation errors next to the field', async () => {
    api.state.mockResolvedValue(pageState(null));
    api.saveDraft.mockRejectedValue(new PlatformApiError('The request contains invalid fields.', 422, 'VALIDATION_ERROR', {
      fields: { 'content.hero.headline': 'Value error, markup characters (< >) are not allowed in website text' },
    }));
    renderAt('/website');
    fireEvent.change(await screen.findByLabelText('Headline'), { target: { value: '<script>x</script>' } });
    fireEvent.click(screen.getByRole('button', { name: /Save draft/ }));
    expect(await screen.findByText(/markup characters/)).toBeInTheDocument();
    expect(screen.getByText(/Some fields are not valid/)).toBeInTheDocument();
  });

  it('edits repeatable items: add, reorder, hide, remove', async () => {
    api.state.mockResolvedValue(pageState(null));
    api.saveDraft.mockImplementation((content: LandingContent) => Promise.resolve(pageState(content, 1)));
    renderAt('/website');
    await screen.findByLabelText('Headline');
    fireEvent.click(screen.getByRole('button', { name: 'FAQ' }));
    const list = screen.getByText(/Questions \(5\)/).closest('fieldset')!;
    fireEvent.click(within(list).getByRole('button', { name: /Add question/ }));
    expect(within(list).getByText(/Questions \(6\)/)).toBeInTheDocument();
    fireEvent.click(within(list).getAllByRole('button', { name: 'Move up' })[5]);
    fireEvent.click(within(list).getAllByRole('button', { name: 'Hide' })[0]);
    fireEvent.click(within(list).getAllByRole('button', { name: 'Remove' })[1]);
    fireEvent.click(screen.getByRole('button', { name: /Save draft/ }));
    await waitFor(() => expect(api.saveDraft).toHaveBeenCalled());
    const items = (api.saveDraft.mock.calls[0][0] as LandingContent).faq.items;
    // [Q0..Q4] + New -> New moved above Q4 -> Q0 hidden -> Q1 removed
    const original = DEFAULT_LANDING_CONTENT.faq.items;
    expect(items.map((i) => i.q)).toEqual([original[0].q, original[2].q, original[3].q, 'New question?', original[4].q]);
    expect(items[0].visible).toBe(false);
    expect(items.slice(1).every((i) => i.visible !== false)).toBe(true);
  });

  it('previews the draft with the real landing page and toggles to the live version', async () => {
    const edited = clone(DEFAULT_LANDING_CONTENT);
    edited.hero.headline = 'Preview headline';
    api.state.mockResolvedValue(pageState(edited));
    renderAt('/website');
    fireEvent.click(await screen.findByRole('tab', { name: 'preview' }));
    const preview = await screen.findByTestId('landing-preview');
    expect(within(preview).getByText('Preview headline')).toBeInTheDocument();
    expect(within(preview).getByText('Frequently Asked Questions')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Live version 3/ }));
    expect(await within(screen.getByTestId('landing-preview')).findByText('Powerful billing.')).toBeInTheDocument();
  });

  it('publishes the saved draft through step-up', async () => {
    const edited = clone(DEFAULT_LANDING_CONTENT);
    edited.hero.headline = 'New';
    api.state.mockResolvedValue(pageState(edited, 4));
    api.publish
      .mockRejectedValueOnce(new PlatformApiError('Confirm it is you.', 403, 'STEP_UP_REQUIRED'))
      .mockResolvedValueOnce({ ...pageState(null), published: { ...meta({ version: 4 }), content: edited } });
    auth.stepUp.mockResolvedValue({ step_up_expires_at: 'x', expires_in: 900 });
    renderAt('/website');
    fireEvent.click(await screen.findByRole('button', { name: /Publish/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Changed sections: hero/)).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Launch the new hero headline' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish' }));
    fireEvent.change(await within(dialog).findByLabelText(/^Authenticator code/), { target: { value: '123456' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Verify and publish' }));
    await waitFor(() => expect(api.publish).toHaveBeenCalledTimes(2));
    expect(api.publish).toHaveBeenLastCalledWith(4, 'Launch the new hero headline');
    expect(await screen.findByText('Version 4 is live')).toBeInTheDocument();
  });

  it('lists history, restores into the draft and rolls back', async () => {
    api.state.mockResolvedValue(pageState(null));
    api.versions.mockResolvedValue({ items: [
      { ...meta({ id: 'v3', version: 3 }), live: true },
      { ...meta({ id: 'v2', version: 2, note: 'Old hero' }), live: false },
    ], total: 2, page: 1, page_size: 20, total_pages: 1 });
    api.restore.mockResolvedValue(pageState(clone(DEFAULT_LANDING_CONTENT), 1));
    api.rollback.mockResolvedValue({ ...pageState(null), published: { ...meta({ version: 4 }), content: DEFAULT_LANDING_CONTENT } });
    auth.stepUp.mockResolvedValue({});
    renderAt('/website');
    fireEvent.click(await screen.findByRole('tab', { name: 'history' }));
    const row = (await screen.findByText('Old hero')).closest('tr')!;
    expect(screen.getAllByRole('button', { name: 'Roll back to this' })).toHaveLength(1); // not on the live one
    fireEvent.click(within(row).getByRole('button', { name: 'Restore to draft' }));
    await waitFor(() => expect(api.restore).toHaveBeenCalledWith(2, 0));
    fireEvent.click(await screen.findByRole('tab', { name: 'history' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Roll back to this' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: 'Revert the hero experiment' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Roll back' }));
    await waitFor(() => expect(api.rollback).toHaveBeenCalledWith(2, 'Revert the hero experiment'));
  });

  it('shows field-level changes against the live page', async () => {
    api.state.mockResolvedValue(pageState(clone(DEFAULT_LANDING_CONTENT)));
    api.compare.mockResolvedValue({ has_draft: true, changed_sections: ['hero'], changes: [
      { path: 'hero.headline', published: 'Powerful billing.', draft: 'Billing that grows.' },
    ] });
    renderAt('/website');
    fireEvent.click(await screen.findByRole('tab', { name: 'Changes vs live' }));
    expect(await screen.findByText('hero.headline')).toBeInTheDocument();
    expect(screen.getByText('"Billing that grows."')).toBeInTheDocument();
  });
});
