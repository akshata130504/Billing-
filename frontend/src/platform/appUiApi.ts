/** Application visual-editor API. Reads: every platform role. Writes: Platform Administrator
 *  (enforced by the server; publish and rollback also need a recent step-up). */
import type { PageConfigs, PageKey } from '../appUi/registry';
import { consoleRequest } from './platformApi';

export interface AppUiVersion {
  id: string;
  state: 'draft' | 'published';
  version: number | null;
  revision: number;
  content_sha256: string;
  note: string | null;
  based_on_version: number | null;
  created_at: string | null;
  created_by_staff_id: string | null;
  updated_at: string | null;
  updated_by_staff_id: string | null;
  published_at: string | null;
  published_by_staff_id: string | null;
}

export type PageContent = NonNullable<PageConfigs[PageKey]>;

export interface AppUiChange {
  path: string;
  published: unknown;
  draft: unknown;
}

export interface AppUiPageState {
  key: PageKey;
  title: string;
  published: (AppUiVersion & { content: PageContent }) | null;
  defaults: PageContent;
  draft: (AppUiVersion & { content: PageContent; changes: AppUiChange[] }) | null;
  updated_at: string | null;
  updated_by_staff_id: string | null;
}

export interface AppUiPageSummary {
  key: PageKey;
  title: string;
  published_version: number | null;
  has_draft: boolean;
  updated_at: string | null;
}

const page = (key: PageKey) => `/app-ui/pages/${encodeURIComponent(key)}`;

export const appUiApi = {
  pages: () => consoleRequest<{ items: AppUiPageSummary[]; can_edit: boolean }>('GET', '/app-ui/pages'),
  state: (key: PageKey) => consoleRequest<AppUiPageState>('GET', page(key)),
  saveDraft: (key: PageKey, content: PageContent, revision: number) =>
    consoleRequest<AppUiPageState>('POST', `${page(key)}/draft`, { content, revision }),
  discardDraft: (key: PageKey) => consoleRequest<AppUiPageState>('POST', `${page(key)}/draft/discard`),
  publish: (key: PageKey, revision: number, note?: string) =>
    consoleRequest<AppUiPageState>('POST', `${page(key)}/publish`, { revision, note }),
  versions: (key: PageKey) =>
    consoleRequest<{ items: (AppUiVersion & { live: boolean })[]; total: number }>(
      'GET', `${page(key)}/versions?page=1&page_size=50`
    ),
  version: (key: PageKey, version: number) =>
    consoleRequest<AppUiVersion & { content: PageContent }>('GET', `${page(key)}/versions/${version}`),
  rollback: (key: PageKey, version: number, note?: string) =>
    consoleRequest<AppUiPageState>('POST', `${page(key)}/versions/${version}/rollback`, { note }),
  restore: (key: PageKey, version: number, revision: number) =>
    consoleRequest<AppUiPageState>('POST', `${page(key)}/versions/${version}/restore`, { revision }),
};
