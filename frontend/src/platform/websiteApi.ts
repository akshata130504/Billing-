/** Website CMS API (Platform Administrator only; enforced by the server). */
import type { LandingContent } from '../pages/public/landing/types';
import { consoleRequest } from './platformApi';

export interface WebsiteVersion {
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

export interface WebsiteVersionWithContent extends WebsiteVersion {
  content: LandingContent;
}

export interface WebsitePageState {
  key: string;
  published: WebsiteVersionWithContent;
  draft: (WebsiteVersionWithContent & { changed_sections: string[] }) | null;
  updated_at: string | null;
  updated_by_staff_id: string | null;
}

export interface WebsiteCompare {
  has_draft: boolean;
  changed_sections: string[];
  changes: { path: string; published: unknown; draft: unknown }[];
}

const PAGE = '/website/pages/landing';

export const websiteApi = {
  state: () => consoleRequest<WebsitePageState>('GET', PAGE),
  saveDraft: (content: LandingContent, revision: number) =>
    consoleRequest<WebsitePageState>('POST', `${PAGE}/draft`, { content, revision }),
  discardDraft: () => consoleRequest<WebsitePageState>('POST', `${PAGE}/draft/discard`),
  compare: () => consoleRequest<WebsiteCompare>('GET', `${PAGE}/compare`),
  publish: (revision: number, note?: string) => consoleRequest<WebsitePageState>('POST', `${PAGE}/publish`, { revision, note }),
  versions: (page = 1) =>
    consoleRequest<{ items: (WebsiteVersion & { live: boolean })[]; total: number; page: number; page_size: number; total_pages: number }>(
      'GET', `${PAGE}/versions?page=${page}&page_size=20`
    ),
  version: (version: number) => consoleRequest<WebsiteVersionWithContent>('GET', `${PAGE}/versions/${version}`),
  rollback: (version: number, note?: string) =>
    consoleRequest<WebsitePageState>('POST', `${PAGE}/versions/${version}/rollback`, { note }),
  restore: (version: number, revision: number) =>
    consoleRequest<WebsitePageState>('POST', `${PAGE}/versions/${version}/restore`, { revision }),
  uploadAsset: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return consoleRequest<{ url: string; bytes: number; content_type: string }>('POST', '/website/assets', form);
  },
};

/** "content.hero.headline" -> "hero.headline" (server field paths, for inline errors). */
export function fieldErrors(details: Record<string, unknown> | undefined): Record<string, string> {
  const fields = (details?.fields ?? {}) as Record<string, string>;
  const problems = (details?.problems ?? []) as { field: string; message: string }[];
  const out: Record<string, string> = {};
  for (const [path, message] of Object.entries(fields)) out[path.replace(/^content\./, '')] = String(message);
  for (const p of problems) out[p.field] = p.message;
  return out;
}
