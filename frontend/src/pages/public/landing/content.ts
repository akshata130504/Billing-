/**
 * Published landing-page content for the public site.
 *
 * The public page only ever requests the PUBLISHED version (GET /public/website/landing); drafts
 * are reachable solely through the authenticated platform console. If the API is unreachable the
 * page falls back to the bundled seed (defaultContent.json - the original page content), so the
 * public site never breaks because of the CMS.
 */
import defaultContentJson from './defaultContent.json';
import type { LandingContent } from './types';

export const DEFAULT_LANDING_CONTENT = defaultContentJson as unknown as LandingContent;

const TOP_LEVEL_KEYS: (keyof LandingContent)[] = [
  'seo', 'header', 'hero', 'section_order', 'capabilities', 'how_it_works', 'workflow', 'pricing', 'why',
  'audiences', 'customer_experience', 'operations', 'faq', 'final_cta', 'footer',
];

/** Shape check for what the API returned (the server already validated it strictly). */
export function isLandingContent(value: unknown): value is LandingContent {
  if (!value || typeof value !== 'object') return false;
  const obj = value as Record<string, unknown>;
  return obj.schema_version === 1 && TOP_LEVEL_KEYS.every((key) => obj[key] !== undefined && obj[key] !== null);
}

export async function fetchPublishedLanding(apiBase: string, timeoutMs = 4000): Promise<LandingContent> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${apiBase}/public/website/landing`, {
      headers: { Accept: 'application/json' },
      credentials: 'omit',
      signal: controller.signal,
    });
    if (!res.ok) return DEFAULT_LANDING_CONTENT;
    const body = await res.json();
    return isLandingContent(body?.content) ? body.content : DEFAULT_LANDING_CONTENT;
  } catch {
    return DEFAULT_LANDING_CONTENT;
  } finally {
    clearTimeout(timer);
  }
}

/** Title and meta description from the content (the SPA equivalent of server-side SEO tags). */
export function applySeo(content: LandingContent): void {
  if (typeof document === 'undefined') return;
  document.title = content.seo.title;
  let meta = document.querySelector('meta[name="description"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute('name', 'description');
    document.head.appendChild(meta);
  }
  meta.setAttribute('content', content.seo.description);
}
